"""Report generation CLI commands."""

import asyncio
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import click
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from rich.console import Console
from rich.table import Table

from src.lib.db import get_session
from src.models.holding import Holding
from src.models.insight import Insight, InsightType
from src.models.market_data import MarketData
from src.models.portfolio import Portfolio
from src.models.recommendation import RecommendationType, StockRecommendation
from src.models.stock import Stock
from src.services.insight_generator import InsightGenerator

console = Console()


@click.group()
def report():
    """Generate portfolio reports and visualizations."""
    pass


@report.command("portfolio")
@click.argument("portfolio_id")
@click.option("--output", "-o", help="Output file path (default: reports/portfolio_<id>.html)")
@click.option("--open", "-b", is_flag=True, help="Open report in browser after generation")
def portfolio_report(portfolio_id: str, output: Optional[str], open: bool):
    """
    Generate comprehensive HTML portfolio report.

    Includes:
    - Performance charts
    - Sector and geographic allocation
    - Holdings table
    - Recommendations summary
    - Portfolio insights
    """
    session = get_session()

    try:
        # Get portfolio
        portfolio_obj = session.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio_obj:
            console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
            return

        # Get holdings
        holdings = (
            session.query(Holding)
            .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
            .all()
        )

        if not holdings:
            console.print("[yellow]Portfolio has no holdings[/yellow]")
            return

        # Generate insights if not present
        console.print("[cyan]Generating fresh insights...[/cyan]")
        generator = InsightGenerator()
        generator.generate_all_insights(portfolio_id)

        # Get latest insights
        insights = (
            session.query(Insight)
            .filter(Insight.portfolio_id == portfolio_id)
            .order_by(Insight.timestamp.desc())
            .all()
        )

        # Get recommendations
        recommendations = (
            session.query(StockRecommendation)
            .filter(StockRecommendation.portfolio_id == portfolio_id)
            .order_by(StockRecommendation.timestamp.desc())
            .all()
        )

        # Build HTML report
        html = _build_portfolio_html(
            portfolio_obj, holdings, insights, recommendations, session
        )

        # Save to file
        if not output:
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)
            output = str(reports_dir / f"portfolio_{portfolio_id[:8]}.html")

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

        console.print(f"[green]✓ Report generated: {output}[/green]")

        # Open in browser
        if open:
            webbrowser.open(f"file://{output_path.absolute()}")
            console.print("[cyan]Opening report in browser...[/cyan]")

    finally:
        session.close()


@report.command("performance")
@click.argument("portfolio_id")
@click.option("--period", type=click.Choice(["30d", "90d", "1y", "all"]), default="90d")
@click.option("--output", "-o", help="Output file path")
@click.option("--open", "-b", is_flag=True, help="Open chart in browser")
def performance_chart(portfolio_id: str, period: str, output: Optional[str], open: bool):
    """Generate performance chart for portfolio over time."""
    session = get_session()

    try:
        portfolio_obj = session.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio_obj:
            console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
            return

        # Calculate period start date
        period_days = {
            "30d": 30,
            "90d": 90,
            "1y": 365,
            "all": 3650,  # 10 years
        }
        start_date = datetime.now() - timedelta(days=period_days[period])

        # Get historical market data for all holdings
        holdings = (
            session.query(Holding)
            .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
            .all()
        )

        if not holdings:
            console.print("[yellow]Portfolio has no holdings[/yellow]")
            return

        # Build performance chart
        fig = _build_performance_chart(holdings, start_date, session)

        # Save to file
        if not output:
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)
            output = str(reports_dir / f"performance_{portfolio_id[:8]}_{period}.html")

        fig.write_html(output)
        console.print(f"[green]✓ Performance chart saved: {output}[/green]")

        if open:
            webbrowser.open(f"file://{Path(output).absolute()}")

    finally:
        session.close()


@report.command("allocation")
@click.argument("portfolio_id")
def allocation_breakdown(portfolio_id: str):
    """Display portfolio allocation breakdown (sector and geographic)."""
    session = get_session()

    try:
        # Get sector allocation insight
        sector_insight = (
            session.query(Insight)
            .filter(
                Insight.portfolio_id == portfolio_id,
                Insight.insight_type == InsightType.SECTOR_ALLOCATION,
            )
            .order_by(Insight.timestamp.desc())
            .first()
        )

        # Get geo allocation insight
        geo_insight = (
            session.query(Insight)
            .filter(
                Insight.portfolio_id == portfolio_id,
                Insight.insight_type == InsightType.GEO_ALLOCATION,
            )
            .order_by(Insight.timestamp.desc())
            .first()
        )

        if not sector_insight and not geo_insight:
            console.print("[yellow]No allocation data available. Run: stocks-helper insight generate <portfolio_id>[/yellow]")
            return

        # Display sector allocation
        if sector_insight:
            console.print("\n[bold cyan]Sector Allocation[/bold cyan]")
            table = Table()
            table.add_column("Sector", style="cyan")
            table.add_column("Percentage", justify="right", style="green")

            allocation = sector_insight.data.get("allocation", {})
            for sector, pct in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
                table.add_row(sector, f"{pct:.1f}%")

            console.print(table)

            if sector_insight.data.get("concentration_risk"):
                concentrated = sector_insight.data.get("concentrated_sector")
                pct = allocation.get(concentrated, 0)
                console.print(f"\n[yellow]⚠️  High concentration in {concentrated} ({pct:.1f}%)[/yellow]")

        # Display geographic allocation
        if geo_insight:
            console.print("\n[bold cyan]Geographic Allocation[/bold cyan]")
            table = Table()
            table.add_column("Country/Region", style="cyan")
            table.add_column("Percentage", justify="right", style="green")

            allocation = geo_insight.data.get("allocation", {})
            for country, pct in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
                table.add_row(country, f"{pct:.1f}%")

            console.print(table)

    finally:
        session.close()


