"""
Extraction script for NinaPro DB6.

DB6 files are named ``S{subject}_D{day}_T{time}.mat`` where ``time`` is
1 (morning) or 2 (afternoon). EMG signals are segmented using the
``restimulus`` labels.

The order of measurements is encoded in ``RawSignal.timestamp``:
    base(day, time) + offset of the segment within the recording.

* base: ``REFERENCE_DATE + (day - 1) days`` at ``SESSION_START_HOURS[time]``
  (08:00 for morning, 14:00 for afternoon).
* offset: segment start sample / fs, in whole seconds (timestamps are stored
  with 1 s resolution). If two consecutive segments would get the same
  second, the later one is shifted by 1 s so the order stays strictly
  increasing.

Sorting signals by timestamp therefore reproduces the order
day -> session (morning/afternoon) -> position within the session.
"""

import datetime
import glob
import logging
import os
import random
import re
from functools import partial
from multiprocessing import Pool, cpu_count

import numpy as np
from scipy.io import loadmat
from tqdm import tqdm

from dexterous_bioprosthesis_2021_raw_datasets.raw_signals.raw_signal import RawSignal
from dexterous_bioprosthesis_2021_raw_datasets.raw_signals.raw_signals import RawSignals
from dexterous_bioprosthesis_2021_raw_datasets.raw_signals.raw_signals_io import (
    save_signals_to_dirs,
)
from log_keeper.log_keeper import LogKeeper

from ninapro_preprocess import settings

FILE_NAME_REGEX = re.compile(r"S(?P<subject>\d+)_D(?P<day>\d+)_T(?P<time>\d+)")
REFERENCE_DATE = datetime.datetime(2000, 1, 1)
SESSION_START_HOURS = {1: 8, 2: 14}  # T1 - morning, T2 - afternoon

DEFAULT_SOURCES = {
    "emg": {"name_pattern": "C{i}", "channels": slice(None)},
}


def parse_file_name(mat_file):
    """Return (subject, day, time) parsed from a DB6 file name."""
    name = os.path.splitext(os.path.basename(mat_file))[0]
    match = FILE_NAME_REGEX.fullmatch(name)
    if match is None:
        raise ValueError(f"File name {name} does not match S<s>_D<d>_T<t> pattern.")
    return int(match["subject"]), int(match["day"]), int(match["time"])


def session_base_timestamp(day, time):
    """Unix timestamp of the beginning of the session (day, time)."""
    if time not in SESSION_START_HOURS:
        raise ValueError(f"Unknown session time T{time}. Expected one of {list(SESSION_START_HOURS)}.")
    base = REFERENCE_DATE + datetime.timedelta(days=day - 1, hours=SESSION_START_HOURS[time])
    return int(base.timestamp())


