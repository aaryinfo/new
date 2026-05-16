"""
Daily Report Generator for NSE F&O Scanner
Generates comprehensive daily trading reports with market analysis
"""

from datetime import datetime, timedelta
import json
from typing import Dict, List, Any
import os


class DailyReportGenerator:
    """Generate daily trading reports with market insights"""
    
    def __init__(self, output_dir="reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_report(self, market_data: Dict, trades: List[Dict], 
                       agent_performance: Dict = None) -> Dict:
        """
        Generate comprehensive daily report
        
        Args:
            market_data: Dictionary with market indices and stock data
            trades: List of trades executed today
            agent_performance: AI agent performance metrics
            
        Returns:
            Dictionary containing the complete report
        """
        report_date = datetime.now().strftime("%Y-%m-%d")
        
        report = {
            "date": report_date,
            "generated_at": datetime.now().isoformat(),
            "market_summary": self._generate_market_summary(market_data),
            "top_performers": self._get_top_performers(market_data),
            "top_losers": self._get_top_losers(market_data),
            "sector_performance": self._analyze_sectors(market_data),
            "trading_summary": self._generate_trading_summary(trades),
            "agent_performance": agent_performance or {},
            "alerts": self._generate_alerts(market_data),
            "recommendations": self._generate_recommendations(market_data, trades)
        }
        
        # Save report to file
        self._save_report(report)
        
        return report
    
    def _generate_market_summary(self, market_data: Dict) -> Dict:
        """Generate overall market summary"""
        indices = market_data.get("indices", {})
        
        return {
            "nifty_50": {
                "value": indices.get("NIFTY", {}).get("value", 0),
                "change": indices.get("NIFTY", {}).get("change", 0),
                "change_pct": indices.get("NIFTY", {}).get("change_pct", 0)
            },
            "bank_nifty": {
                "value": indices.get("BANKNIFTY", {}).get("value", 0),
                "change": indices.get("BANKNIFTY", {}).get("change", 0),
                "change_pct": indices.get("BANKNIFTY", {}).get("change_pct", 0)
            },
            "market_sentiment": self._calculate_sentiment(market_data),
            "total_stocks_tracked": len(market_data.get("stocks", [])),
            "advancing": len([s for s in market_data.get("stocks", []) if s.get("change_pct", 0) > 0]),
            "declining": len([s for s in market_data.get("stocks", []) if s.get("change_pct", 0) < 0]),
            "unchanged": len([s for s in market_data.get("stocks", []) if s.get("change_pct", 0) == 0])
        }
    
    def _calculate_sentiment(self, market_data: Dict) -> str:
        """Calculate overall market sentiment"""
        stocks = market_data.get("stocks", [])
        if not stocks:
            return "Neutral"
        
        advancing = len([s for s in stocks if s.get("change_pct", 0) > 0])
        total = len(stocks)
        
        advance_ratio = advancing / total if total > 0 else 0.5
        
        if advance_ratio > 0.6:
            return "Bullish"
        elif advance_ratio < 0.4:
            return "Bearish"
        else:
            return "Neutral"
    
    def _get_top_performers(self, market_data: Dict, limit: int = 10) -> List[Dict]:
        """Get top performing stocks"""
        stocks = market_data.get("stocks", [])
        sorted_stocks = sorted(stocks, key=lambda x: x.get("change_pct", 0), reverse=True)
        
        return [{
            "symbol": s.get("symbol", ""),
            "name": s.get("name", ""),
            "price": s.get("price", 0),
            "change_pct": s.get("change_pct", 0),
            "volume": s.get("volume", 0),
            "sector": s.get("sector", "Others")
        } for s in sorted_stocks[:limit]]
    
    def _get_top_losers(self, market_data: Dict, limit: int = 10) -> List[Dict]:
        """Get worst performing stocks"""
        stocks = market_data.get("stocks", [])
        sorted_stocks = sorted(stocks, key=lambda x: x.get("change_pct", 0))
        
        return [{
            "symbol": s.get("symbol", ""),
            "name": s.get("name", ""),
            "price": s.get("price", 0),
            "change_pct": s.get("change_pct", 0),
            "volume": s.get("volume", 0),
            "sector": s.get("sector", "Others")
        } for s in sorted_stocks[:limit]]
    
    def _analyze_sectors(self, market_data: Dict) -> Dict:
        """Analyze sector-wise performance"""
        stocks = market_data.get("stocks", [])
        sectors = {}
        
        for stock in stocks:
            sector = stock.get("sector", "Others")
            if sector not in sectors:
                sectors[sector] = {
                    "count": 0,
                    "total_change": 0,
                    "advancing": 0,
                    "declining": 0
                }
            
            sectors[sector]["count"] += 1
            change = stock.get("change_pct", 0)
            sectors[sector]["total_change"] += change
            
            if change > 0:
                sectors[sector]["advancing"] += 1
            elif change < 0:
                sectors[sector]["declining"] += 1
        
        # Calculate average change per sector
        sector_performance = {}
        for sector, data in sectors.items():
            avg_change = data["total_change"] / data["count"] if data["count"] > 0 else 0
            sector_performance[sector] = {
                "avg_change_pct": round(avg_change, 2),
                "stocks_count": data["count"],
                "advancing": data["advancing"],
                "declining": data["declining"],
                "sentiment": "Bullish" if avg_change > 0.5 else "Bearish" if avg_change < -0.5 else "Neutral"
            }
        
        # Sort by performance
        sorted_sectors = dict(sorted(sector_performance.items(), 
                                    key=lambda x: x[1]["avg_change_pct"], 
                                    reverse=True))
        
        return sorted_sectors
    
    def _generate_trading_summary(self, trades: List[Dict]) -> Dict:
        """Generate trading activity summary"""
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "largest_win": 0,
                "largest_loss": 0
            }
        
        winning = [t for t in trades if t.get("pnl", 0) > 0]
        losing = [t for t in trades if t.get("pnl", 0) < 0]
        
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        avg_profit = sum(t.get("pnl", 0) for t in winning) / len(winning) if winning else 0
        avg_loss = sum(t.get("pnl", 0) for t in losing) / len(losing) if losing else 0
        
        return {
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": round(len(winning) / len(trades) * 100, 2) if trades else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_profit": round(avg_profit, 2),
            "avg_loss": round(avg_loss, 2),
            "largest_win": round(max((t.get("pnl", 0) for t in trades), default=0), 2),
            "largest_loss": round(min((t.get("pnl", 0) for t in trades), default=0), 2),
            "trades_detail": trades
        }
    
    def _generate_alerts(self, market_data: Dict) -> List[Dict]:
        """Generate important alerts and notifications"""
        alerts = []
        stocks = market_data.get("stocks", [])
        
        # High volatility alerts
        for stock in stocks:
            change_pct = abs(stock.get("change_pct", 0))
            if change_pct > 5:
                alerts.append({
                    "type": "HIGH_VOLATILITY",
                    "severity": "HIGH" if change_pct > 10 else "MEDIUM",
                    "symbol": stock.get("symbol", ""),
                    "message": f"{stock.get('name', '')} moved {change_pct:.2f}% today",
                    "timestamp": datetime.now().isoformat()
                })
        
        # Volume spike alerts
        for stock in stocks:
            volume_ratio = stock.get("volume_ratio", 1)
            if volume_ratio > 2:
                alerts.append({
                    "type": "VOLUME_SPIKE",
                    "severity": "MEDIUM",
                    "symbol": stock.get("symbol", ""),
                    "message": f"{stock.get('name', '')} volume {volume_ratio:.1f}x average",
                    "timestamp": datetime.now().isoformat()
                })
        
        return alerts[:20]  # Limit to top 20 alerts
    
    def _generate_recommendations(self, market_data: Dict, trades: List[Dict]) -> List[str]:
        """Generate trading recommendations based on analysis"""
        recommendations = []
        
        # Market sentiment based recommendations
        sentiment = self._calculate_sentiment(market_data)
        if sentiment == "Bullish":
            recommendations.append("Market showing bullish momentum - Consider long positions in strong sectors")
        elif sentiment == "Bearish":
            recommendations.append("Market under pressure - Exercise caution, consider defensive stocks")
        else:
            recommendations.append("Market consolidating - Wait for clear directional move")
        
        # Sector rotation recommendations
        sectors = self._analyze_sectors(market_data)
        top_sector = list(sectors.keys())[0] if sectors else None
        if top_sector:
            recommendations.append(f"Focus on {top_sector} sector - showing relative strength")
        
        # Risk management
        if trades:
            win_rate = len([t for t in trades if t.get("pnl", 0) > 0]) / len(trades) * 100
            if win_rate < 40:
                recommendations.append("Win rate below 40% - Review strategy and risk management")
        
        return recommendations
    
    def _save_report(self, report: Dict):
        """Save report to JSON file"""
        filename = f"daily_report_{report['date']}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"[REPORT] Saved to {filepath}")
    
    def generate_html_report(self, report: Dict) -> str:
        """Generate HTML version of the report"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Daily Trading Report - {report['date']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .summary-box {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .metric-label {{ font-weight: bold; color: #7f8c8d; }}
        .metric-value {{ font-size: 24px; color: #2c3e50; }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #34495e; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
        tr:hover {{ background: #f8f9fa; }}
        .alert {{ padding: 10px; margin: 5px 0; border-radius: 5px; }}
        .alert-high {{ background: #fee; border-left: 4px solid #e74c3c; }}
        .alert-medium {{ background: #fef5e7; border-left: 4px solid #f39c12; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Daily Trading Report</h1>
        <p><strong>Date:</strong> {report['date']} | <strong>Generated:</strong> {report['generated_at']}</p>
        
        <h2>Market Summary</h2>
        <div class="summary-box">
            <div class="metric">
                <div class="metric-label">NIFTY 50</div>
                <div class="metric-value {'positive' if report['market_summary']['nifty_50']['change'] > 0 else 'negative'}">
                    {report['market_summary']['nifty_50']['value']:.2f} 
                    ({report['market_summary']['nifty_50']['change_pct']:+.2f}%)
                </div>
            </div>
            <div class="metric">
                <div class="metric-label">Sentiment</div>
                <div class="metric-value">{report['market_summary']['market_sentiment']}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Advancing</div>
                <div class="metric-value positive">{report['market_summary']['advancing']}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Declining</div>
                <div class="metric-value negative">{report['market_summary']['declining']}</div>
            </div>
        </div>
        
        <h2>Top Performers</h2>
        <table>
            <tr><th>Symbol</th><th>Name</th><th>Price</th><th>Change %</th><th>Sector</th></tr>
            {''.join(f"<tr><td>{s['symbol']}</td><td>{s['name']}</td><td>₹{s['price']:.2f}</td><td class='positive'>{s['change_pct']:+.2f}%</td><td>{s['sector']}</td></tr>" for s in report['top_performers'][:5])}
        </table>
        
        <h2>Top Losers</h2>
        <table>
            <tr><th>Symbol</th><th>Name</th><th>Price</th><th>Change %</th><th>Sector</th></tr>
            {''.join(f"<tr><td>{s['symbol']}</td><td>{s['name']}</td><td>₹{s['price']:.2f}</td><td class='negative'>{s['change_pct']:+.2f}%</td><td>{s['sector']}</td></tr>" for s in report['top_losers'][:5])}
        </table>
        
        <h2>Trading Summary</h2>
        <div class="summary-box">
            <div class="metric">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">{report['trading_summary']['total_trades']}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{report['trading_summary']['win_rate']:.1f}%</div>
            </div>
            <div class="metric">
                <div class="metric-label">Total P&L</div>
                <div class="metric-value {'positive' if report['trading_summary']['total_pnl'] > 0 else 'negative'}">
                    ₹{report['trading_summary']['total_pnl']:,.2f}
                </div>
            </div>
        </div>
        
        <h2>Recommendations</h2>
        <ul>
            {''.join(f"<li>{rec}</li>" for rec in report['recommendations'])}
        </ul>
    </div>
</body>
</html>
"""
        
        # Save HTML report
        filename = f"daily_report_{report['date']}.html"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"[REPORT] HTML saved to {filepath}")
        return filepath


# Example usage
if __name__ == "__main__":
    generator = DailyReportGenerator()
    
    # Sample data
    sample_market_data = {
        "indices": {
            "NIFTY": {"value": 23847, "change": 285, "change_pct": 1.21},
            "BANKNIFTY": {"value": 51234, "change": 412, "change_pct": 0.81}
        },
        "stocks": [
            {"symbol": "RELIANCE", "name": "Reliance Industries", "price": 2934, "change_pct": 1.5, "volume": 5000000, "sector": "Oil & Gas"},
            {"symbol": "TCS", "name": "Tata Consultancy Services", "price": 3845, "change_pct": 2.1, "volume": 3000000, "sector": "IT Services"}
        ]
    }
    
    sample_trades = [
        {"symbol": "RELIANCE", "entry": 2900, "exit": 2934, "pnl": 340, "timestamp": datetime.now().isoformat()},
        {"symbol": "TCS", "entry": 3800, "exit": 3845, "pnl": 450, "timestamp": datetime.now().isoformat()}
    ]
    
    report = generator.generate_report(sample_market_data, sample_trades)
    generator.generate_html_report(report)
    print("Daily report generated successfully!")
