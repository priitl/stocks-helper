"""CLI entry point for stocks-helper."""

import sys
import traceback

import click
from rich.console import Console

from src.cli import (
    batch,
    holding,
    insight,
    portfolio,
    quota,
    recommendation,
    report,
    stock,
    suggestion,
)
from src.cli import init as init_cmd
from src.lib.errors import StocksHelperError, format_error_message, get_error_color

console = Console()


@click.group()  # type: ignore[misc]
@click.option("--debug", is_flag=True, help="Enable debug mode")  # type: ignore[misc]
@click.option("--config-file", type=click.Path(), help="Path to config file")  # type: ignore[misc]
@click.pass_context  # type: ignore[misc]
def main(ctx: click.Context, debug: bool, config_file: str | None) -> None:
    """Personal Stocks Tracker & Analyzer - Track investments and get insights."""
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug
    ctx.obj["CONFIG_FILE"] = config_file


def handle_exception(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: object
) -> None:
    """
    Global exception handler for CLI.

    Formats exceptions with Rich colors and provides user-friendly messages.
    """
    # Don't handle KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)  # type: ignore[arg-type]
        return

    # Format and display error
    color = get_error_color(exc_value) if isinstance(exc_value, Exception) else "red"
    message = (
        format_error_message(exc_value) if isinstance(exc_value, Exception) else str(exc_value)
    )

    console.print(f"\n[{color}]✗ Error: {message}[/{color}]\n")

    # Show traceback in debug mode
    if isinstance(exc_value, StocksHelperError):
        # For known errors, only show traceback if requested
        debug_mode = False
        try:
            if "--debug" in sys.argv:
                debug_mode = True
        except Exception:
            pass

        if debug_mode:
            console.print("[dim]Traceback:[/dim]")
            traceback.print_exception(exc_value)
    else:
        # For unknown errors, always show some context
        console.print("[dim]Unexpected error occurred. Use --debug for full traceback.[/dim]")
        if "--debug" in sys.argv:
            traceback.print_exception(exc_value)

    sys.exit(1)


# Install global exception handler
sys.excepthook = handle_exception


@main.command()  # type: ignore[misc]
def version() -> None:
    """Show version information."""
    click.echo("stocks-helper version 0.1.0")


# Register subcommands
main.add_command(portfolio.portfolio)
main.add_command(holding.holding)
main.add_command(stock.stock)
main.add_command(recommendation.recommendation)
main.add_command(suggestion.suggestion)
main.add_command(insight.insight)
main.add_command(report.report)
main.add_command(batch.batch)
main.add_command(quota.quota)
main.add_command(init_cmd.init)


if __name__ == "__main__":
    main()