def _build_portfolio_html(
    portfolio: Portfolio,
    holdings: list[Holding],
    insights: list[Insight],
    recommendations: list[StockRecommendation],
    session,
) -> str:
    """Build comprehensive portfolio HTML report."""

    # Calculate portfolio value
    total_value = 0
    total_cost = 0
    holdings_data = []

    for holding in holdings:
        market_data = (
            session.query(MarketData)
            .filter(MarketData.ticker == holding.ticker, MarketData.is_latest == True)
            .first()
        )

        current_price = market_data.price if market_data else holding.avg_purchase_price
        value = holding.quantity * current_price
        cost = holding.quantity * holding.avg_purchase_price
        gain_loss = value - cost
        gain_loss_pct = (gain_loss / cost * 100) if cost > 0 else 0

        total_value += value
        total_cost += cost

        holdings_data.append({
            "ticker": holding.ticker,
            "quantity": holding.quantity,
            "avg_price": holding.avg_purchase_price,
            "current_price": current_price,
            "value": value,
            "gain_loss": gain_loss,
            "gain_loss_pct": gain_loss_pct,
        })

    total_gain_loss = total_value - total_cost
    total_gain_loss_pct = (total_gain_loss / total_cost * 100) if total_cost > 0 else 0

    # Build charts
    charts_html = ""

    # Sector allocation pie chart
    sector_insight = next(
        (i for i in insights if i.insight_type == InsightType.SECTOR_ALLOCATION), None
    )
    if sector_insight:
        allocation = sector_insight.data.get("allocation", {})
        fig_sector = go.Figure(data=[go.Pie(
            labels=list(allocation.keys()),
            values=list(allocation.values()),
            hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
        )])
        fig_sector.update_layout(
            title="Sector Allocation",
            height=400,
        )
        charts_html += f'<div class="chart">{fig_sector.to_html(full_html=False, include_plotlyjs="cdn")}</div>'

    # Geographic allocation pie chart
    geo_insight = next(
        (i for i in insights if i.insight_type == InsightType.GEO_ALLOCATION), None
    )
    if geo_insight:
        allocation = geo_insight.data.get("allocation", {})
        fig_geo = go.Figure(data=[go.Pie(
            labels=list(allocation.keys()),
            values=list(allocation.values()),
            hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
        )])
        fig_geo.update_layout(
            title="Geographic Allocation",
            height=400,
        )
        charts_html += f'<div class="chart">{fig_geo.to_html(full_html=False, include_plotlyjs="cdn")}</div>'

    # Holdings table
    holdings_html = '<table class="holdings-table">'
    holdings_html += "<thead><tr><th>Ticker</th><th>Quantity</th><th>Avg Price</th><th>Current Price</th><th>Value</th><th>Gain/Loss</th><th>%</th></tr></thead>"
    holdings_html += "<tbody>"

    for h in sorted(holdings_data, key=lambda x: x["value"], reverse=True):
        gain_loss_class = "positive" if h["gain_loss"] >= 0 else "negative"
        holdings_html += f"""
        <tr>
            <td><strong>{h['ticker']}</strong></td>
            <td>{h['quantity']:.2f}</td>
            <td>${h['avg_price']:.2f}</td>
            <td>${h['current_price']:.2f}</td>
            <td>${h['value']:.2f}</td>
            <td class="{gain_loss_class}">${h['gain_loss']:.2f}</td>
            <td class="{gain_loss_class}">{h['gain_loss_pct']:+.1f}%</td>
        </tr>
        """

    holdings_html += "</tbody></table>"

    # Recommendations summary
    recommendations_html = ""
    if recommendations:
        buy_count = sum(1 for r in recommendations if r.recommendation == RecommendationType.BUY)
        sell_count = sum(1 for r in recommendations if r.recommendation == RecommendationType.SELL)
        hold_count = sum(1 for r in recommendations if r.recommendation == RecommendationType.HOLD)

        recommendations_html = f"""
        <div class="recommendations-summary">
            <h3>Recommendations</h3>
            <div class="rec-counts">
                <div class="rec-item buy">
                    <div class="rec-label">BUY</div>
                    <div class="rec-count">{buy_count}</div>
                </div>
                <div class="rec-item hold">
                    <div class="rec-label">HOLD</div>
                    <div class="rec-count">{hold_count}</div>
                </div>
                <div class="rec-item sell">
                    <div class="rec-label">SELL</div>
                    <div class="rec-count">{sell_count}</div>
                </div>
            </div>
        </div>
        """

    # Insights summary
    insights_html = "<div class='insights-summary'><h3>Key Insights</h3><ul>"
    for insight in insights[:5]:  # Top 5 insights
        insights_html += f"<li><strong>{insight.insight_type.value}:</strong> {insight.summary}</li>"
    insights_html += "</ul></div>"

    # Build final HTML
    total_gain_loss_class = "positive" if total_gain_loss >= 0 else "negative"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Portfolio Report - {portfolio.name}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin-bottom: 10px;
            }}
            .summary {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .summary-row {{
                display: flex;
                justify-content: space-between;
                margin: 10px 0;
                font-size: 18px;
            }}
            .positive {{ color: #28a745; }}
            .negative {{ color: #dc3545; }}
            .chart {{
                margin: 30px 0;
            }}
            .holdings-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 30px 0;
            }}
            .holdings-table th {{
                background: #007bff;
                color: white;
                padding: 12px;
                text-align: left;
            }}
            .holdings-table td {{
                padding: 10px 12px;
                border-bottom: 1px solid #ddd;
            }}
            .holdings-table tr:hover {{
                background: #f8f9fa;
            }}
            .recommendations-summary {{
                margin: 30px 0;
            }}
            .rec-counts {{
                display: flex;
                gap: 20px;
                margin-top: 15px;
            }}
            .rec-item {{
                flex: 1;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
            }}
            .rec-item.buy {{ background: #d4edda; border: 2px solid #28a745; }}
            .rec-item.hold {{ background: #fff3cd; border: 2px solid #ffc107; }}
            .rec-item.sell {{ background: #f8d7da; border: 2px solid #dc3545; }}
            .rec-label {{ font-weight: bold; font-size: 14px; }}
            .rec-count {{ font-size: 36px; font-weight: bold; margin-top: 10px; }}
            .insights-summary {{
                margin: 30px 0;
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
            }}
            .insights-summary ul {{
                list-style: none;
                padding: 0;
            }}
            .insights-summary li {{
                margin: 10px 0;
                padding: 10px;
                background: white;
                border-radius: 4px;
            }}
            .timestamp {{
                color: #6c757d;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{portfolio.name}</h1>
            <div class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>

            <div class="summary">
                <div class="summary-row">
                    <span><strong>Total Value:</strong></span>
                    <span>${total_value:,.2f}</span>
                </div>
                <div class="summary-row">
                    <span><strong>Total Cost:</strong></span>
                    <span>${total_cost:,.2f}</span>
                </div>
                <div class="summary-row">
                    <span><strong>Total Gain/Loss:</strong></span>
                    <span class="{total_gain_loss_class}">${total_gain_loss:,.2f} ({total_gain_loss_pct:+.1f}%)</span>
                </div>
                <div class="summary-row">
                    <span><strong>Base Currency:</strong></span>
                    <span>{portfolio.base_currency}</span>
                </div>
                <div class="summary-row">
                    <span><strong>Holdings Count:</strong></span>
                    <span>{len(holdings)}</span>
                </div>
            </div>

            {charts_html}

            <h2>Holdings</h2>
            {holdings_html}

            {recommendations_html}

            {insights_html}
        </div>
    </body>
    </html>
    """

    return html


def _build_performance_chart(holdings: list[Holding], start_date: datetime, session) -> go.Figure:
    """Build performance line chart."""

    # Get historical market data for each holding
    dates = []
    portfolio_values = {}

    for holding in holdings:
        market_data_history = (
            session.query(MarketData)
            .filter(
                MarketData.ticker == holding.ticker,
                MarketData.timestamp >= start_date,
            )
            .order_by(MarketData.timestamp)
            .all()
        )

        for md in market_data_history:
            date_str = md.timestamp.strftime("%Y-%m-%d")
            if date_str not in dates:
                dates.append(date_str)

            value = holding.quantity * md.price
            portfolio_values[date_str] = portfolio_values.get(date_str, 0) + value

    # Sort dates
    dates = sorted(dates)
    values = [portfolio_values.get(d, 0) for d in dates]

    # Create line chart
    fig = go.Figure()

    if dates and values:
        fig.add_trace(go.Scatter(
            x=dates,
            y=values,
            mode="lines+markers",
            name="Portfolio Value",
            line=dict(color="#007bff", width=2),
            hovertemplate="Date: %{x}<br>Value: $%{y:,.2f}<extra></extra>",
        ))
    else:
        # No historical data - show placeholder
        fig.add_annotation(
            text="No historical data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=20, color="gray"),
        )

    fig.update_layout(
        title="Portfolio Performance Over Time",
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified",
        height=500,
    )

    return fig
