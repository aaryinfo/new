"""
Quick scan function for Vercel serverless - fetches top 20 stocks only
This works within the 10-second timeout limit
"""
import yfinance as yf
from datetime import datetime

# Top 20 most liquid F&O stocks for quick scanning
QUICK_SCAN_STOCKS = [
    ("Reliance", "RELIANCE.NS"),
    ("TCS", "TCS.NS"),
    ("HDFC Bank", "HDFCBANK.NS"),
    ("Infosys", "INFY.NS"),
    ("ICICI Bank", "ICICIBANK.NS"),
    ("Bharti Airtel", "BHARTIARTL.NS"),
    ("ITC", "ITC.NS"),
    ("SBI", "SBIN.NS"),
    ("Axis Bank", "AXISBANK.NS"),
    ("Kotak Bank", "KOTAKBANK.NS"),
    ("HUL", "HINDUNILVR.NS"),
    ("L&T", "LT.NS"),
    ("Asian Paints", "ASIANPAINT.NS"),
    ("Maruti Suzuki", "MARUTI.NS"),
    ("Bajaj Finance", "BAJFINANCE.NS"),
    ("Titan", "TITAN.NS"),
    ("Wipro", "WIPRO.NS"),
    ("Tech Mahindra", "TECHM.NS"),
    ("HCL Tech", "HCLTECH.NS"),
    ("Tata Steel", "TATASTEEL.NS")
]

def quick_scan_for_vercel():
    """
    Fetch current data for top 20 stocks quickly
    Returns within 5-8 seconds to stay under Vercel's 10-second limit
    """
    results = []
    
    try:
        # Fetch all symbols at once (faster than individual requests)
        symbols = [sym for _, sym in QUICK_SCAN_STOCKS]
        tickers = yf.Tickers(' '.join(symbols))
        
        for name, symbol in QUICK_SCAN_STOCKS:
            try:
                ticker = tickers.tickers[symbol]
                info = ticker.info
                hist = ticker.history(period="1d")
                
                if hist.empty:
                    continue
                
                curr_close = float(hist['Close'].iloc[-1])
                prev_close = float(info.get('previousClose', curr_close))
                change = curr_close - prev_close
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0
                
                # Simple signal logic
                signal = "NEUTRAL"
                if change_pct > 2:
                    signal = "BUY"
                elif change_pct < -2:
                    signal = "SELL"
                
                results.append({
                    "name": name,
                    "symbol": symbol.replace(".NS", ""),
                    "curr_close": round(curr_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": int(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0,
                    "high": round(float(hist['High'].iloc[-1]), 2),
                    "low": round(float(hist['Low'].iloc[-1]), 2),
                    "signal": signal,
                    "alerted": abs(change_pct) > 2,
                    "sector": "Unknown",
                    "last_updated": datetime.now().strftime("%H:%M:%S")
                })
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                continue
        
        return results
    
    except Exception as e:
        print(f"Quick scan error: {e}")
        return []
