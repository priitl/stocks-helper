"""CLI commands for portfolio insights."""

import click
from rich.console import Console
from rich.table import Table

from src.lib.db import get_session
from src.models.insight import Insight, InsightType
from src.services.insight_generator import InsightGenerator

console = Console()


@click.group()
def insight():
    """View portfolio insights and analytics."""
    pass


@insight.command("show")
@click.argument("portfolio_id")
def show_insights(portfolio_id):
    """Show all insights for a portfolio."""
    session = get_session()
    try:
        # Get latest insights of each type
        insights = {}

        for insight_type in InsightType:
            latest = (
                session.query(Insight)
                .filter(
                    Insight.portfolio_id == portfolio_id,
                    Insight.insight_type == insight_type,
                )
                .order_by(Insight.timestamp.desc())
                .first()
            )

            if latest:
                insights[insight_type] = latest

        if not insights:
            console.print("[yellow]No insights found. Run batch processor or 'insight generate' to create insights.[/yellow]")
            return

        console.print(f"\n[bold]Portfolio Insights[/bold]\n")

        # Sector Allocation
        if InsightType.SECTOR_ALLOCATION in insights:
            sector_insight = insights[InsightType.SECTOR_ALLOCATION]
            console.print("[bold cyan]📊 Sector Allocation[/bold cyan]")
            console.print(f"Updated: {sector_insight.timestamp.strftime('%Y-%m-%d %H:%M')}")

            allocation = sector_insight.data.get("allocation", {})

            if allocation:
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Sector")
                table.add_column("Allocation", justify="right")
                table.add_column("Bar")

                for sector, pct in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
                    bar_length = int(pct / 2)  # Scale to fit
                    bar = "█" * bar_length

                    # Color coding
                    if pct > 40:
                        color = "red"
                    elif pct > 25:
                        color = "yellow"
                    else:
                        color = "green"

                    table.add_row(
                        sector,
                        f"[{color}]{pct:.1f}%[/{color}]",
                        f"[{color}]{bar}[/{color}]"
                    )

                console.print(table)

                if sector_insight.data.get("concentration_risk"):
                    console.print(f"[red]⚠️  High concentration in {sector_insight.data['concentrated_sector']}[/red]")

            console.print()

        # Geographic Allocation
        if InsightType.GEO_ALLOCATION in insights:
            geo_insight = insights[InsightType.GEO_ALLOCATION]
            console.print("[bold green]🌍 Geographic Distribution[/bold green]")
            console.print(f"Updated: {geo_insight.timestamp.strftime('%Y-%m-%d %H:%M')}")

            allocation = geo_insight.data.get("allocation", {})

            if allocation:
                table = Table(show_header=True, header_style="bold green")
                table.add_column("Country/Region")
                table.add_column("Allocation", justify="right")

                for country, pct in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
                    table.add_row(country, f"{pct:.1f}%")

                console.print(table)

            console.print()

        # Diversification Gaps
        if InsightType.DIVERSIFICATION_GAP in insights:
            gap_insight = insights[InsightType.DIVERSIFICATION_GAP]
            console.print("[bold yellow]🎯 Diversification Gaps[/bold yellow]")
            console.print(f"Updated: {gap_insight.timestamp.strftime('%Y-%m-%d %H:%M')}")

            sector_gaps = gap_insight.data.get("sector_gaps", [])
            geo_gaps = gap_insight.data.get("geo_gaps", [])

            if sector_gaps:
                console.print("\nUnderrepresented Sectors:")
                for gap in sector_gaps:
                    console.print(f"  • {gap['sector']}: {gap['percentage']:.1f}%")

            if geo_gaps:
                console.print("\nUnderrepresented Regions:")
                for gap in geo_gaps:
                    console.print(f"  • {gap['country']}: {gap['percentage']:.1f}%")

            if not sector_gaps and not geo_gaps:
                console.print("[green]✓ Portfolio is well-diversified[/green]")

            console.print()

        # High Performers
        if InsightType.HIGH_PERFORMERS in insights:
            perf_insight = insights[InsightType.HIGH_PERFORMERS]
            console.print("[bold magenta]⭐ Top Performers[/bold magenta]")
            console.print(f"Updated: {perf_insight.timestamp.strftime('%Y-%m-%d %H:%M')}")

            top_performers = perf_insight.data.get("top_performers", [])

            if top_performers:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Rank")
                table.add_column("Ticker")
                table.add_column("Gain/Loss", justify="right")
                table.add_column("Current Value", justify="right")

                for i, perf in enumerate(top_performers, 1):
                    gain_loss = perf["gain_loss_pct"]
                    color = "green" if gain_loss >= 0 else "red"

                    table.add_row(
                        f"#{i}",
                        perf["ticker"],
                        f"[{color}]{gain_loss:+.1f}%[/{color}]",
                        f"${perf['current_value']:,.2f}"
                    )

                console.print(table)

            console.print()

        # Risk Assessment
        if InsightType.RISK_ASSESSMENT in insights:
            risk_insight = insights[InsightType.RISK_ASSESSMENT]
            console.print("[bold red]⚠️  Risk Assessment[/bold red]")
            console.print(f"Updated: {risk_insight.timestamp.strftime('%Y-%m-%d %H:%M')}")

            portfolio_value = risk_insight.data.get("portfolio_value", 0)
            console.print(f"Portfolio Value: ${portfolio_value:,.2f}")

            volatility = risk_insight.data.get("volatility")
            sharpe = risk_insight.data.get("sharpe_ratio")
            beta = risk_insight.data.get("beta")

            if volatility:
                console.print(f"Volatility: {volatility:.2%}")
            if sharpe:
                console.print(f"Sharpe Ratio: {sharpe:.2f}")
            if beta:
                console.print(f"Beta: {beta:.2f}")

            if not volatility and not sharpe and not beta:
                console.print("[yellow]ℹ️  Risk metrics require historical data[/yellow]")

            console.print()

    finally:
        session.close()


@insight.command("generate")
@click.argument("portfolio_id")
def generate_insights(portfolio_id):
    """Generate fresh insights for a portfolio."""
    console.print(f"[bold]Generating insights...[/bold]\n")

    generator = InsightGenerator()
    insights = generator.generate_all_insights(portfolio_id)

    if insights:
        console.print(f"[green]✓ Generated {len(insights)} insights![/green]")

        types_generated = [i.insight_type.value for i in insights]
        for insight_type in types_generated:
            console.print(f"  • {insight_type}")

        console.print(f"\nRun 'stocks-helper insight show {portfolio_id}' to view them.\n")
    else:
        console.print("[yellow]No insights generated. Check if portfolio has holdings.[/yellow]\n")


if __name__ == "__main__":
    insight()
