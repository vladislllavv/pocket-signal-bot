"""
Настройка логирования.
Использует стандартный logging (совместимость) + loguru (красивые цвета).
"""

from __future__ import annotations

import logging
import sys

from loguru import logger as loguru_logger

from app.config import config


class InterceptHandler(logging.Handler):
    """Перенаправляет стандартные логи из logging в loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """Настройка логирования."""
    # Удаляем все стандартные handler'ы
    logging.root.handlers = []
    logging.root.setLevel(config.LOG_LEVEL)

    # Перехватчик
    handler = InterceptHandler()
    logging.root.addHandler(handler)

    # Библиотеки, которые мы хотим видеть
    for name in (
        "aiogram",
        "aiohttp",
        "sqlalchemy.engine",
        "apscheduler",
    ):
        logging.getLogger(name).setLevel(config.LOG_LEVEL)
        logging.getLogger(name).handlers = []
        logging.getLogger(name).addHandler(handler)

    # Настройка loguru
    loguru_logger.remove()  # удаляем дефолтный stderr

    # Вывод в stderr (цветной)
    loguru_logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=config.LOG_LEVEL,
        colorize=True,
    )

    # Вывод в файл
    loguru_logger.add(
        config.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=config.LOG_LEVEL,
        rotation="10 MB",
        retention="7 days",
    )

    loguru_logger.info("Логирование настроено (уровень: {})", config.LOG_LEVEL)
