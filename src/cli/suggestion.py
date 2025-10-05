"""CLI commands for stock suggestions."""

import asyncio

import click
from rich.console import Console
from rich.table import Table

from src.lib.db import get_session
from src.lib.validators import validate_ticker
from src.models.suggestion import StockSuggestion, SuggestionType
from src.services.suggestion_engine import SuggestionEngine

console = Console()


@click.group()
def suggestion():
    """Discover new stock opportunities."""
    pass


@suggestion.command("list")
@click.argument("portfolio_id")
@click.option(
    "--type",
    "suggestion_type",
    type=click.Choice(["DIVERSIFICATION", "SIMILAR_TO_WINNERS", "MARKET_OPPORTUNITY"]),
    help="Filter by suggestion type",
)
@click.option("--limit", default=10, help="Maximum number of suggestions to show")
def list_suggestions(portfolio_id, suggestion_type, limit):
    """List stock suggestions for portfolio."""
    session = get_session()
    try:
        query = session.query(StockSuggestion).filter(StockSuggestion.portfolio_id == portfolio_id)

        if suggestion_type:
            query = query.filter(StockSuggestion.suggestion_type == SuggestionType[suggestion_type])

        suggestions = query.order_by(StockSuggestion.overall_score.desc()).limit(limit).all()

        if not suggestions:
            console.print(
                "[yellow]No suggestions found. "
                "Run batch processor to generate suggestions.[/yellow]"
            )
            return

        # Group by type
        diversification = [
            s for s in suggestions if s.suggestion_type == SuggestionType.DIVERSIFICATION
        ]
        similar = [s for s in suggestions if s.suggestion_type == SuggestionType.SIMILAR_TO_WINNERS]
        opportunities = [
            s for s in suggestions if s.suggestion_type == SuggestionType.MARKET_OPPORTUNITY
        ]

        # Display Diversification suggestions
        if diversification and (not suggestion_type or suggestion_type == "DIVERSIFICATION"):
            console.print("\n[bold blue]🎯 Diversification Opportunities[/bold blue]")
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Ticker")
            table.add_column("Score")
            table.add_column("Technical")
            table.add_column("Fundamental")
            table.add_column("Portfolio Fit")

            for sug in diversification:
                table.add_row(
                    sug.ticker,
                    f"[bold]{sug.overall_score}/100[/bold]",
                    f"{sug.technical_score}/100",
                    f"{sug.fundamental_score}/100",
                    (
                        sug.portfolio_fit[:40] + "..."
                        if len(sug.portfolio_fit) > 40
                        else sug.portfolio_fit
                    ),
                )

            console.print(table)

        # Display Similar-to-winners suggestions
        if similar and (not suggestion_type or suggestion_type == "SIMILAR_TO_WINNERS"):
            console.print("\n[bold green]⭐ Similar to Your Winners[/bold green]")
            table = Table(show_header=True, header_style="bold green")
            table.add_column("Ticker")
            table.add_column("Score")
            table.add_column("Technical")
            table.add_column("Fundamental")
            table.add_column("Similar To")

            for sug in similar:
                table.add_row(
                    sug.ticker,
                    f"[bold]{sug.overall_score}/100[/bold]",
                    f"{sug.technical_score}/100",
                    f"{sug.fundamental_score}/100",
                    sug.related_holding_ticker or "N/A",
                )

            console.print(table)

        # Display Market opportunities
        if opportunities and (not suggestion_type or suggestion_type == "MARKET_OPPORTUNITY"):
            console.print("\n[bold magenta]💎 Market Opportunities[/bold magenta]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Ticker")
            table.add_column("Score")
            table.add_column("Technical")
            table.add_column("Fundamental")
            table.add_column("Summary")

            for sug in opportunities:
                table.add_row(
                    sug.ticker,
                    f"[bold]{sug.overall_score}/100[/bold]",
                    f"{sug.technical_score}/100",
                    f"{sug.fundamental_score}/100",
                    (
                        sug.technical_summary[:40] + "..."
                        if len(sug.technical_summary) > 40
                        else sug.technical_summary
                    ),
                )

            console.print(table)

        console.print()

    finally:
        session.close()


@suggestion.command("show")
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
def show_suggestion(portfolio_id, ticker):
    """Show detailed suggestion for a specific stock."""
    session = get_session()
    try:
        # Validate ticker
        try:
            validated_ticker = validate_ticker(ticker)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        sug = (
            session.query(StockSuggestion)
            .filter(
                StockSuggestion.portfolio_id == portfolio_id,
                StockSuggestion.ticker == validated_ticker,
            )
            .order_by(StockSuggestion.timestamp.desc())
            .first()
        )

        if not sug:
            console.print(f"[red]No suggestion found for {validated_ticker}[/red]")
            return

        # Header
        console.print(f"\n[bold]Suggestion for {sug.ticker}[/bold]")
        console.print(f"Type: {sug.suggestion_type.value}")
        console.print(f"Updated: {sug.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Scores
        console.print("[bold]Scores:[/bold]")
        console.print(f"  Technical:    {sug.technical_score}/100")
        console.print(f"  Fundamental:  {sug.fundamental_score}/100")
        console.print(f"  [bold]Overall:      {sug.overall_score}/100[/bold]")
        console.print()

        # Technical Summary
        console.print("[bold cyan]Technical Analysis:[/bold cyan]")
        console.print(f"  {sug.technical_summary}")
        console.print()

        # Fundamental Summary
        console.print("[bold magenta]Fundamental Analysis:[/bold magenta]")
        console.print(f"  {sug.fundamental_summary}")
        console.print()

        # Portfolio Fit
        console.print("[bold green]Portfolio Fit:[/bold green]")
        console.print(f"  {sug.portfolio_fit}")
        console.print()

        # Related Holding
        if sug.related_holding_ticker:
            console.print(f"[bold]Related to:[/bold] {sug.related_holding_ticker}")
            console.print()

    finally:
        session.close()


@suggestion.command("generate")
@click.argument("portfolio_id")
@click.option(
    "--tickers",
    required=True,
    help="Comma-separated list of candidate tickers (e.g., NVDA,AMD,INTC)",
)
def generate_suggestions(portfolio_id, tickers):
    """Generate suggestions for candidate tickers."""

    async def generate():
        # Validate and normalize tickers
        candidate_list = []
        for t in tickers.split(","):
            try:
                validated_ticker = validate_ticker(t.strip())
                candidate_list.append(validated_ticker)
            except Exception as e:
                console.print(f"[yellow]Skipping invalid ticker '{t.strip()}': {e}[/yellow]")

        if not candidate_list:
            console.print("[red]No valid tickers provided.[/red]")
            return

        console.print(
            f"[bold]Generating suggestions for {len(candidate_list)} candidates...[/bold]\n"
        )

        engine = SuggestionEngine()
        suggestions = await engine.generate_all_suggestions(portfolio_id, candidate_list)

        if suggestions:
            console.print(f"[green]✓ Generated {len(suggestions)} suggestions![/green]")

            # Summary by type
            types = {}
            for sug in suggestions:
                types[sug.suggestion_type.value] = types.get(sug.suggestion_type.value, 0) + 1

            console.print("\nBy type:")
            for sug_type, count in types.items():
                console.print(f"  {sug_type}: {count}")

            console.print(f"\nRun 'stocks-helper suggestion list {portfolio_id}' to view them.\n")
        else:
            console.print(
                "[yellow]No suggestions generated. "
                "Check if candidates are valid and not already owned.[/yellow]\n"
            )

    asyncio.run(generate())


if __name__ == "__main__":
    suggestion()
