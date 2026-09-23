import logging

from app.platform.config import get_settings
from app.platform.logging import configure_logging, log_event


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log_event(logging.getLogger("nianian.worker"), logging.INFO, "WORKER_READY")


if __name__ == "__main__":
    main()
