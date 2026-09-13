"""(#14) Structured (JSON) logging, so requests can actually be inspected
after the fact via DigitalOcean's Runtime Logs / `doctl apps logs`, instead
of the service being a black box.
"""

import json
import logging
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("delphos_works")
    if logger.handlers:
        return logger  # already configured (e.g. re-imported)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_request(logger: logging.Logger, **fields) -> None:
    logger.info("request", extra={"extra_fields": fields})
