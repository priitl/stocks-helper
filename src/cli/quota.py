"""Quota management commands."""

import click
from rich.console import Console
from rich.table import Table

from src.lib.quota_tracker import QuotaTracker

console = Console()


@click.group()  # type: ignore[misc]
def quota() -> None:
    """Manage API quotas."""
    pass


@quota.command("status")  # type: ignore[misc]
def quota_status() -> None:
    """Show current API quota status."""
    # Alpha Vantage quota
    av_tracker = QuotaTracker(api_name="alpha_vantage", daily_limit=25, per_minute_limit=5)
    av_quota = av_tracker.get_remaining_quota()

    table = Table(title="API Quota Status", show_header=True, header_style="bold cyan")
    table.add_column("API", style="cyan")
    table.add_column("Period", style="magenta")
    table.add_column("Used", style="yellow")
    table.add_column("Limit", style="green")
    table.add_column("Remaining", style="blue")
    table.add_column("Status", style="bold")

    # Daily quota row
    daily_pct = (av_quota["daily_used"] / av_quota["daily_limit"]) * 100
    daily_status = "🟢 OK" if daily_pct < 80 else "🟡 Warning" if daily_pct < 100 else "🔴 Exceeded"

    table.add_row(
        "Alpha Vantage",
        "Daily",
        str(av_quota["daily_used"]),
        str(av_quota["daily_limit"]),
        str(av_quota["daily_remaining"]),
        daily_status,
    )

    # Per-minute quota row (if available)
    if "per_minute_used" in av_quota:
        minute_pct = (av_quota["per_minute_used"] / av_quota["per_minute_limit"]) * 100
        minute_status = (
            "🟢 OK" if minute_pct < 80 else "🟡 Warning" if minute_pct < 100 else "🔴 Exceeded"
        )

        table.add_row(
            "",
            "Per Minute",
            str(av_quota["per_minute_used"]),
            str(av_quota["per_minute_limit"]),
            str(av_quota["per_minute_remaining"]),
            minute_status,
        )

    console.print(table)
    console.print(f"\n📅 Date: {av_quota['date']}")


@quota.command("reset")  # type: ignore[misc]
@click.option("--api", type=str, help="API name to reset (default: all)")  # type: ignore[misc]
def quota_reset(api: str | None) -> None:
    """Reset API quota counters."""
    if api and api.lower() == "alpha_vantage":
        tracker = QuotaTracker(api_name="alpha_vantage", daily_limit=25, per_minute_limit=5)
        tracker.reset()
        console.print("✅ Reset quota for Alpha Vantage", style="green")
    else:
        # Reset all
        av_tracker = QuotaTracker(api_name="alpha_vantage", daily_limit=25, per_minute_limit=5)
        av_tracker.reset()
        console.print("✅ Reset all API quotas", style="green")