def split_matrix(X, y, base_timestamp, fs=2000, channel_names=None):
    """Split X into RawSignal segments of constant label y.

    Each segment gets timestamp = base_timestamp + segment start time [s],
    forced to be strictly increasing.
    """
    y = np.asarray(y)
    change_points = np.flatnonzero(y[1:] != y[:-1]) + 1
    starts = np.concatenate(([0], change_points))
    ends = np.concatenate((change_points, [len(y)]))

    raw_signals = []
    prev_ts = None
    for start, end in zip(starts, ends):
        ts = base_timestamp + int(start // fs)
        if prev_ts is not None and ts <= prev_ts:
            ts = prev_ts + 1
        prev_ts = ts
        raw_signals.append(
            RawSignal(
                signal=X[start:end],
                object_class=str(y[start]),
                sample_rate=fs,
                channel_names=channel_names,
                timestamp=ts,
            )
        )
    return raw_signals


def process_mat_obj(mat_obj, base_timestamp, lab_key="restimulus", fs=2000, sources=None, logger=None) -> RawSignals:
    """Convert a loaded DB6 .mat dict into RawSignals with ordered timestamps."""
    if sources is None:
        sources = DEFAULT_SOURCES
    if logger is None:
        logger = logging.getLogger(__name__)

    arrays = []
    channel_names = []
    for mat_key, src_cfg in sources.items():
        data = mat_obj[mat_key][:, src_cfg.get("channels", slice(None))]
        pattern = src_cfg.get("name_pattern", f"{mat_key}_{{i}}")
        channel_names.extend(pattern.format(i=i) for i in range(data.shape[1]))
        arrays.append(data)
    combined_np = np.hstack(arrays)

    labels = np.asarray(mat_obj[lab_key]).ravel().astype(int)
    logger.debug("Found unique labels: %s", np.unique(labels))

    r_signals_list = split_matrix(
        combined_np, labels, base_timestamp=base_timestamp, fs=fs, channel_names=channel_names
    )
    raw_signals = RawSignals(raw_signal_list=r_signals_list, sample_rate=fs)

    u_lab, u_cnt = np.unique(raw_signals.get_labels(), return_counts=True)
    logger.debug("Found %d signals. Label stats: %s", len(raw_signals), dict(zip(u_lab, u_cnt)))
    return raw_signals


def _process_single_mat_file(mat_file, output_directory, fs, sources, labels_keys, logging_queue):
    """Process a single DB6 mat file. Designed to be called in a separate process."""
    worker_logger = LogKeeper.get_client_logger(
        logging_queue=logging_queue, logger_name=f"Worker for {os.path.basename(mat_file)}"
    )
    worker_logger.info("Processing %s", mat_file)
    try:
        subject, day, time = parse_file_name(mat_file)
        base_ts = session_base_timestamp(day, time)
        worker_logger.info(
            "Subject %d, day %d, time %d -> base timestamp %s",
            subject, day, time, datetime.datetime.fromtimestamp(base_ts),
        )

        loaded_mat = loadmat(mat_file)
        mat_file_name = os.path.splitext(os.path.basename(mat_file))[0]
        for lab_key in labels_keys:
            out_dataset_directory = os.path.join(output_directory, f"{mat_file_name}_{lab_key}")
            worker_logger.info("Processing labels key %s.", lab_key)
            raw_signals = process_mat_obj(
                loaded_mat, base_timestamp=base_ts, lab_key=lab_key, fs=fs,
                sources=sources, logger=worker_logger,
            )
            worker_logger.info("Saving processed signals to %s", out_dataset_directory)
            save_signals_to_dirs(raw_signals, out_dataset_directory)
    except Exception as e:
        worker_logger.error("Error processing %s: %s", mat_file, e, exc_info=True)
    finally:
        worker_logger.info("Finished processing %s", mat_file)
        LogKeeper.shutdown_client_logger(worker_logger)


def run_experiment(
    input_dir,
    output_directory,
    fs=2000,
    sources=None,
    labels_keys=("restimulus",),
    mat_file_regex="**/S*_D*_T*.mat",
    progress_log_handler=None,
    comment_str="",
    n_workers=None,
    logging_queue=None,
):
    exp_logger = LogKeeper.get_client_logger(
        logging_queue=logging_queue, logger_name="Main Experiment logger"
    )

    mat_files = sorted(glob.glob(os.path.join(input_dir, mat_file_regex), recursive=True))
    n_mat_files = len(mat_files)
    exp_logger.info("Found %d mat files.", n_mat_files)

    info_file_path = os.path.join(output_directory, "info.md")
    with open(info_file_path, "w") as f:
        f.write(f"# Experiment Info\n\n{comment_str}\n")
        f.write(f"Input directory: {input_dir}\n")
        f.write(f"Output directory: {output_directory}\n")
        f.write(f"Sampling frequency: {fs}\n")
        f.write(f"Mat file regex: {mat_file_regex}\n")
        f.write(f"Sources: {sources}\n")
        f.write(f"Labels keys: {labels_keys}\n")
        f.write(f"Timestamp reference date: {REFERENCE_DATE}\n")
        f.write(f"Session start hours: {SESSION_START_HOURS}\n")
        f.write(f"Found {n_mat_files} mat files.\nMat files:\n")
        for mat_file in mat_files:
            f.write(f"- {mat_file}\n")

    if n_workers is None:
        n_workers = cpu_count()

    worker_fn = partial(
        _process_single_mat_file,
        output_directory=output_directory,
        fs=fs,
        sources=sources,
        labels_keys=list(labels_keys),
        logging_queue=logging_queue,
    )

    exp_logger.info("Processing %d mat files with %d workers.", n_mat_files, n_workers)
    with Pool(processes=n_workers) as pool:
        for _ in tqdm(
            pool.imap_unordered(worker_fn, mat_files),
            desc="Mat file: ",
            file=progress_log_handler,
            total=n_mat_files,
        ):
            pass
    LogKeeper.shutdown_client_logger(exp_logger)


def main():
    np.random.seed(0)
    random.seed(0)

    output_directory = os.path.join(settings.OUTPUT_DATA_PATH, "./db6/")
    os.makedirs(output_directory, exist_ok=True)

    log_dir = os.path.dirname(settings.EXPERIMENTS_LOGS_PATH)
    log_file = os.path.splitext(os.path.basename(__file__))[0]
    log_file_path = LogKeeper.generate_file_name(logging_dir_path=log_dir, name_prefix=log_file)
    logging_queue = LogKeeper.generate_logging_queue()
    lp = LogKeeper(
        logging_queue=logging_queue,
        log_file_path=log_file_path,
        run_threaded=True,
        stderr_handler=True,
    )
    lp.start()

    comment_str = """
    NinaPro DB6 extraction: EMG signals segmented by restimulus.
    Measurement order (day, session, position in session) encoded in RawSignal timestamp.
    """
    progress_log_path = os.path.join(output_directory, "progress.log")
    with open(progress_log_path, "w") as progress_log_handler:
        run_experiment(
            settings.DB6DATAPATH,
            output_directory,
            fs=2000,
            sources=DEFAULT_SOURCES,
            labels_keys=["restimulus"],
            progress_log_handler=progress_log_handler,
            comment_str=comment_str,
            n_workers=None,
            logging_queue=logging_queue,
        )
    lp.quit()


if __name__ == "__main__":
    main()
