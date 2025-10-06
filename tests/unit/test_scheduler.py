"""Unit tests for PortfolioScheduler."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.services.scheduler import PortfolioScheduler, get_scheduler


@pytest.fixture
def scheduler():
    """Provide PortfolioScheduler instance."""
    return PortfolioScheduler()


@pytest.fixture
def mock_portfolios():
    """Provide mock portfolios."""
    portfolio1 = MagicMock()
    portfolio1.id = "portfolio-1"
    portfolio1.name = "Test Portfolio 1"

    portfolio2 = MagicMock()
    portfolio2.id = "portfolio-2"
    portfolio2.name = "Test Portfolio 2"

    return [portfolio1, portfolio2]


@pytest.mark.unit
class TestPortfolioScheduler:
    """Test suite for PortfolioScheduler."""

    def test_init(self, scheduler):
        """Scheduler initializes correctly."""
        assert scheduler.scheduler is not None
        assert scheduler.batch_processor is not None
        assert scheduler.is_running is False

    def test_start_scheduler(self, scheduler):
        """Scheduler starts successfully."""
        try:
            scheduler.start(daily_time="18:00")

            assert scheduler.is_running is True
            jobs = scheduler.scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].id == "daily_portfolio_update"
            assert jobs[0].name == "Daily Portfolio Update"

        finally:
            scheduler.stop()

    def test_start_scheduler_custom_time(self, scheduler):
        """Scheduler starts with custom time."""
        try:
            scheduler.start(daily_time="09:30")

            assert scheduler.is_running is True
            jobs = scheduler.scheduler.get_jobs()
            assert len(jobs) == 1

            # Verify job was created with correct ID
            assert jobs[0].id == "daily_portfolio_update"
            assert jobs[0].name == "Daily Portfolio Update"

        finally:
            scheduler.stop()

    def test_start_scheduler_already_running(self, scheduler):
        """Starting already running scheduler shows warning."""
        try:
            scheduler.start(daily_time="18:00")

            with patch("src.services.scheduler.logger") as mock_logger:
                scheduler.start(daily_time="18:00")
                mock_logger.warning.assert_called_with("Scheduler already running")

        finally:
            scheduler.stop()

    def test_stop_scheduler(self, scheduler):
        """Scheduler stops successfully."""
        scheduler.start(daily_time="18:00")
        assert scheduler.is_running is True

        scheduler.stop()

        assert scheduler.is_running is False
        assert len(scheduler.scheduler.get_jobs()) == 0

    def test_stop_scheduler_not_running(self, scheduler):
        """Stopping non-running scheduler does nothing."""
        assert scheduler.is_running is False

        # Should not raise
        scheduler.stop()

        assert scheduler.is_running is False

    def test_start_replaces_existing_job(self, scheduler):
        """Starting scheduler replaces existing job."""
        try:
            scheduler.start(daily_time="18:00")
            first_jobs = scheduler.scheduler.get_jobs()
            assert len(first_jobs) == 1

            # Start again with different time
            scheduler.start(daily_time="09:00")
            second_jobs = scheduler.scheduler.get_jobs()

            # Should still have only one job (replaced)
            assert len(second_jobs) == 1
            assert second_jobs[0].id == "daily_portfolio_update"

        finally:
            scheduler.stop()

    @pytest.mark.asyncio
    async def test_process_all_portfolios_success(self, scheduler, mock_portfolios):
        """All portfolios process successfully."""
        with patch("src.services.scheduler.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.all.return_value = mock_portfolios

            # Mock batch processor
            scheduler.batch_processor.process_portfolio = AsyncMock(
                return_value={
                    "market_data_updated": 5,
                    "recommendations_generated": 3,
                    "insights_generated": 2,
                }
            )

            await scheduler._process_all_portfolios()

            # Verify all portfolios were processed
            assert scheduler.batch_processor.process_portfolio.call_count == 2
            scheduler.batch_processor.process_portfolio.assert_any_call("portfolio-1")
            scheduler.batch_processor.process_portfolio.assert_any_call("portfolio-2")

    @pytest.mark.asyncio
    async def test_process_all_portfolios_one_fails(self, scheduler, mock_portfolios):
        """One portfolio fails, others continue processing."""
        with patch("src.services.scheduler.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.all.return_value = mock_portfolios

            # First portfolio fails, second succeeds
            scheduler.batch_processor.process_portfolio = AsyncMock(
                side_effect=[
                    Exception("API timeout"),
                    {
                        "market_data_updated": 3,
                        "recommendations_generated": 2,
                        "insights_generated": 1,
                    },
                ]
            )

            with patch("src.services.scheduler.logger") as mock_logger:
                await scheduler._process_all_portfolios()

                # Should log error for first portfolio
                assert mock_logger.error.called
                error_msg = str(mock_logger.error.call_args[0][0])
                assert "Test Portfolio 1" in error_msg

                # But still process second portfolio
                assert scheduler.batch_processor.process_portfolio.call_count == 2

    @pytest.mark.asyncio
    async def test_run_once_success(self, scheduler, mock_portfolios):
        """Manual batch run completes successfully."""
        with patch("src.services.scheduler.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.all.return_value = mock_portfolios

            scheduler.batch_processor.process_portfolio = AsyncMock(
                return_value={
                    "market_data_updated": 5,
                    "recommendations_generated": 3,
                    "insights_generated": 2,
                }
            )

            result = await scheduler.run_once()

            assert result["portfolios_processed"] == 2
            assert result["portfolios_failed"] == 0
            assert result["total_stocks_updated"] == 10  # 5 * 2
            assert result["total_recommendations"] == 6  # 3 * 2
            assert result["total_insights"] == 4  # 2 * 2
            assert result["duration_seconds"] > 0

    @pytest.mark.asyncio
    async def test_run_once_with_failures(self, scheduler, mock_portfolios):
        """Manual batch run handles failures correctly."""
        with patch("src.services.scheduler.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.all.return_value = mock_portfolios

            # First succeeds, second fails
            scheduler.batch_processor.process_portfolio = AsyncMock(
                side_effect=[
                    {
                        "market_data_updated": 5,
                        "recommendations_generated": 3,
                        "insights_generated": 2,
                    },
                    Exception("Network error"),
                ]
            )

            result = await scheduler.run_once()

            assert result["portfolios_processed"] == 1
            assert result["portfolios_failed"] == 1
            assert result["total_stocks_updated"] == 5
            assert result["total_recommendations"] == 3
            assert result["total_insights"] == 2

    def test_run_daily_batch_success(self, scheduler):
        """Daily batch job runs successfully."""
        with patch.object(scheduler, "_process_all_portfolios") as mock_process:
            # Create async mock that succeeds
            async def successful_process():
                return None

            mock_process.return_value = successful_process()

            with patch("src.services.scheduler.logger") as mock_logger:
                scheduler.run_daily_batch()

                # Should log start and completion
                assert any(
                    "Starting daily batch" in str(call) for call in mock_logger.info.call_args_list
                )
                assert any("completed" in str(call) for call in mock_logger.info.call_args_list)

    def test_run_daily_batch_failure(self, scheduler):
        """Daily batch job handles failures gracefully."""
        with patch.object(scheduler, "_process_all_portfolios") as mock_process:
            # Create async mock that raises exception
            async def failing_process():
                raise Exception("Database connection failed")

            mock_process.side_effect = lambda: failing_process()

            # Should not raise, just log error
            try:
                scheduler.run_daily_batch()
            except Exception:
                # If exception is raised, test fails
                pytest.fail("run_daily_batch should catch exceptions")

    def test_get_status_not_running(self, scheduler):
        """Get status when scheduler is not running."""
        status = scheduler.get_status()

        assert status["running"] is False
        assert status["jobs"] == []

    def test_get_status_running(self, scheduler):
        """Get status when scheduler is running."""
        try:
            scheduler.start(daily_time="18:00")

            status = scheduler.get_status()

            assert status["running"] is True
            assert len(status["jobs"]) == 1
            assert status["jobs"][0]["id"] == "daily_portfolio_update"
            assert status["jobs"][0]["name"] == "Daily Portfolio Update"
            assert status["jobs"][0]["next_run"] is not None

        finally:
            scheduler.stop()

    @freeze_time("2025-10-06 12:00:00")
    def test_next_run_time_calculation(self, scheduler):
        """Next run time is calculated correctly."""
        try:
            # Schedule for 18:00
            scheduler.start(daily_time="18:00")

            status = scheduler.get_status()
            next_run_str = status["jobs"][0]["next_run"]
            next_run = datetime.fromisoformat(next_run_str)

            # Should be today at 18:00
            assert next_run.hour == 18
            assert next_run.minute == 0

        finally:
            scheduler.stop()

    def test_max_instances_prevents_concurrent_runs(self, scheduler):
        """Job configured to prevent concurrent runs."""
        try:
            scheduler.start(daily_time="18:00")

            jobs = scheduler.scheduler.get_jobs()
            job = jobs[0]

            # Should have max_instances=1
            assert job.max_instances == 1

        finally:
            scheduler.stop()


@pytest.mark.unit
class TestGetScheduler:
    """Test global scheduler instance."""

    def test_get_scheduler_singleton(self):
        """get_scheduler returns singleton instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2

    def test_get_scheduler_returns_portfolio_scheduler(self):
        """get_scheduler returns PortfolioScheduler instance."""
        scheduler = get_scheduler()

        assert isinstance(scheduler, PortfolioScheduler)
