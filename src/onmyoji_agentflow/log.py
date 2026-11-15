"""Logging setup. Secrets must never be passed to the logger."""
import logging
import sys

logger = logging.getLogger("onmyoji_agentflow")


def setup_logging(level: str = "INFO", logfile: str | None = None) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.handlers.clear()
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    if logfile:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger.setLevel(level)
