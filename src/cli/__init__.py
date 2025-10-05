"""CLI entry point for stocks-helper."""

import click


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--config-file", type=click.Path(), help="Path to config file")
@click.pass_context
def main(ctx, debug, config_file):
    """Personal Stocks Tracker & Analyzer - Track investments and get insights."""
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug
    ctx.obj["CONFIG_FILE"] = config_file


@main.command()
def version():
    """Show version information."""
    click.echo("stocks-helper version 0.1.0")


# Import and register subcommands
from src.cli import holding, portfolio, init as init_cmd

main.add_command(portfolio.portfolio)
main.add_command(holding.holding)
main.add_command(init_cmd.init)


if __name__ == "__main__":
    main()
