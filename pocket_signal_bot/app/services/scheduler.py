"""
Планировщик задач на основе APScheduler.
Запускает периодический анализ рынков и отправку сигналов.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import config

logger = logging.getLogger(__name__)


class SignalScheduler:
    """
    Обёртка над APScheduler для запуска/остановки
    периодических задач анализа.
    """

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self._jobs: dict[str, Any] = {}

    def start(self) -> None:
        """Запуск планировщика."""
        self.scheduler.start()
        logger.info("Scheduler: запущен")

    def stop(self) -> None:
        """Остановка планировщика."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler: остановлен")

    def add_signal_job(
        self,
        coro_func: Any,
        job_id: str = "signal_analysis",
        interval_seconds: int | None = None,
    ) -> None:
        """
        Добавить задачу анализа сигналов.

        Args:
            coro_func: корутина для выполнения (SignalManager._analysis_cycle)
            job_id: уникальный ID задачи
            interval_seconds: интервал в секундах (по умолч. из config)
        """
        interval = interval_seconds or config.SIGNAL_CHECK_INTERVAL_SEC

        if job_id in self._jobs:
            logger.warning("Job %s уже существует, удаляю", job_id)
            self.remove_job(job_id)

        job = self.scheduler.add_job(
            coro_func,
            trigger=IntervalTrigger(seconds=interval),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=30,
        )
        self._jobs[job_id] = job
        logger.info(
            "Scheduler: добавлена задача %s (интервал=%dс)", job_id, interval
        )

    def remove_job(self, job_id: str) -> None:
        """Удалить задачу."""
        try:
            self.scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)
            logger.info("Scheduler: задача %s удалена", job_id)
        except Exception as exc:
            logger.warning("Scheduler: ошибка удаления %s: %s", job_id, exc)

    def pause_all(self) -> None:
        """Приостановить все задачи."""
        self.scheduler.pause()
        logger.info("Scheduler: все задачи приостановлены")

    def resume_all(self) -> None:
        """Возобновить все задачи."""
        self.scheduler.resume()
        logger.info("Scheduler: все задачи возобновлены")
