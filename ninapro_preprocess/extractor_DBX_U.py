import glob
from ninapro_preprocess import settings
from ninapro_preprocess.tools import logger
import numpy as np
import random
import os
from scipy.io import loadmat
from tqdm import tqdm
from dexterous_bioprosthesis_2021_raw_datasets.raw_signals.raw_signals import RawSignals
from dexterous_bioprosthesis_2021_raw_datasets.raw_signals.raw_signal import RawSignal
from dexterous_bioprosthesis_2021_raw_datasets.raw_signals.raw_signals_io import (
    save_signals_to_dirs,
)
import logging
from multiprocessing import Pool, cpu_count
from functools import partial
from log_keeper.log_keeper import LogKeeper


def split_matrix(X, y, fs=2000, channels=slice(None), channel_names=None):
    raw_signals = []
    start_idx = 0

    for i in range(1, len(y)):
        if y[i] != y[i - 1]:
            raw_signals.append(
                RawSignal(
                    signal=X[start_idx:i, channels],
                    object_class=str(y[i - 1]),
                    sample_rate=fs,
                    channel_names=channel_names,
                )
            )
            start_idx = i

    raw_signals.append(
        RawSignal(
            signal=X[start_idx:, channels],
            object_class=str(y[start_idx]),
            sample_rate=fs,
            channel_names=channel_names,
        )
    )

    return raw_signals


def preprocess_labels(labels):
    return [int(lab[0]) for lab in labels]


DEFAULT_SOURCES = {
    "emg": {"name_pattern": "C{i}", "channels": slice(None)},
    "force": {"name_pattern": "F{i}", "channels": slice(None)},
}


def process_mat_obj(mat_obj, lab_key="stimulus", fs=2000, sources=None, logger=None) -> RawSignals:
    """
    Process a loaded .mat object into RawSignals.

    Args:
        mat_obj: Loaded mat file dict.
        lab_key: Key for labels in mat_obj.
        fs: Sampling frequency.
        sources: Dict describing which mat_obj elements to use.
            Each key is a mat_obj key, each value is a dict with:
                - "name_pattern": str with "{i}" placeholder for channel naming (e.g. "C{i}").
                - "channels": slice or index array to select columns from that element.
            If None, defaults to DEFAULT_SOURCES (emg + force).
    """
    if sources is None:
        sources = DEFAULT_SOURCES

    logging.debug("Processing labels")

    arrays = []
    channel_names = []
    for mat_key, src_cfg in sources.items():
        data = mat_obj[mat_key]
        cols = src_cfg.get("channels", slice(None))
        data = data[:, cols]
        n_ch = data.shape[1]
        pattern = src_cfg.get("name_pattern", f"{mat_key}_{{i}}")
        channel_names.extend([pattern.format(i=i) for i in range(n_ch)])
        arrays.append(data)

    combined_np = np.hstack(arrays)

    labels = preprocess_labels(mat_obj[lab_key])
    u_labels = np.unique(labels)
    logging.debug(f"Found {len(u_labels)} unique labels: {u_labels}")

    r_signals_list = split_matrix(
        combined_np, labels, fs=fs, channel_names=channel_names
    )

    raw_signals = RawSignals(raw_signal_list=r_signals_list, sample_rate=fs)
    logging.debug(f"Finished processing labels. Found {len(raw_signals)} signals.")
    u_sig_labels, u_sig_labels_counts = np.unique(
        raw_signals.get_labels(), return_counts=True
    )
    lab_stats = dict(zip(u_sig_labels, u_sig_labels_counts))
    logging.debug(f"Signal label stats: {lab_stats}")
    return raw_signals


def get_eff_label_keys(labels_keys):
    if labels_keys is None:
        return ["stimulus"]

    return labels_keys


