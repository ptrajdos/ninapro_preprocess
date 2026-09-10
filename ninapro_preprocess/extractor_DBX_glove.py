from ninapro_preprocess import settings
from ninapro_preprocess.tools import logger
import numpy as np
import random
import os
from ninapro_preprocess.extractor_DB2_B import run_experiment


def main():
    np.random.seed(0)
    random.seed(0)

    data_path = settings.DB2DATAPATH

    output_directory = os.path.join(
        settings.OUTPUT_DATA_PATH,
        "./db2_acc/",
    )
    os.makedirs(output_directory, exist_ok=True)

    log_dir = os.path.dirname(settings.EXPERIMENTS_LOGS_PATH)
    log_file = os.path.splitext(os.path.basename(__file__))[0]
    logger(log_dir, log_file, enable_logging=True)

    progress_log_path = os.path.join(output_directory, "progress.log")
    progress_log_handler = open(progress_log_path, "w")

    comment_str = """
    Extract accelerometer (acc) signals from mat files.
    """
    run_experiment(
        data_path,
        output_directory,
        fs=2000,
        sources={
            "emg": {"name_pattern": "C{i}", "channels": slice(None)},
            "glove": {"name_pattern": "JA{i}", "channels": slice(None)},
        },
        labels_keys=None,
        mat_file_regex="*.mat",
        progress_log_handler=progress_log_handler,
        comment_str=comment_str,
    )


if __name__ == "__main__":
    """
    Extract accelerometer (acc) data from DB2 mat files.
    """
    main()
