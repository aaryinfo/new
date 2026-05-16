# Trading Journal & Daily Report System

Complete trading journal and daily report generation system for NSE F&O Scanner.

## 📋 Features

### Trading Journal
- ✅ Track all trades with detailed information
- ✅ Calculate P&L, win rate, and performance metrics
- ✅ Add notes, emotions, lessons learned
- ✅ Tag trades by strategy, setup, sector
- ✅ Export to CSV for analysis
- ✅ Generate performance reports
- ✅ Analyze best/worst days and symbols

### Daily Reports
- ✅ Market summary with indices
- ✅ Top performers and losers
- ✅ Sector-wise performance analysis
- ✅ Trading activity summary
- ✅ Alerts and notifications
- ✅ AI-powered recommendations
- ✅ HTML and JSON export

## 🚀 Quick Start

### 1. Test the Modules

```bash
# Test Trading Journal
python trading_journal.py

# Test Daily Report Generator
python daily_report.py
```

### 2. Integrate with Flask App

Add to your `app.py`:

```python
from journal_api import register_journal_routes

# After creating Flask app
app = Flask(__name__)
CORS(app)

# Register journal routes
register_journal_routes(app)
```

### 3. Use the API Endpoints

#### Trading Journal Endpoints

**Add a Trade:**
```bash
POST /api/journal/trade
Content-Type: application/json

{
  "symbol": "RELIANCE",
  "name": "Reliance Industries",
  "type": "LONG",
  "entry_price": 2900,
  "exit_price": 2950,
  "quantity": 10,
  "fees": 50,
  "strategy": "Breakout",
  "setup": "Bull flag breakout",
  "notes": "Strong volume confirmation",
  "tags": ["breakout", "momentum"],
  "stop_loss": 2880,
  "target": 2960,
  "sector": "Oil & Gas"
}
```

**Get All Trades:**
```bash
GET /api/journal/trades
GET /api/journal/trades?symbol=RELIANCE
GET /api/journal/trades?start_date=2024-01-01&end_date=2024-12-31
```

**Get Performance Stats:**
```bash
GET /api/journal/stats?days=30
```

**Export to CSV:**
```bash
GET /api/journal/export
```

**Generate Report:**
```bash
GET /api/journal/report?days=30
```

#### Daily Report Endpoints

**Generate Daily Report:**
```bash
POST /api/report/daily
Content-Type: application/json

{
  "market_data": {
    "indices": {
      "NIFTY": {"value": 23847, "change": 285, "change_pct": 1.21}
    },
    "stocks": [
      {
        "symbol": "RELIANCE",
        "name": "Reliance Industries",
        "price": 2934,
        "change_pct": 1.5,
        "volume": 5000000,
        "sector": "Oil & Gas"
      }
    ]
  },
  "trades": [
    {
      "symbol": "RELIANCE",
      "entry": 2900,
      "exit": 2934,
      "pnl": 340
    }
  ]
}
```

**Generate HTML Report:**
```bash
POST /api/report/daily/html
```

## 📊 Trading Journal Usage

### Python API

```python
from trading_journal import TradingJournal

# Initialize journal
journal = TradingJournal()

# Add a trade
trade = {
    "symbol": "RELIANCE",
    "name": "Reliance Industries",
    "type": "LONG",
    "entry_price": 2900,
    "exit_price": 2950,
    "quantity": 10,
    "fees": 50,
    "strategy": "Breakout",
    "notes": "Strong momentum",
    "tags": ["breakout"],
    "stop_loss": 2880,
    "target": 2960
}

trade_id = journal.add_trade(trade)

# Get performance stats
stats = journal.get_performance_stats(days=30)
print(f"Win Rate: {stats['win_rate']}%")
print(f"Total P&L: ₹{stats['total_pnl']:,.2f}")

# Generate report
journal.generate_journal_report(30)

# Export to CSV
journal.export_to_csv()
```

## 📈 Daily Report Usage

### Python API

```python
from daily_report import DailyReportGenerator

# Initialize generator
generator = DailyReportGenerator()

# Prepare market data
market_data = {
    "indices": {
        "NIFTY": {"value": 23847, "change": 285, "change_pct": 1.21}
    },
    "stocks": [
        {
            "symbol": "RELIANCE",
            "name": "Reliance Industries",
            "price": 2934,
            "change_pct": 1.5,
            "volume": 5000000,
            "sector": "Oil & Gas"
        }
    ]
}

trades = [
    {"symbol": "RELIANCE", "entry": 2900, "exit": 2934, "pnl": 340}
]

# Generate report
report = generator.generate_report(market_data, trades)

# Generate HTML version
html_path = generator.generate_html_report(report)
print(f"Report saved to: {html_path}")
```

