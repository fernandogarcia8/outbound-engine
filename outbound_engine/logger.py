"""
Logs every action taken during a campaign run.
Writes to a local timestamped file AND updates the Google Sheet.
"""

import logging
import os
from datetime import datetime, timezone

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


def setup_file_logger(run_timestamp: str) -> logging.Logger:
    """
    Creates a logger that writes to logs/run_<timestamp>.log.
    Returns the logger instance to use throughout the run.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"run_{run_timestamp}.log")

    logger = logging.getLogger("outbound_engine")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if called multiple times in the same process
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s")

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def now_iso() -> str:
    """Returns the current UTC date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class RunSummary:
    """Tracks stats across the entire run and prints a summary at the end."""

    def __init__(self):
        self.total_eligible  = 0
        self.sent_email      = 0
        self.sent_sms        = 0
        self.sent_both       = 0
        self.skipped         = 0
        self.errors          = 0

    def record_sent(self, email_sent: bool, sms_sent: bool) -> None:
        if email_sent and sms_sent:
            self.sent_both  += 1
        elif email_sent:
            self.sent_email += 1
        elif sms_sent:
            self.sent_sms   += 1

    def record_skipped(self) -> None:
        self.skipped += 1

    def record_error(self) -> None:
        self.errors += 1

    def total_contacted(self) -> int:
        return self.sent_email + self.sent_sms + self.sent_both

    def print_summary(self, logger: logging.Logger) -> None:
        logger.info("─" * 50)
        logger.info("RUN SUMMARY")
        logger.info("─" * 50)
        logger.info(f"  Eligible rows processed : {self.total_eligible}")
        logger.info(f"  Successfully contacted   : {self.total_contacted()}")
        logger.info(f"    ↳ Email + SMS          : {self.sent_both}")
        logger.info(f"    ↳ Email only           : {self.sent_email}")
        logger.info(f"    ↳ SMS only             : {self.sent_sms}")
        logger.info(f"  Skipped (no contact info): {self.skipped}")
        logger.info(f"  Errors (API failures)    : {self.errors}")
        logger.info("─" * 50)
