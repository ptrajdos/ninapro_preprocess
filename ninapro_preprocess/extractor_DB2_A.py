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

def split_matrix(X, y, fs=2000, channels=slice(None)):
    raw_signals = []
    start_idx = 0

    for i in range(1, len(y)):
        if y[i] != y[i - 1]:
            raw_signals.append(
                RawSignal(
                    signal=X[start_idx:i, channels],
                    object_class=str(y[i - 1]),
                    sample_rate=fs,
                )
            )
            start_idx = i

    raw_signals.append(
        RawSignal(
            signal=X[start_idx:, channels], object_class=str(y[start_idx]), sample_rate=fs
        )
    )

    return raw_signals

def preprocess_labels(labels):
    return [
        int(lab[0]) for lab in labels
    ]

def process_mat_obj(
    mat_obj, lab_key="stimulus", fs=2000, channels=slice(None)
) -> RawSignals:
    logging.debug("Processing labels")
    emg_np = mat_obj["emg"]
    labels = preprocess_labels(mat_obj[lab_key])
    u_labels = np.unique(labels)
    logging.debug(f"Found {len(u_labels)} unique labels: {u_labels}")

    r_signals_list = split_matrix(emg_np, labels, fs=fs, channels=channels)

    raw_signals = RawSignals(raw_signal_list=r_signals_list, sample_rate=fs)
    logging.debug(f"Finished processing labels. Found {len(raw_signals)} signals.")
    u_sig_labels, u_sig_labels_counts =  np.unique(raw_signals.get_labels(), return_counts=True)
    lab_stats = dict(zip(u_sig_labels, u_sig_labels_counts))
    logging.debug(f"Signal label stats: {lab_stats}")
    return raw_signals


def get_eff_label_keys(labels_keys):
    if labels_keys is None:
        return ["stimulus", "restimulus"]

    return labels_keys


def run_experiment(
    input_dir,
    output_directory,
    channels=slice(None),
    fs=2000,
    labels_keys=None,
    progress_log_handler=None,
    comment_str="",
):
    logging.info("Searching fot mat files...")
    mat_files = glob.glob(f"{input_dir}/*.mat", recursive=True)
    n_mat_files = len(mat_files)
    logging.debug(f"Found {n_mat_files} mat files.")

    for mat_file in tqdm(
        mat_files, desc="Mat file: ", file=progress_log_handler, total=n_mat_files
    ):
        logging.info(f"Processing {mat_file}")
        loaded_mat = loadmat(mat_file)
        mat_file_name = os.path.splitext(os.path.basename(mat_file))[0]
        for lab_key in get_eff_label_keys(labels_keys):
            out_dataset_directory = os.path.join(
                output_directory, f"{mat_file_name}_{lab_key}"
            )
            raw_sigals = process_mat_obj(loaded_mat, fs=fs, channels=channels)
            save_signals_to_dirs(raw_sigals, out_dataset_directory)


def main():
    np.random.seed(0)
    random.seed(0)

    data_path = settings.DB2DATAPATH

    output_directory = os.path.join(
        settings.OUTPUT_DATA_PATH,
        "./db2/",
    )
    os.makedirs(output_directory, exist_ok=True)

    log_dir = os.path.dirname(settings.EXPERIMENTS_LOGS_PATH)
    log_file = os.path.splitext(os.path.basename(__file__))[0]
    logger(log_dir, log_file, enable_logging=True)

    progress_log_path = os.path.join(output_directory, "progress.log")
    progress_log_handler = open(progress_log_path, "w")

    comment_str = """
    Simple feature extraction.
    """
    run_experiment(
        data_path,
        output_directory,
        channels=slice(None),
        progress_log_handler=progress_log_handler,
        comment_str=comment_str,
    )


if __name__ == "__main__":
    main()