## 📁 File Structure

```
project/
├── trading_journal.py      # Trading journal core module
├── daily_report.py          # Daily report generator
├── journal_api.py           # Flask API endpoints
├── journal/                 # Journal data directory
│   ├── trades.json         # All trades database
│   ├── journal_report_*.txt
│   └── trading_journal_*.csv
└── reports/                 # Daily reports directory
    ├── daily_report_*.json
    └── daily_report_*.html
```

## 📝 Trade Fields

### Required Fields
- `symbol`: Stock symbol (e.g., "RELIANCE")
- `entry_price`: Entry price
- `exit_price`: Exit price
- `quantity`: Number of shares/contracts

### Optional Fields
- `name`: Stock name
- `type`: "LONG" or "SHORT" (default: "LONG")
- `fees`: Trading fees
- `strategy`: Strategy name (e.g., "Breakout", "Reversal")
- `setup`: Trade setup description
- `notes`: Additional notes
- `tags`: Array of tags
- `stop_loss`: Stop loss price
- `target`: Target price
- `risk_reward`: Risk-reward ratio
- `sector`: Stock sector
- `market_condition`: Market condition during trade
- `emotions`: Emotional state during trade
- `mistakes`: Mistakes made
- `lessons`: Lessons learned

## 📊 Performance Metrics

The journal calculates:
- **Win Rate**: Percentage of winning trades
- **Total P&L**: Net profit/loss
- **Average Win/Loss**: Average profit and loss per trade
- **Profit Factor**: Ratio of total wins to total losses
- **Expectancy**: Expected value per trade
- **Best/Worst Day**: Most profitable and worst trading days
- **Best/Worst Symbol**: Best and worst performing stocks
- **Most Traded Symbol**: Most frequently traded stock

## 🎨 Report Features

Daily reports include:
- Market summary with indices
- Top 10 gainers and losers
- Sector-wise performance analysis
- Trading activity summary
- High volatility alerts
- Volume spike notifications
- AI-powered recommendations
- HTML and JSON export formats

## 🔧 Customization

### Custom Report Templates

Edit `daily_report.py` to customize:
- Report sections
- Alert thresholds
- Recommendation logic
- HTML styling

### Custom Journal Fields

Edit `trading_journal.py` to add:
- Custom trade fields
- Additional metrics
- Custom calculations
- Export formats

## 📱 Integration Tips

### Auto-generate Daily Reports

Add to your scanner's end-of-day routine:

```python
from daily_report import DailyReportGenerator

def end_of_day_routine():
    # Fetch today's market data
    market_data = get_market_data()
    trades = get_today_trades()
    
    # Generate report
    generator = DailyReportGenerator()
    report = generator.generate_report(market_data, trades)
    generator.generate_html_report(report)
    
    # Send email notification
    send_email_report(report)
```

### Auto-log Trades

Connect to your trading system:

```python
from trading_journal import TradingJournal

journal = TradingJournal()

def on_trade_exit(trade_data):
    # Automatically log completed trades
    journal.add_trade(trade_data)
```

## 🎯 Best Practices

1. **Log Every Trade**: Record all trades immediately after exit
2. **Add Detailed Notes**: Include setup, emotions, and lessons
3. **Review Weekly**: Generate weekly performance reports
4. **Tag Consistently**: Use consistent tags for easy filtering
5. **Track Emotions**: Record emotional state for pattern analysis
6. **Document Mistakes**: Learn from errors by documenting them
7. **Set Goals**: Track progress toward trading goals

## 📧 Support

For issues or questions:
1. Check the example usage in the Python files
2. Review the API endpoint documentation
3. Test with sample data first

## 🚀 Future Enhancements

Planned features:
- [ ] Chart integration with trade markers
- [ ] Email report delivery
- [ ] Telegram/WhatsApp notifications
- [ ] Advanced analytics dashboard
- [ ] Machine learning insights
- [ ] Multi-timeframe analysis
- [ ] Risk management calculator
- [ ] Position sizing recommendations

---

**Happy Trading! 📈**
