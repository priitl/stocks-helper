"""Batch job scheduler for daily portfolio updates."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.lib.db import db_session
from src.models.portfolio import Portfolio
from src.services.batch_processor import BatchProcessor

logger = logging.getLogger(__name__)


class PortfolioScheduler:
    """Manages scheduled batch jobs for portfolio updates."""

    def __init__(self) -> None:
        """Initialize portfolio scheduler."""
        self.scheduler = BackgroundScheduler()
        self.batch_processor = BatchProcessor()
        self.is_running = False

    def start(self, daily_time: str = "18:00") -> None:
        """
        Start the scheduler daemon.

        Args:
            daily_time: Time to run daily batch (HH:MM in local time, default 18:00 / 6 PM)
        """
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        # Parse time
        hour, minute = map(int, daily_time.split(":"))

        # Add daily job
        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            self.run_daily_batch,
            trigger=trigger,
            id="daily_portfolio_update",
            name="Daily Portfolio Update",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.start()
        self.is_running = True
        logger.info(f"Scheduler started - daily batch at {daily_time}")

    def stop(self) -> None:
        """Stop the scheduler daemon."""
        if not self.is_running:
            return

        self.scheduler.shutdown(wait=True)
        self.is_running = False
        logger.info("Scheduler stopped")

    def run_daily_batch(self) -> None:
        """Run daily batch job for all portfolios."""
        logger.info("Starting daily batch job")
        start_time = datetime.now()

        try:
            # Run async batch in sync context
            asyncio.run(self._process_all_portfolios())

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Daily batch completed in {duration:.1f}s")

        except Exception as e:
            logger.error(f"Daily batch failed: {e}", exc_info=True)
            # Scheduler will retry based on configuration

    async def _process_all_portfolios(self) -> None:
        """Process all portfolios in the database."""
        with db_session() as session:
            portfolios = session.query(Portfolio).all()
            logger.info(f"Processing {len(portfolios)} portfolios")

            for portfolio in portfolios:
                logger.info(f"Processing portfolio: {portfolio.name} ({portfolio.id})")

                try:
                    summary = await self.batch_processor.process_portfolio(portfolio.id)

                    logger.info(
                        f"Portfolio {portfolio.name}: "
                        f"{summary['market_data_updated']} stocks updated, "
                        f"{summary['recommendations_generated']} recommendations, "
                        f"{summary['insights_generated']} insights"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process portfolio {portfolio.name}: {e}", exc_info=True
                    )
                    # Continue with next portfolio

    async def run_once(self) -> dict[str, Any]:
        """
        Run batch job once for all portfolios (manual trigger).

        Returns:
            Summary dict with batch results
        """
        logger.info("Running manual batch job")
        start_time = datetime.now()

        with db_session() as session:
            portfolios = session.query(Portfolio).all()

            total_summary = {
                "portfolios_processed": 0,
                "portfolios_failed": 0,
                "total_stocks_updated": 0,
                "total_recommendations": 0,
                "total_insights": 0,
                "duration_seconds": 0.0,
            }

            for portfolio in portfolios:
                try:
                    summary = await self.batch_processor.process_portfolio(portfolio.id)

                    total_summary["portfolios_processed"] += 1
                    total_summary["total_stocks_updated"] += summary["market_data_updated"]
                    total_summary["total_recommendations"] += summary["recommendations_generated"]
                    total_summary["total_insights"] += summary["insights_generated"]

                    logger.info(f"✓ Processed portfolio: {portfolio.name}")

                except Exception as e:
                    total_summary["portfolios_failed"] += 1
                    logger.error(f"✗ Failed portfolio {portfolio.name}: {e}")

            total_summary["duration_seconds"] = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"Batch completed: {total_summary['portfolios_processed']} portfolios, "
                f"{total_summary['total_stocks_updated']} stocks, "
                f"{total_summary['total_recommendations']} recommendations in "
                f"{total_summary['duration_seconds']:.1f}s"
            )

            return total_summary

    def get_status(self) -> dict[str, Any]:
        """
        Get scheduler status.

        Returns:
            Dict with scheduler status info
        """
        jobs_list: list[dict[str, Any]] = []
        status: dict[str, Any] = {
            "running": self.is_running,
            "jobs": jobs_list,
        }

        if self.is_running:
            for job in self.scheduler.get_jobs():
                jobs_list.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    }
                )

        return status


# Global scheduler instance
_scheduler: Optional[PortfolioScheduler] = None


def get_scheduler() -> PortfolioScheduler:
    """Get global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = PortfolioScheduler()
    return _scheduler
