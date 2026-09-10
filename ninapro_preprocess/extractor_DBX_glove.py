from ninapro_preprocess import settings
import numpy as np
import random
import os
from ninapro_preprocess.extractor_DBX_U import run_experiment
from log_keeper.log_keeper import LogKeeper


def main():
    np.random.seed(0)
    random.seed(0)

    data_path = settings.DB2DATAPATH

    output_directory = os.path.join(
        settings.OUTPUT_DATA_PATH,
        "./db2_glove/",
    )
    os.makedirs(output_directory, exist_ok=True)

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
    Extract emg and glove signals from mat files.
    """
    run_experiment(
        data_path,
        output_directory,
        fs=2000,
        sources={
            "emg": {"name_pattern": "C{i}", "channels": slice(None)},
            "glove": {"name_pattern": "JA{i}", "channels": slice(None)},
        },
        labels_keys=["restimulus"],
        mat_file_regex="*.mat",
        progress_log_handler=progress_log_handler,
        comment_str=comment_str,
        logging_queue=logging_queue,
        n_workers=None,
    )
    lp.quit()


if __name__ == "__main__":
    """
    Extract emg glove data from mat files.
    """
    main()
