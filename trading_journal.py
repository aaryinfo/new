"""
Trading Journal System for NSE F&O Scanner
Track all trades, analyze performance, and maintain detailed trading records
"""

from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Optional
import csv


class TradingJournal:
    """Comprehensive trading journal with analytics"""
    
    def __init__(self, journal_dir="journal"):
        self.journal_dir = journal_dir
        os.makedirs(journal_dir, exist_ok=True)
        self.journal_file = os.path.join(journal_dir, "trades.json")
        self.trades = self._load_trades()
    
    def _load_trades(self) -> List[Dict]:
        """Load existing trades from file"""
        if os.path.exists(self.journal_file):
            try:
                with open(self.journal_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_trades(self):
        """Save trades to file"""
        with open(self.journal_file, 'w') as f:
            json.dump(self.trades, f, indent=2)
    
    def add_trade(self, trade: Dict) -> str:
        """
        Add a new trade to the journal
        
        Args:
            trade: Dictionary containing trade details
            
        Returns:
            Trade ID
        """
        trade_id = f"T{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        trade_entry = {
            "id": trade_id,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "symbol": trade.get("symbol", ""),
            "name": trade.get("name", ""),
            "type": trade.get("type", "LONG"),  # LONG or SHORT
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("exit_price", 0),
            "quantity": trade.get("quantity", 0),
            "entry_time": trade.get("entry_time", datetime.now().isoformat()),
            "exit_time": trade.get("exit_time", datetime.now().isoformat()),
            "pnl": self._calculate_pnl(trade),
            "pnl_pct": self._calculate_pnl_pct(trade),
            "fees": trade.get("fees", 0),
            "net_pnl": 0,  # Will be calculated
            "strategy": trade.get("strategy", "Manual"),
            "setup": trade.get("setup", ""),
            "notes": trade.get("notes", ""),
            "tags": trade.get("tags", []),
            "screenshots": trade.get("screenshots", []),
            "ai_signal": trade.get("ai_signal", ""),
            "stop_loss": trade.get("stop_loss", 0),
            "target": trade.get("target", 0),
            "risk_reward": trade.get("risk_reward", 0),
            "sector": trade.get("sector", ""),
            "market_condition": trade.get("market_condition", ""),
            "emotions": trade.get("emotions", ""),
            "mistakes": trade.get("mistakes", ""),
            "lessons": trade.get("lessons", "")
        }
        
        # Calculate net P&L
        trade_entry["net_pnl"] = trade_entry["pnl"] - trade_entry["fees"]
        
        self.trades.append(trade_entry)
        self._save_trades()
        
        print(f"[JOURNAL] Trade {trade_id} added: {trade_entry['symbol']} | P&L: ₹{trade_entry['net_pnl']:.2f}")
        return trade_id
    
    def _calculate_pnl(self, trade: Dict) -> float:
        """Calculate profit/loss for a trade"""
        entry = trade.get("entry_price", 0)
        exit_price = trade.get("exit_price", 0)
        quantity = trade.get("quantity", 0)
        trade_type = trade.get("type", "LONG")
        
        if trade_type == "LONG":
            pnl = (exit_price - entry) * quantity
        else:  # SHORT
            pnl = (entry - exit_price) * quantity
        
        return round(pnl, 2)
    
    def _calculate_pnl_pct(self, trade: Dict) -> float:
        """Calculate profit/loss percentage"""
        entry = trade.get("entry_price", 0)
        exit_price = trade.get("exit_price", 0)
        trade_type = trade.get("type", "LONG")
        
        if entry == 0:
            return 0
        
        if trade_type == "LONG":
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:  # SHORT
            pnl_pct = ((entry - exit_price) / entry) * 100
        
        return round(pnl_pct, 2)
    
    def get_trade(self, trade_id: str) -> Optional[Dict]:
        """Get a specific trade by ID"""
        for trade in self.trades:
            if trade["id"] == trade_id:
                return trade
        return None
    
    def update_trade(self, trade_id: str, updates: Dict):
        """Update an existing trade"""
        for i, trade in enumerate(self.trades):
            if trade["id"] == trade_id:
                self.trades[i].update(updates)
                self._save_trades()
                print(f"[JOURNAL] Trade {trade_id} updated")
                return True
        return False
    
    def delete_trade(self, trade_id: str):
        """Delete a trade"""
        self.trades = [t for t in self.trades if t["id"] != trade_id]
        self._save_trades()
        print(f"[JOURNAL] Trade {trade_id} deleted")
    
    def get_trades_by_date(self, date: str) -> List[Dict]:
        """Get all trades for a specific date"""
        return [t for t in self.trades if t["date"] == date]
    
    def get_trades_by_symbol(self, symbol: str) -> List[Dict]:
        """Get all trades for a specific symbol"""
        return [t for t in self.trades if t["symbol"] == symbol]
    
    def get_trades_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get trades within a date range"""
        return [t for t in self.trades 
                if start_date <= t["date"] <= end_date]
    
    def get_performance_stats(self, days: int = 30) -> Dict:
        """Calculate performance statistics"""
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent_trades = [t for t in self.trades if t["date"] >= cutoff_date]
        
        if not recent_trades:
            return self._empty_stats()
        
        winning_trades = [t for t in recent_trades if t["net_pnl"] > 0]
        losing_trades = [t for t in recent_trades if t["net_pnl"] < 0]
        breakeven_trades = [t for t in recent_trades if t["net_pnl"] == 0]
        
        total_pnl = sum(t["net_pnl"] for t in recent_trades)
        total_wins = sum(t["net_pnl"] for t in winning_trades)
        total_losses = sum(t["net_pnl"] for t in losing_trades)
        
        return {
            "period_days": days,
            "total_trades": len(recent_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "breakeven_trades": len(breakeven_trades),
            "win_rate": round(len(winning_trades) / len(recent_trades) * 100, 2),
            "total_pnl": round(total_pnl, 2),
            "total_wins": round(total_wins, 2),
            "total_losses": round(total_losses, 2),
            "avg_win": round(total_wins / len(winning_trades), 2) if winning_trades else 0,
            "avg_loss": round(total_losses / len(losing_trades), 2) if losing_trades else 0,
            "largest_win": round(max((t["net_pnl"] for t in recent_trades), default=0), 2),
            "largest_loss": round(min((t["net_pnl"] for t in recent_trades), default=0), 2),
            "avg_pnl_per_trade": round(total_pnl / len(recent_trades), 2),
            "profit_factor": round(abs(total_wins / total_losses), 2) if total_losses != 0 else 0,
            "expectancy": round(total_pnl / len(recent_trades), 2),
            "best_day": self._get_best_day(recent_trades),
            "worst_day": self._get_worst_day(recent_trades),
            "most_traded_symbol": self._get_most_traded_symbol(recent_trades),
            "best_performing_symbol": self._get_best_symbol(recent_trades),
            "worst_performing_symbol": self._get_worst_symbol(recent_trades)
        }
    
    def _empty_stats(self) -> Dict:
        """Return empty statistics"""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "avg_win": 0,
            "avg_loss": 0
        }
    
    def _get_best_day(self, trades: List[Dict]) -> Dict:
        """Find the best trading day"""
        daily_pnl = {}
        for trade in trades:
            date = trade["date"]
            daily_pnl[date] = daily_pnl.get(date, 0) + trade["net_pnl"]
        
        if not daily_pnl:
            return {"date": "", "pnl": 0}
        
        best_date = max(daily_pnl, key=daily_pnl.get)
        return {"date": best_date, "pnl": round(daily_pnl[best_date], 2)}
    
    def _get_worst_day(self, trades: List[Dict]) -> Dict:
        """Find the worst trading day"""
        daily_pnl = {}
        for trade in trades:
            date = trade["date"]
            daily_pnl[date] = daily_pnl.get(date, 0) + trade["net_pnl"]
        
        if not daily_pnl:
            return {"date": "", "pnl": 0}
        
        worst_date = min(daily_pnl, key=daily_pnl.get)
        return {"date": worst_date, "pnl": round(daily_pnl[worst_date], 2)}
    
    def _get_most_traded_symbol(self, trades: List[Dict]) -> Dict:
        """Find most frequently traded symbol"""
        symbol_counts = {}
        for trade in trades:
            symbol = trade["symbol"]
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        if not symbol_counts:
            return {"symbol": "", "count": 0}
        
        most_traded = max(symbol_counts, key=symbol_counts.get)
        return {"symbol": most_traded, "count": symbol_counts[most_traded]}
    
    def _get_best_symbol(self, trades: List[Dict]) -> Dict:
        """Find best performing symbol"""
        symbol_pnl = {}
        for trade in trades:
            symbol = trade["symbol"]
            symbol_pnl[symbol] = symbol_pnl.get(symbol, 0) + trade["net_pnl"]
        
        if not symbol_pnl:
            return {"symbol": "", "pnl": 0}
        
        best_symbol = max(symbol_pnl, key=symbol_pnl.get)
        return {"symbol": best_symbol, "pnl": round(symbol_pnl[best_symbol], 2)}
    
    def _get_worst_symbol(self, trades: List[Dict]) -> Dict:
        """Find worst performing symbol"""
        symbol_pnl = {}
        for trade in trades:
            symbol = trade["symbol"]
            symbol_pnl[symbol] = symbol_pnl.get(symbol, 0) + trade["net_pnl"]
        
        if not symbol_pnl:
            return {"symbol": "", "pnl": 0}
        
        worst_symbol = min(symbol_pnl, key=symbol_pnl.get)
        return {"symbol": worst_symbol, "pnl": round(symbol_pnl[worst_symbol], 2)}
    
    def export_to_csv(self, filename: str = None):
        """Export journal to CSV"""
        if not filename:
            filename = f"trading_journal_{datetime.now().strftime('%Y%m%d')}.csv"
        
        filepath = os.path.join(self.journal_dir, filename)
        
        if not self.trades:
            print("[JOURNAL] No trades to export")
            return
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.trades[0].keys())
            writer.writeheader()
            writer.writerows(self.trades)
        
        print(f"[JOURNAL] Exported to {filepath}")
        return filepath
    
    def generate_journal_report(self, days: int = 30) -> str:
        """Generate a detailed journal report"""
        stats = self.get_performance_stats(days)
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║           TRADING JOURNAL PERFORMANCE REPORT                 ║
║              Last {days} Days Analysis                            ║
╚══════════════════════════════════════════════════════════════╝

📊 OVERALL STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Trades:        {stats['total_trades']}
Winning Trades:      {stats['winning_trades']} ✓
Losing Trades:       {stats['losing_trades']} ✗
Breakeven Trades:    {stats['breakeven_trades']} ─
Win Rate:            {stats['win_rate']:.2f}%

💰 PROFIT & LOSS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total P&L:           ₹{stats['total_pnl']:,.2f}
Total Wins:          ₹{stats['total_wins']:,.2f}
Total Losses:        ₹{stats['total_losses']:,.2f}
Average Win:         ₹{stats['avg_win']:,.2f}
Average Loss:        ₹{stats['avg_loss']:,.2f}
Largest Win:         ₹{stats['largest_win']:,.2f}
Largest Loss:        ₹{stats['largest_loss']:,.2f}

📈 PERFORMANCE METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Avg P&L per Trade:   ₹{stats['avg_pnl_per_trade']:,.2f}
Profit Factor:       {stats['profit_factor']:.2f}
Expectancy:          ₹{stats['expectancy']:,.2f}

🏆 HIGHLIGHTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Best Day:            {stats['best_day']['date']} (₹{stats['best_day']['pnl']:,.2f})
Worst Day:           {stats['worst_day']['date']} (₹{stats['worst_day']['pnl']:,.2f})
Most Traded:         {stats['most_traded_symbol']['symbol']} ({stats['most_traded_symbol']['count']} trades)
Best Symbol:         {stats['best_performing_symbol']['symbol']} (₹{stats['best_performing_symbol']['pnl']:,.2f})
Worst Symbol:        {stats['worst_performing_symbol']['symbol']} (₹{stats['worst_performing_symbol']['pnl']:,.2f})

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # Save report
        report_file = os.path.join(self.journal_dir, f"journal_report_{datetime.now().strftime('%Y%m%d')}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(report)
        print(f"\n[JOURNAL] Report saved to {report_file}")
        return report


# Example usage
if __name__ == "__main__":
    journal = TradingJournal()
    
    # Add sample trades
    sample_trade_1 = {
        "symbol": "RELIANCE",
        "name": "Reliance Industries",
        "type": "LONG",
        "entry_price": 2900,
        "exit_price": 2950,
        "quantity": 10,
        "fees": 50,
        "strategy": "Breakout",
        "setup": "Bull flag breakout above 2900",
        "notes": "Strong volume confirmation, held above EMA9",
        "tags": ["breakout", "momentum"],
        "stop_loss": 2880,
        "target": 2960,
        "risk_reward": 2.5,
        "sector": "Oil & Gas",
        "market_condition": "Bullish",
        "emotions": "Confident, patient",
        "lessons": "Waited for confirmation before entry"
    }
    
    sample_trade_2 = {
        "symbol": "TCS",
        "name": "Tata Consultancy Services",
        "type": "LONG",
        "entry_price": 3800,
        "exit_price": 3750,
        "quantity": 5,
        "fees": 30,
        "strategy": "Support Bounce",
        "setup": "Bounce from support zone",
        "notes": "Failed to hold support, cut loss quickly",
        "tags": ["support", "reversal"],
        "stop_loss": 3780,
        "target": 3850,
        "risk_reward": 2.0,
        "sector": "IT Services",
        "market_condition": "Neutral",
        "emotions": "Disappointed but disciplined",
        "mistakes": "Entered too early without confirmation",
        "lessons": "Wait for price action confirmation at support"
    }
    
    # Add trades
    trade_id_1 = journal.add_trade(sample_trade_1)
    trade_id_2 = journal.add_trade(sample_trade_2)
    
    # Get performance stats
    stats = journal.get_performance_stats(30)
    print("\n" + "="*60)
    print(f"Performance Stats (Last 30 days):")
    print(f"Total Trades: {stats['total_trades']}")
    print(f"Win Rate: {stats['win_rate']}%")
    print(f"Total P&L: ₹{stats['total_pnl']:,.2f}")
    print("="*60)
    
    # Generate report
    journal.generate_journal_report(30)
    
    # Export to CSV
    journal.export_to_csv()