def _process_single_mat_file(
    mat_file, output_directory, fs, sources, labels_keys, info_file_path, logging_queue
):
    """Process a single mat file. Designed to be called in a separate process."""
    worker_logger = LogKeeper.get_client_logger(
        logging_queue=logging_queue, logger_name=f"Worker for {os.path.basename(mat_file)}"
    )
    worker_logger.info("Processing %s", mat_file)
    try:

        loaded_mat = loadmat(mat_file)
        worker_logger.info("Loaded %s successfully.", mat_file)
        mat_file_name = os.path.splitext(os.path.basename(mat_file))[0]
        for lab_key in get_eff_label_keys(labels_keys):
            worker_logger.info("Processing labels with key: %s", lab_key)
            out_dataset_directory = os.path.join(
                output_directory, f"{mat_file_name}_{lab_key}"
            )
            worker_logger.info("Processing mat file %s with labels key %s.", mat_file, lab_key)
            raw_sigals = process_mat_obj(loaded_mat, fs=fs, sources=sources, lab_key=lab_key, logger=worker_logger)
            worker_logger.info("Saving processed signals to %s", out_dataset_directory)
            save_signals_to_dirs(raw_sigals, out_dataset_directory)
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
    labels_keys=None,
    mat_file_regex="*.mat",
    progress_log_handler=None,
    comment_str="",
    n_workers=None,
    logging_queue=None,
):
    exp_logger = LogKeeper.get_client_logger(
        logging_queue=logging_queue, logger_name="Main Experiment logger"
    )

    info_file_path = os.path.join(output_directory, "info.md")
    with open(info_file_path, "w") as f:
        f.write(f"# Experiment Info\n\n{comment_str}\n")
        f.write(f"Input directory: {input_dir}\n")
        f.write(f"Output directory: {output_directory}\n")
        f.write(f"Sampling frequency: {fs}\n")
        f.write(f"Mat file regex: {mat_file_regex}\n")
        f.write(f"Sources: {sources}\n")
        f.write(f"Labels keys: {labels_keys}\n")

    exp_logger.info("Searching for mat files...")
    mat_files = glob.glob(f"{input_dir}/{mat_file_regex}", recursive=True)
    n_mat_files = len(mat_files)
    exp_logger.debug(f"Found {n_mat_files} mat files.")

    with open(info_file_path, "a") as f:
        f.write(f"Found {n_mat_files} mat files.\n")
        f.write(f"Mat files:\n")
        for mat_file in mat_files:
            f.write(f"- {mat_file}\n")

    if n_workers is None:
        n_workers = cpu_count()

    worker_fn = partial(
        _process_single_mat_file,
        output_directory=output_directory,
        fs=fs,
        sources=sources,
        labels_keys=labels_keys,
        info_file_path=info_file_path,
        logging_queue=logging_queue,
    )

    exp_logger.info(f"Processing {n_mat_files} mat files with {n_workers} workers.")
    with Pool(processes=n_workers) as pool:
        for _ in tqdm(
            pool.imap_unordered(worker_fn, mat_files),
            desc="Mat file: ",
            file=progress_log_handler,
            total=n_mat_files,
        ):
            pass


def main():
    np.random.seed(0)
    random.seed(0)

    data_path = settings.DB2DATAPATH

    output_directory = os.path.join(
        settings.OUTPUT_DATA_PATH,
        "./db2_force/",
    )
    os.makedirs(output_directory, exist_ok=True)

    # TODO change to using logKeeper!
    log_dir = os.path.dirname(settings.EXPERIMENTS_LOGS_PATH)
    log_file = os.path.splitext(os.path.basename(__file__))[0]

    log_file_path = LogKeeper.generate_file_name(
        logging_dir_path=log_dir, name_prefix=log_file
    )
    logging_queue = LogKeeper.generate_logging_queue()
    lp = LogKeeper(
        logging_queue=logging_queue,
        log_file_path=log_file_path,
        run_threaded=True,
        stderr_handler=True,
    )
    lp.start()

    progress_log_path = os.path.join(output_directory, "progress.log")
    progress_log_handler = open(progress_log_path, "w")

    comment_str = """
    Simple feature extraction.
    Multiple sources from mat files can be extracted.
    """
    run_experiment(
        data_path,
        output_directory,
        fs=2000,
        sources={
            "emg": {"name_pattern": "C{i}", "channels": slice(None)},
        },
        labels_keys=["restimulus"],
        mat_file_regex="*.mat",
        progress_log_handler=progress_log_handler,
        comment_str=comment_str,
        logging_que=logging_queue,
        n_workers=None,
    )
    lp.quit()


if __name__ == "__main__":
    """
    Extract EMG and force levels (last 6 columns)
    """
    main()
