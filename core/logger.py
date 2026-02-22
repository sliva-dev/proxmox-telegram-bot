import logging
import sys
import os
import re
from logging.handlers import RotatingFileHandler

TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


class TokenMasker(logging.Filter):
    """Маскирует токен бота в логах, если он там внезапно появится."""

    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = TOKEN_RE.sub("bot[TOKEN_HIDDEN]", record.msg)
        return True


def setup_logging():
    if not os.path.exists("logs"):
        os.makedirs("logs")

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    file_handler = RotatingFileHandler(
        "logs/bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TokenMasker())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
