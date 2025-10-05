"""CLI commands for stock recommendations."""

import asyncio

import click
from rich.console import Console
from rich.table import Table

from src.lib.db import get_session
from src.models.recommendation import RecommendationType, StockRecommendation
from src.services.batch_processor import BatchProcessor
from src.services.recommendation_engine import RecommendationEngine

console = Console()


@click.group()
def recommendation():
    """Manage stock recommendations (buy/sell/hold)."""
    pass


@recommendation.command("list")
@click.argument("portfolio_id")
@click.option("--action", type=click.Choice(["BUY", "SELL", "HOLD"]), help="Filter by recommendation action")
def list_recommendations(portfolio_id, action):
    """List recommendations for a portfolio."""
    session = get_session()
    try:
        # Query recommendations
        query = session.query(StockRecommendation).filter(
            StockRecommendation.portfolio_id == portfolio_id
        )

        if action:
            query = query.filter(StockRecommendation.recommendation == RecommendationType[action])

        recommendations = query.order_by(StockRecommendation.timestamp.desc()).all()

        if not recommendations:
            console.print("[yellow]No recommendations found.[/yellow]")
            return

        # Group by recommendation type
        buy_recs = [r for r in recommendations if r.recommendation == RecommendationType.BUY]
        sell_recs = [r for r in recommendations if r.recommendation == RecommendationType.SELL]
        hold_recs = [r for r in recommendations if r.recommendation == RecommendationType.HOLD]

        # Display BUY recommendations
        if buy_recs and (not action or action == "BUY"):
            console.print("\n[bold green]🚀 BUY Recommendations[/bold green]")
            table = Table(show_header=True, header_style="bold green")
            table.add_column("Ticker")
            table.add_column("Confidence")
            table.add_column("Technical")
            table.add_column("Fundamental")
            table.add_column("Combined")
            table.add_column("Updated")

            for rec in buy_recs:
                table.add_row(
                    rec.ticker,
                    rec.confidence.value,
                    f"{rec.technical_score}/100",
                    f"{rec.fundamental_score}/100",
                    f"[bold]{rec.combined_score}/100[/bold]",
                    rec.timestamp.strftime("%Y-%m-%d %H:%M"),
                )

            console.print(table)

        # Display SELL recommendations
        if sell_recs and (not action or action == "SELL"):
            console.print("\n[bold red]📉 SELL Recommendations[/bold red]")
            table = Table(show_header=True, header_style="bold red")
            table.add_column("Ticker")
            table.add_column("Confidence")
            table.add_column("Technical")
            table.add_column("Fundamental")
            table.add_column("Combined")
            table.add_column("Updated")

            for rec in sell_recs:
                table.add_row(
                    rec.ticker,
                    rec.confidence.value,
                    f"{rec.technical_score}/100",
                    f"{rec.fundamental_score}/100",
                    f"[bold]{rec.combined_score}/100[/bold]",
                    rec.timestamp.strftime("%Y-%m-%d %H:%M"),
                )

            console.print(table)

        # Display HOLD recommendations
        if hold_recs and (not action or action == "HOLD"):
            console.print("\n[bold yellow]⏸️  HOLD Recommendations[/bold yellow]")
            table = Table(show_header=True, header_style="bold yellow")
            table.add_column("Ticker")
            table.add_column("Confidence")
            table.add_column("Technical")
            table.add_column("Fundamental")
            table.add_column("Combined")
            table.add_column("Updated")

            for rec in hold_recs:
                table.add_row(
                    rec.ticker,
                    rec.confidence.value,
                    f"{rec.technical_score}/100",
                    f"{rec.fundamental_score}/100",
                    f"[bold]{rec.combined_score}/100[/bold]",
                    rec.timestamp.strftime("%Y-%m-%d %H:%M"),
                )

            console.print(table)

        console.print()

    finally:
        session.close()


@recommendation.command("show")
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
def show_recommendation(portfolio_id, ticker):
    """Show detailed recommendation for a specific stock."""
    session = get_session()
    try:
        rec = (
            session.query(StockRecommendation)
            .filter(
                StockRecommendation.portfolio_id == portfolio_id,
                StockRecommendation.ticker == ticker.upper(),
            )
            .order_by(StockRecommendation.timestamp.desc())
            .first()
        )

        if not rec:
            console.print(f"[red]No recommendation found for {ticker}[/red]")
            return

        # Header
        console.print(f"\n[bold]Recommendation for {rec.ticker}[/bold]")
        console.print(f"Updated: {rec.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Recommendation
        if rec.recommendation == RecommendationType.BUY:
            color = "green"
            icon = "🚀"
        elif rec.recommendation == RecommendationType.SELL:
            color = "red"
            icon = "📉"
        else:
            color = "yellow"
            icon = "⏸️"

        console.print(f"[bold {color}]{icon} {rec.recommendation.value}[/bold {color}]")
        console.print(f"Confidence: {rec.confidence.value}")
        console.print()

        # Scores
        console.print("[bold]Scores:[/bold]")
        console.print(f"  Technical:    {rec.technical_score}/100")
        console.print(f"  Fundamental:  {rec.fundamental_score}/100")
        console.print(f"  [bold]Combined:     {rec.combined_score}/100[/bold]")
        console.print()

        # Technical Signals
        console.print("[bold cyan]Technical Signals:[/bold cyan]")
        for signal in rec.technical_signals:
            console.print(f"  • {signal}")
        console.print()

        # Fundamental Signals
        console.print("[bold magenta]Fundamental Signals:[/bold magenta]")
        for signal in rec.fundamental_signals:
            console.print(f"  • {signal}")
        console.print()

        # Rationale
        console.print("[bold]Rationale:[/bold]")
        console.print(rec.rationale)
        console.print()

    finally:
        session.close()


@recommendation.command("refresh")
@click.argument("portfolio_id")
@click.option("--ticker", help="Refresh specific ticker only")
def refresh_recommendations(portfolio_id, ticker):
    """Refresh recommendations by fetching latest data."""

    async def refresh():
        if ticker:
            # Refresh single ticker
            console.print(f"[bold]Refreshing recommendation for {ticker}...[/bold]\n")

            engine = RecommendationEngine()
            rec = await engine.generate_recommendation(ticker.upper(), portfolio_id)

            if rec:
                console.print(f"[green]✓ {ticker}: {rec.recommendation.value} (confidence: {rec.confidence.value})[/green]")
                console.print(f"  Combined score: {rec.combined_score}/100\n")
            else:
                console.print(f"[red]✗ Failed to generate recommendation for {ticker}[/red]\n")
        else:
            # Refresh entire portfolio
            console.print(f"[bold]Refreshing all recommendations...[/bold]\n")

            processor = BatchProcessor()
            summary = await processor.process_portfolio(portfolio_id)

            if "error" in summary:
                console.print(f"[red]Error: {summary['error']}[/red]")
            else:
                console.print(f"[green]✓ Refresh complete![/green]")
                console.print(f"  Recommendations generated: {summary.get('recommendations_generated', 0)}")
                console.print(f"  Insights generated: {summary.get('insights_generated', 0)}\n")

    asyncio.run(refresh())


if __name__ == "__main__":
    recommendation()
