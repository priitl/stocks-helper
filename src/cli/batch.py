"""Batch processing CLI commands."""

import asyncio
import signal
import sys

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table

from src.services.scheduler import get_scheduler

console = Console()


@click.group()
def batch():
    """Batch processing and scheduled updates."""
    pass


@batch.command("run-once")
def run_once():
    """Run batch update once for all portfolios (manual trigger)."""
    console.print("[cyan]Starting batch update for all portfolios...[/cyan]")

    scheduler = get_scheduler()

    try:
        summary = asyncio.run(scheduler.run_once())

        console.print("\n[green]✓ Batch update completed![/green]\n")

        # Display summary
        table = Table(title="Batch Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="green")

        table.add_row("Portfolios Processed", str(summary["portfolios_processed"]))
        table.add_row("Portfolios Failed", str(summary["portfolios_failed"]))
        table.add_row("Stocks Updated", str(summary["total_stocks_updated"]))
        table.add_row("Recommendations Generated", str(summary["total_recommendations"]))
        table.add_row("Insights Generated", str(summary["total_insights"]))
        table.add_row("Duration (seconds)", f"{summary['duration_seconds']:.1f}")

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ Batch update failed: {e}[/red]")
        sys.exit(1)


@batch.command("start")
@click.option("--time", default="18:00", help="Daily run time (HH:MM, default: 18:00)")
def start_daemon(time: str):
    """
    Start batch scheduler daemon.

    Runs daily batch updates at specified time.
    Press Ctrl+C to stop.
    """
    console.print(f"[cyan]Starting batch scheduler (daily at {time})...[/cyan]")

    scheduler = get_scheduler()

    try:
        scheduler.start(daily_time=time)
        console.print("[green]✓ Scheduler started![/green]")
        console.print(f"[yellow]Daily batch will run at {time}[/yellow]")
        console.print("[dim]Press Ctrl+C to stop...[/dim]\n")

        # Display status table
        def generate_table():
            """Generate live status table."""
            status = scheduler.get_status()

            table = Table(title="Scheduler Status")
            table.add_column("Job", style="cyan")
            table.add_column("Next Run", style="green")

            if status["jobs"]:
                for job in status["jobs"]:
                    next_run = job.get("next_run", "N/A")
                    if next_run and next_run != "N/A":
                        # Format datetime nicely
                        from datetime import datetime

                        dt = datetime.fromisoformat(next_run)
                        next_run = dt.strftime("%Y-%m-%d %H:%M:%S")

                    table.add_row(job.get("name", job["id"]), next_run)
            else:
                table.add_row("No jobs scheduled", "")

            return table

        # Keep running and update status every 60 seconds
        with Live(generate_table(), refresh_per_second=0.1, console=console) as live:

            def signal_handler(sig, frame):
                """Handle Ctrl+C gracefully."""
                console.print("\n[yellow]Stopping scheduler...[/yellow]")
                scheduler.stop()
                console.print("[green]✓ Scheduler stopped[/green]")
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)

            while True:
                time.sleep(60)  # Update table every 60 seconds
                live.update(generate_table())

    except Exception as e:
        console.print(f"[red]✗ Scheduler failed: {e}[/red]")
        scheduler.stop()
        sys.exit(1)


@batch.command("status")
def status():
    """Show batch scheduler status."""
    scheduler = get_scheduler()
    status = scheduler.get_status()

    if not status["running"]:
        console.print("[yellow]Scheduler is not running[/yellow]")
        console.print("\nStart with: [cyan]stocks-helper batch start[/cyan]")
        return

    console.print("[green]✓ Scheduler is running[/green]\n")

    if status["jobs"]:
        table = Table(title="Scheduled Jobs")
        table.add_column("Job ID", style="cyan")
        table.add_column("Name", style="blue")
        table.add_column("Next Run", style="green")

        for job in status["jobs"]:
            next_run = job.get("next_run", "N/A")
            if next_run and next_run != "N/A":
                from datetime import datetime

                dt = datetime.fromisoformat(next_run)
                next_run = dt.strftime("%Y-%m-%d %H:%M:%S")

            table.add_row(job["id"], job.get("name", ""), next_run)

        console.print(table)
    else:
        console.print("[yellow]No jobs scheduled[/yellow]")


@batch.command("stop")
def stop():
    """Stop batch scheduler daemon."""
    scheduler = get_scheduler()

    if not scheduler.is_running:
        console.print("[yellow]Scheduler is not running[/yellow]")
        return

    console.print("[cyan]Stopping scheduler...[/cyan]")
    scheduler.stop()
    console.print("[green]✓ Scheduler stopped[/green]")
