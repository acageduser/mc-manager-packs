import logging
from pathlib import Path
import datetime
from .config import settings_dir

def init_logging():
    log_dir = Path(settings_dir()) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / (datetime.datetime.now().strftime("%Y%m%d") + ".log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(logfile, encoding="utf-8"), logging.StreamHandler()],
    )
    logging.info("Logging initialized at %s", logfile)
    return logfile
