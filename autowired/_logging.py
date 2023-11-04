try:  # pragma: no cover
    # noinspection PyPackageRequirements
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    # noinspection PyMethodMayBeStatic
    class _SimpleLogger:
        def trace(self, msg: str):
            logging.debug(msg)

    logger = _SimpleLogger()
