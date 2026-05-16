"""
Indian Intraday Stock Scanner - Enhanced Backend Server
Requirements: pip install yfinance pymongo flask flask-cors pandas numpy scikit-learn openai supabase PyJWT
Run: python app.py
"""

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import time
import json
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.linear_model import LinearRegression

# ── Supabase Auth ────────────────────────────────────────────────────
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ADMIN_EMAIL          = os.environ.get("ADMIN_EMAIL", "admin@yourdomain.com")
JWT_SECRET           = os.environ.get("SUPABASE_JWT_SECRET", "")  # from Supabase dashboard → Settings → API

_supabase_admin = None
try:
    from supabase import create_client
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        _supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("[OK] Supabase admin client ready")
    else:
        print("[WARN] SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
except ImportError:
    print("[WARN] supabase package not installed — run: pip install supabase")

def _verify_token(token: str) -> dict | None:
    """Verify Supabase JWT and return payload or None."""
    if not token: return None
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(
            token, JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        return payload
    except Exception as ex:
        print(f"[AUTH] Token verify failed: {ex}")
        return None

def _get_user_role(payload: dict) -> str:
    """Return 'admin' or 'user' based on email in token."""
    email = (payload.get("email") or
             (payload.get("user_metadata") or {}).get("email") or "")
    return "admin" if email.lower() == ADMIN_EMAIL.lower() else "user"

def require_auth(f):
    """Decorator: protects routes — requires valid Supabase JWT."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        payload = _verify_token(token)
        if not payload:
            return jsonify({"error": "Unauthorized", "code": 401}), 401
        request.user_payload = payload
        request.user_role = _get_user_role(payload)
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    """Decorator: admin-only routes."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        payload = _verify_token(token)
        if not payload:
            return jsonify({"error": "Unauthorized", "code": 401}), 401
        if _get_user_role(payload) != "admin":
            return jsonify({"error": "Forbidden — admin only", "code": 403}), 403
        request.user_payload = payload
        request.user_role = "admin"
        return f(*args, **kwargs)
    return decorated

# -- OpenAI for news ---------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = None
try:
    import openai
    if OPENAI_API_KEY:
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        print("[OK] OpenAI configured")
    else:
        print("[INFO] OPENAI_API_KEY not set - news will use fallback")
except ImportError:
    print("[INFO] openai package not installed - news will use fallback")

# -- MongoDB -----------------------------------------------------------------
try:
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    client.server_info()
    db = client["stock_scanner"]
    stocks_col  = db["live_stocks"]
    history_col = db["history"]
    backtest_col = db["backtest"]
    news_col = db["news_cache"]
    journal_col = db["trading_journal"]
    trade_state_col = db["current_daily_trade"]
    agent_trades_col  = db["agent_trades"]
    agent_journal_col = db["agent_journal"]
    agent_log_col     = db["agent_log"]
    users_col         = db["users"]
    MONGO_OK = True
    print("[OK] MongoDB connected")
except Exception as e:
    print(f"[WARN] MongoDB unavailable ({e}), using CSV file storage")
    MONGO_OK = False
    _memory_store = {}; _news_cache = {}; _journal_store = []; _active_trade_store = None
    agent_trades_col = agent_journal_col = agent_log_col = users_col = None
    _ag_mem_trades: list = []; _ag_mem_journal: list = []; _ag_mem_log: list = []
    
    # CSV file paths for persistence
    import os
    CSV_DIR = "data"
    os.makedirs(CSV_DIR, exist_ok=True)
    AGENT_TRADES_CSV = os.path.join(CSV_DIR, "agent_trades.csv")
    AGENT_JOURNAL_CSV = os.path.join(CSV_DIR, "agent_journal.csv")
    AGENT_LOG_CSV = os.path.join(CSV_DIR, "agent_log.csv")
    
    # Load existing data from CSV on startup
    def _load_csv_data():
        global _ag_mem_trades, _ag_mem_journal, _ag_mem_log
        import csv
        
        # Load agent trades (open trades)
        if os.path.exists(AGENT_TRADES_CSV):
            try:
                with open(AGENT_TRADES_CSV, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    _ag_mem_trades = [dict(row) for row in reader]
                    # Convert numeric fields
                    for t in _ag_mem_trades:
                        for key in ['entry', 'sl', 'target', 'curr_price', 'exit_price', 'p_l', 'p_l_pct', 'qty', 'score', 'rsi_at_entry', 'chg_at_entry', 'peak_price', 'trail_sl']:
                            if key in t and t[key]:
                                try:
                                    t[key] = float(t[key])
                                except:
                                    pass
                        if 'qty' in t and t['qty']:
                            t['qty'] = int(float(t['qty']))
                print(f"[CSV] Loaded {len(_ag_mem_trades)} open trades")
            except Exception as e:
                print(f"[CSV] Error loading trades: {e}")
        
        # Load agent journal (closed trades)
        if os.path.exists(AGENT_JOURNAL_CSV):
            try:
                with open(AGENT_JOURNAL_CSV, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    _ag_mem_journal = [dict(row) for row in reader]
                    # Convert numeric fields
                    for t in _ag_mem_journal:
                        for key in ['entry', 'sl', 'target', 'curr_price', 'exit_price', 'p_l', 'p_l_pct', 'qty', 'score', 'rsi_at_entry', 'chg_at_entry', 'peak_price', 'trail_sl']:
                            if key in t and t[key]:
                                try:
                                    t[key] = float(t[key])
                                except:
                                    pass
                        if 'qty' in t and t['qty']:
                            t['qty'] = int(float(t['qty']))
                print(f"[CSV] Loaded {len(_ag_mem_journal)} closed trades")
            except Exception as e:
                print(f"[CSV] Error loading journal: {e}")
        
        # Load agent log
        if os.path.exists(AGENT_LOG_CSV):
            try:
                with open(AGENT_LOG_CSV, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    _ag_mem_log = [dict(row) for row in reader]
                    # Convert numeric fields
                    for log in _ag_mem_log:
                        for key in ['score', 'entry', 'sl', 'target', 'rsi', 'chg', 'qty']:
                            if key in log and log[key]:
                                try:
                                    log[key] = float(log[key])
                                except:
                                    pass
                print(f"[CSV] Loaded {len(_ag_mem_log)} log entries")
            except Exception as e:
                print(f"[CSV] Error loading log: {e}")
    
    # Save data to CSV
    def _save_to_csv(filepath, data, fieldnames):
        import csv
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(data)
        except Exception as e:
            print(f"[CSV] Error saving to {filepath}: {e}")
    
    # Load data on startup
    _load_csv_data()

_oi_spurts_cache = {}
_oi_contracts_cache = {} # symbol -> list of contracts
_last_oi_spurts_update = datetime.min
_ten_min_history_cache = None
_last_ten_min_update = datetime.min
# symbol -> {"trend": str, "signal_time": str, "latched_levels": dict}
_stock_state_cache_v2 = {}
_watchlist_state_cache_v2 = {}
_backtest_cache = None
_last_backtest_update = datetime.min
import requests
from sector_mapping import get_sector

app = Flask(__name__)
CORS(app)

# Use individual headers instead of a global session to avoid thread-safety issues
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def sanitize(obj):
    """Recursively replace NaN/Inf floats with None and convert numpy types to native python types."""
    import math
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if type(obj).__module__ == 'numpy':
        # Convert numpy scalar to python scalar
        try:
            val = obj.item()
            if isinstance(val, (float, int)):
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    return None
            return val
        except:
            if hasattr(obj, 'tolist'):
                return [sanitize(x) for x in obj.tolist()]
            return None
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list) or isinstance(obj, tuple):
        return [sanitize(v) for v in obj]
    return obj


def safe_jsonify(data):
    """jsonify after sanitizing NaN values."""
    return jsonify(sanitize(data))

FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))

# -- Stock list (NSE F&O universe - 206 stocks) ------------------------------
FO_STOCKS = [
    ("360 ONE WAM", "360ONE.NS"), ("ABB India", "ABB.NS"), ("APL Apollo", "APLAPOLLO.NS"),
    ("AU Small Finance", "AUBANK.NS"), ("Adani Energy", "ADANIENSOL.NS"),
    ("Adani Enterprises", "ADANIENT.NS"), ("Adani Green", "ADANIGREEN.NS"),
    ("Adani Ports", "ADANIPORTS.NS"), ("Aditya Birla Capital", "ABCAPITAL.NS"),
    ("Alkem Labs", "ALKEM.NS"), ("Amber Enterprises", "AMBER.NS"),
    ("Ambuja Cements", "AMBUJACEM.NS"), ("Angel One", "ANGELONE.NS"),
    ("Apollo Hospitals", "APOLLOHOSP.NS"), ("Ashok Leyland", "ASHOKLEY.NS"),
    ("Asian Paints", "ASIANPAINT.NS"), ("Astral", "ASTRAL.NS"),
    ("Aurobindo Pharma", "AUROPHARMA.NS"), ("Avenue Supermarts", "DMART.NS"),
    ("Axis Bank", "AXISBANK.NS"), ("BSE", "BSE.NS"), ("Bajaj Auto", "BAJAJ-AUTO.NS"),
    ("Bajaj Finance", "BAJFINANCE.NS"), ("Bajaj Finserv", "BAJAJFINSV.NS"),
    ("Bajaj Holdings", "BAJAJHLDNG.NS"), ("Bandhan Bank", "BANDHANBNK.NS"),
    ("Bank of Baroda", "BANKBARODA.NS"), ("Bank of India", "BANKINDIA.NS"),
    ("Bharat Dynamics", "BDL.NS"), ("Bharat Electronics", "BEL.NS"),
    ("Bharat Forge", "BHARATFORG.NS"), ("BHEL", "BHEL.NS"), ("BPCL", "BPCL.NS"),
    ("Bharti Airtel", "BHARTIARTL.NS"), ("Biocon", "BIOCON.NS"),
    ("Blue Star", "BLUESTARCO.NS"), ("Bosch", "BOSCHLTD.NS"),
    ("Britannia", "BRITANNIA.NS"), ("CG Power", "CGPOWER.NS"),
    ("Canara Bank", "CANBK.NS"), ("CDSL", "CDSL.NS"), ("Cholamandalam", "CHOLAFIN.NS"),
    ("Cipla", "CIPLA.NS"), ("Coal India", "COALINDIA.NS"), ("Coforge", "COFORGE.NS"),
    ("Colgate", "COLPAL.NS"), ("CAMS", "CAMS.NS"), ("CONCOR", "CONCOR.NS"),
    ("Crompton Greaves", "CROMPTON.NS"), ("Cummins India", "CUMMINSIND.NS"),
    ("DLF", "DLF.NS"), ("Dabur", "DABUR.NS"), ("Dalmia Bharat", "DALBHARAT.NS"),
    ("Delhivery", "DELHIVERY.NS"), ("Divi's Labs", "DIVISLAB.NS"),
    ("Dixon Tech", "DIXON.NS"), ("Dr Reddy's", "DRREDDY.NS"), ("Eternal", "ETERNAL.NS"),
    ("Eicher Motors", "EICHERMOT.NS"), ("Exide", "EXIDEIND.NS"),
    ("Nykaa", "NYKAA.NS"), ("Fortis Healthcare", "FORTIS.NS"), ("GAIL", "GAIL.NS"),
    ("GMR Airports", "GMRAIRPORT.NS"), ("Glenmark", "GLENMARK.NS"),
    ("Godrej Consumer", "GODREJCP.NS"), ("Godrej Properties", "GODREJPROP.NS"),
    ("Grasim", "GRASIM.NS"), ("HCL Tech", "HCLTECH.NS"), ("HDFC AMC", "HDFCAMC.NS"),
    ("HDFC Bank", "HDFCBANK.NS"), ("HDFC Life", "HDFCLIFE.NS"),
    ("Havells", "HAVELLS.NS"), ("Hero MotoCorp", "HEROMOTOCO.NS"),
    ("Hindalco", "HINDALCO.NS"), ("HAL", "HAL.NS"), ("HPCL", "HINDPETRO.NS"),
    ("HUL", "HINDUNILVR.NS"), ("Hindustan Zinc", "HINDZINC.NS"),
    ("Hitachi Energy", "POWERINDIA.NS"), ("HUDCO", "HUDCO.NS"),
    ("ICICI Bank", "ICICIBANK.NS"), ("ICICI Lombard", "ICICIGI.NS"),
    ("ICICI Prudential", "ICICIPRULI.NS"), ("IDFC First", "IDFCFIRSTB.NS"),
    ("ITC", "ITC.NS"), ("Indian Bank", "INDIANB.NS"), ("IEX", "IEX.NS"),
    ("IOC", "IOC.NS"), ("IRFC", "IRFC.NS"), ("IREDA", "IREDA.NS"),
    ("Indus Towers", "INDUSTOWER.NS"), ("IndusInd Bank", "INDUSINDBK.NS"),
    ("Info Edge", "NAUKRI.NS"), ("Infosys", "INFY.NS"), ("Inox Wind", "INOXWIND.NS"),
    ("IndiGo", "INDIGO.NS"), ("Jindal Steel", "JINDALSTEL.NS"),
    ("JSW Energy", "JSWENERGY.NS"), ("JSW Steel", "JSWSTEEL.NS"),
    ("Jio Financial", "JIOFIN.NS"), ("Jubilant Foodworks", "JUBLFOOD.NS"),
    ("KEI Industries", "KEI.NS"), ("KPIT Tech", "KPITTECH.NS"),
    ("Kalyan Jewellers", "KALYANKJIL.NS"), ("Kaynes Tech", "KAYNES.NS"),
    ("Kfin Technologies", "KFINTECH.NS"), ("Kotak Bank", "KOTAKBANK.NS"),
    ("L&T Finance", "LTF.NS"), ("LIC Housing", "LICHSGFIN.NS"),
    ("LTIMindtree", "LTIM.NS"), ("L&T", "LT.NS"), ("Laurus Labs", "LAURUSLABS.NS"),
    ("LIC India", "LICI.NS"), ("Lodha", "LODHA.NS"), ("Lupin", "LUPIN.NS"),
    ("M&M", "M&M.NS"), ("Manappuram", "MANAPPURAM.NS"), ("Mankind Pharma", "MANKIND.NS"),
    ("Marico", "MARICO.NS"), ("Maruti Suzuki", "MARUTI.NS"),
    ("Max Financial", "MFSL.NS"), ("Max Healthcare", "MAXHEALTH.NS"),
    ("Mazagon Dock", "MAZDOCK.NS"), ("Mphasis", "MPHASIS.NS"),
    ("MCX", "MCX.NS"), ("Muthoot Finance", "MUTHOOTFIN.NS"),
    ("NBCC", "NBCC.NS"), ("NHPC", "NHPC.NS"), ("NMDC", "NMDC.NS"),
    ("NTPC", "NTPC.NS"), ("NALCO", "NATIONALUM.NS"), ("Nestle India", "NESTLEIND.NS"),
    ("Nuvama", "NUVAMA.NS"), ("Oberoi Realty", "OBEROIRLTY.NS"),
    ("ONGC", "ONGC.NS"), ("Oil India", "OIL.NS"), ("Paytm", "PAYTM.NS"),
    ("OFSS", "OFSS.NS"), ("PB Fintech", "POLICYBZR.NS"), ("PG Electroplast", "PGEL.NS"),
    ("PI Industries", "PIIND.NS"), ("PNB Housing", "PNBHOUSING.NS"),
    ("Page Industries", "PAGEIND.NS"), ("Patanjali Foods", "PATANJALI.NS"),
    ("Persistent Systems", "PERSISTENT.NS"), ("Petronet LNG", "PETRONET.NS"),
    ("Pidilite", "PIDILITIND.NS"), ("Piramal Pharma", "PPLPHARMA.NS"),
    ("Polycab", "POLYCAB.NS"), ("PFC", "PFC.NS"), ("Power Grid", "POWERGRID.NS"),
    ("Premier Energies", "PREMIERENE.NS"), ("Prestige Estates", "PRESTIGE.NS"),
    ("PNB", "PNB.NS"), ("RBL Bank", "RBLBANK.NS"), ("REC", "RECLTD.NS"),
    ("RVNL", "RVNL.NS"), ("Reliance", "RELIANCE.NS"), ("SBI Cards", "SBICARD.NS"),
    ("SBI Life", "SBILIFE.NS"), ("Shree Cement", "SHREECEM.NS"),
    ("SRF", "SRF.NS"), ("Sammaan Capital", "SAMMAANCAP.NS"),
    ("Motherson", "MOTHERSON.NS"), ("Shriram Finance", "SHRIRAMFIN.NS"),
    ("Siemens", "SIEMENS.NS"), ("Solar Industries", "SOLARINDS.NS"),
    ("Sona BLW", "SONACOMS.NS"), ("SBI", "SBIN.NS"), ("SAIL", "SAIL.NS"),
    ("Sun Pharma", "SUNPHARMA.NS"), ("Supreme Ind", "SUPREMEIND.NS"),
    ("Suzlon", "SUZLON.NS"), ("Swiggy", "SWIGGY.NS"), ("Syngene", "SYNGENE.NS"),
    ("Tata Consumer", "TATACONSUM.NS"), ("TVS Motor", "TVSMOTOR.NS"),
    ("TCS", "TCS.NS"), ("Tata Elxsi", "TATAELXSI.NS"), ("Tata Motors", "TMCV.NS"),
    ("Tata Power", "TATAPOWER.NS"), ("Tata Steel", "TATASTEEL.NS"),
    ("Tata Tech", "TATATECH.NS"), ("Tech Mahindra", "TECHM.NS"),
    ("Federal Bank", "FEDERALBNK.NS"), ("Indian Hotels", "INDHOTEL.NS"),
    ("Phoenix Mills", "PHOENIXLTD.NS"), ("Titan", "TITAN.NS"),
    ("Torrent Pharma", "TORNTPHARM.NS"), ("Torrent Power", "TORNTPOWER.NS"),
    ("Trent", "TRENT.NS"), ("Tube Investments", "TIINDIA.NS"),
    ("UNO Minda", "UNOMINDA.NS"), ("UPL", "UPL.NS"), ("UltraTech Cement", "ULTRACEMCO.NS"),
    ("Union Bank", "UNIONBANK.NS"), ("United Spirits", "UNITDSPR.NS"),
    ("Varun Beverages", "VBL.NS"), ("Vedanta", "VEDL.NS"),
    ("Vodafone Idea", "IDEA.NS"), ("Voltas", "VOLTAS.NS"),
    ("Waaree Energies", "WAAREEENER.NS"), ("Wipro", "WIPRO.NS"),
    ("Yes Bank", "YESBANK.NS"), ("Zydus Life", "ZYDUSLIFE.NS"),
]

# Cache for daily history to avoid rate limiting
_daily_history_cache = None
_last_history_update = datetime.min
GLOBAL_MARKETS = [
    ("Nifty 50", "^NSEI"), ("Sensex", "^BSESN"), ("Bank Nifty", "^NSEBANK"),
    ("Gift Nifty", "GIFTY=F"), ("Gold", "GC=F"), ("Crude Oil", "CL=F"),
    ("Silver", "SI=F"), ("USD/INR", "USDINR=X"),
    ("S&P 500", "^GSPC"), ("Dow Jones", "^DJI"), ("Nasdaq", "^IXIC"),
    ("FTSE 100", "^FTSE"), ("Nikkei 225", "^N225"), ("Hang Seng", "^HSI"),
    ("DAX", "^GDAXI"), ("Shanghai", "000001.SS"), ("Bitcoin", "BTC-USD")
]

_market_data = [] # Cache for global indices/commodities

# Build symbol -> name map
_SYMBOL_NAME_MAP = {sym.replace(".NS", ""): name for name, sym in FO_STOCKS}

# -- Helpers -----------------------------------------------------------------

def is_market_open():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def data_hash(data):
    """Create hash of key fields for change detection."""
    key = f"{data['curr_close']}|{data['volume']}|{data['change_pct']}|{data['high']}|{data['low']}"
    return hashlib.md5(key.encode()).hexdigest()


def predict_next_day(hist_df):
    """Linear regression on close prices -> next-day prediction."""
    try:
        if len(hist_df) < 10:
            return None
        closes = hist_df["Close"].values[-30:]
        X = np.arange(len(closes)).reshape(-1, 1)
        y = closes
        model = LinearRegression().fit(X, y)
        pred = model.predict([[len(closes)]])[0]
        return round(float(pred), 2)
    except Exception:
        return None


def calculate_ema_angle(data, period=9):
    """Calculate the slope/angle of an EMA over last 5 candles."""
    try:
        if len(data) < period + 5: return 0
        
        # Calculate EMA
        def ema(subset, p):
            if len(subset) < p: return subset[-1]
            multiplier = 2.0 / (p + 1)
            e = np.mean(subset[:p])
            for val in subset[p:]:
                e = (val - e) * multiplier + e
            return e

        # Get last 5 EMA points
        ema_points = []
        for i in range(5, 0, -1):
            subset = data[-(i+period):-i] if i > 1 else data[-period:]
            ema_points.append(ema(subset, period))
        
        # Linear regression for slope
        x = np.arange(len(ema_points)).reshape(-1, 1)
        y = np.array(ema_points)
        model = LinearRegression().fit(x, y)
        slope = model.coef_[0]
        
        # Normalize slope by current price to get a "percent slope"
        # 1% move over 5 candles is roughly what we consider a "strong angle"
        normalized_slope = (slope / data[-1]) * 100
        return normalized_slope
    except Exception:
        return 0

# -- AI Indicator: Entry / SL / Target ------------------------------------
def compute_ai_levels(hist_df, curr_close, high, low, open_price, momentum=0):
    """Compute AI Entry, Stop Loss, Target using RSI, ATR, EMA confluence."""
    try:
        closes = hist_df["Close"].astype(float).values
        highs  = hist_df["High"].astype(float).values
        lows   = hist_df["Low"].astype(float).values

        if len(closes) < 15:
            return None

        # --- ATR(14) ---
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i] - closes[i-1]))
            trs.append(tr)
        atr14 = float(np.mean(trs[-14:])) if len(trs) >= 14 else float(np.mean(trs))

        # --- RSI(14) ---
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = float(np.mean(gains[-14:])) if len(gains) >= 14 else float(np.mean(gains))
        avg_loss = float(np.mean(losses[-14:])) if len(losses) >= 14 else float(np.mean(losses))
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100.0 - (100.0 / (1.0 + rs)), 2)

        # --- EMA(9) & EMA(21) ---
        def ema(data, period):
            if len(data) < period:
                return float(np.mean(data))
            multiplier = 2.0 / (period + 1)
            e = float(np.mean(data[:period]))
            for val in data[period:]:
                e = (float(val) - e) * multiplier + e
            return e

        ema9 = round(ema(closes, 9), 2)
        ema21 = round(ema(closes, 21), 2)

        # --- AI Signal Logic ---
        bullish_ema = ema9 > ema21
        bearish_ema = ema9 < ema21
        oversold = rsi < 40
        overbought = rsi > 70
        near_support = curr_close <= open_price and curr_close <= (low + atr14 * 0.5)
        near_resist  = curr_close >= open_price and curr_close >= (high - atr14 * 0.5)

        reasons = []
        if oversold:
            reasons.append(f"RSI Oversold ({rsi:.0f})")
        if overbought:
            reasons.append(f"RSI Overbought ({rsi:.0f})")
        if bullish_ema:
            reasons.append("EMA9 > EMA21")
        if bearish_ema:
            reasons.append("EMA9 < EMA21")

        # Determine signal
        buy_score = 0
        sell_score = 0
        if oversold: buy_score += 2
        if overbought: sell_score += 2
        if bullish_ema: buy_score += 1
        if bearish_ema: sell_score += 1
        if near_support: buy_score += 1
        if near_resist: sell_score += 1
        if rsi < 50: buy_score += 0.5
        if rsi > 50: sell_score += 0.5

        # --- EMA Angle Strategy ---
        angle9 = calculate_ema_angle(closes, 9)
        angle21 = calculate_ema_angle(closes, 21)
        
        # Determine signal based on EMA 9/21 Cross & Angle
        # Angle > 0.15% per candle is significant (approx 45 deg in trading terms)
        ema_cross_up = ema9 > ema21 and angle9 > 0.15
        ema_cross_dn = ema9 < ema21 and angle9 < -0.15

        if ema_cross_up or (buy_score > sell_score and buy_score >= 2):
            ai_signal = "BUY"
            # SL below EMA 21 or previous candle's low
            # Use data_lows to avoid shadowing from internal loop variables
            data_lows = hist_df["Low"].values
            sl = min(ema21, float(np.min(data_lows[-3:])))
            entry = round(curr_close, 2)
            
            # Ensure SL is below entry
            if sl >= entry:
                sl = entry - (atr14 * 1.5)
            
            risk = entry - sl
            # Ensure minimum risk buffer
            min_risk = atr14 * 1.0
            if risk < min_risk:
                sl = entry - min_risk
                risk = min_risk
            
            target = round(entry + (risk * 2.0), 2) # Strict 1:2 RR
            sl_dist = risk
            tgt_dist = risk * 2.0
        elif ema_cross_dn or (sell_score > buy_score and sell_score >= 2):
            ai_signal = "SELL"
            # SL above EMA 21 or previous candle's high
            data_highs = hist_df["High"].values
            sl = max(ema21, float(np.max(data_highs[-3:])))
            entry = round(curr_close, 2)
            
            # Ensure SL is above entry
            if sl <= entry:
                sl = entry + (atr14 * 1.5)
                
            risk = sl - entry
            min_risk = atr14 * 1.0
            if risk < min_risk:
                sl = entry + min_risk
                risk = min_risk

            target = round(entry - (risk * 2.0), 2) # Strict 1:2 RR
            sl_dist = risk
            tgt_dist = risk * 2.0
        else:
            ai_signal = "NEUTRAL"
            sl_dist = round(atr14 * 1.5, 2)
            tgt_dist = round(atr14 * 3.0, 2)
            entry = round(curr_close, 2)
            sl = round(curr_close - sl_dist, 2)
            target = round(curr_close + tgt_dist, 2)

        rr = round(tgt_dist / sl_dist, 2) if sl_dist > 0 else 0
        if not reasons:
            reasons.append(f"RSI Neutral ({rsi:.0f})")

        # --- Trend Reversal & Divergence Logic ---
        ai_trend = "Neutral"
        ai_trend_reason = "--"
        ai_reversal_timeframe = "N/A"
        try:
            if len(closes) >= 30:
                close_s = pd.Series(closes)
                delta = close_s.diff()
                gain = delta.where(delta > 0, 0).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs_s = gain / loss
                rsi_s = 100 - (100 / (1 + rs_s))
                
                recent_c = closes[-20:]
                recent_r = rsi_s.values[-20:]
                
                l_pts = []
                h_pts = []
                for i in range(1, 19):
                    if recent_c[i] <= recent_c[i-1] and recent_c[i] <= recent_c[i+1]:
                        l_pts.append(i)
                    if recent_c[i] >= recent_c[i-1] and recent_c[i] >= recent_c[i+1]:
                        h_pts.append(i)
                
                curr_i = 19
                if l_pts:
                    last_low = l_pts[-1]
                    if recent_c[curr_i] < recent_c[last_low] and recent_r[curr_i] > recent_r[last_low] + 2:
                        ai_trend = "Bullish Reversal"
                        ai_trend_reason = f"Bullish Divergence: Price Lower & RSI Higher"
                        ai_reversal_timeframe = f"{curr_i - last_low} Days"
                
                if h_pts and ai_trend == "Neutral":
                    last_high = h_pts[-1]
                    if recent_c[curr_i] > recent_c[last_high] and recent_r[curr_i] < recent_r[last_high] - 2:
                        ai_trend = "Bearish Reversal"
                        ai_trend_reason = f"Bearish Divergence: Price Higher & RSI Lower"
                        ai_reversal_timeframe = f"{curr_i - last_high} Days"
                
                if ai_trend == "Neutral":
                    prev_ema9 = ema(closes[:-1], 9)
                    if closes[-2] < prev_ema9 and closes[-1] > ema9 and rsi < 50:
                        ai_trend = "Bullish Reversal"
                        ai_trend_reason = "Crossed above EMA(9) from low RSI"
                        ai_reversal_timeframe = "1 Day Cut"
                    elif closes[-2] > prev_ema9 and closes[-1] < ema9 and rsi > 50:
                        ai_trend = "Bearish Reversal"
                        ai_trend_reason = "Crossed below EMA(9) from high RSI"
                        ai_reversal_timeframe = "1 Day Cut"
        except Exception as e:
            pass

        # --- Intraday Options Setup ---
        ai_option_setup = "None"
        ai_target_date = "--"
        ai_trade_timing = "--"
        
        if ai_trend in ["Bullish Reversal", "Bearish Reversal"]:
            ai_target_date = "Intraday (Today)"
            if abs(momentum) >= 0.5:
                # Nearest strike calculation
                if curr_close < 200: step = 5
                elif curr_close < 500: step = 10
                elif curr_close < 2000: step = 20
                elif curr_close < 5000: step = 50
                else: step = 100
                
                strike = round(curr_close / step) * step
                opt_type = "CE" if ai_trend == "Bullish Reversal" else "PE"
                ai_option_setup = f"{strike} {opt_type}"
                
                # Determine intelligent entry timing based on current local time
                now = datetime.now()
                market_time_dec = now.hour + now.minute / 60.0
                if 9.25 <= market_time_dec < 10.0:
                    ai_trade_timing = "Morning Momentum (Execute Now)"
                elif 10.0 <= market_time_dec < 13.5:
                    ai_trade_timing = "Mid-Day (Entry Valid)"
                elif 13.5 <= market_time_dec < 15.0:
                    ai_trade_timing = "Afternoon Breakout (Execute Now)"
                elif market_time_dec >= 15.0:
                    ai_trade_timing = "Market Closing (Do Not Enter)"
                else:
                    ai_trade_timing = "Pre-Market (Wait for Open)"
            else:
                ai_option_setup = "Low Momentum (Skip Options)"
                ai_trade_timing = "Awaiting Momentum Surge"

        # --- 10m Indicators (Wait for ten_min_df) ---
        return {
            "ai_signal": ai_signal,
            "ai_entry": entry,
            "ai_sl": sl,
            "ai_target": target,
            "ai_rsi": round(rsi, 1),
            "ai_atr": round(atr14, 2),
            "ai_ema9": ema9,
            "ai_ema21": ema21,
            "ai_rr": rr,
            "ai_reason": " | ".join(reasons),
            "ai_trend": ai_trend,
            "ai_trend_reason": ai_trend_reason,
            "ai_reversal_timeframe": ai_reversal_timeframe,
            "ai_option_setup": ai_option_setup,
            "ai_target_date": ai_target_date,
            "ai_trade_timing": ai_trade_timing
        }
    except Exception as e:
        print(f"[AI] Error computing levels: {e}")
        return None

def compute_intraday_indicators(five_min_df):
    """Compute 10-minute based EMAs and RSI using resampled 5m data.
    Also computes intraday swing high/low for tight SL calculation."""
    try:
        if five_min_df is None or len(five_min_df) < 6:
            return {}

        # FIX: pandas 2.2+ renamed '10T' → '10min' (and '5T'→'5min', etc.)
        # Use try/except to support both old and new pandas versions
        try:
            ten_min_df = five_min_df.resample('10min').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()
        except ValueError:
            ten_min_df = five_min_df.resample('10T').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()

        if len(ten_min_df) < 3:
            return {}

        closes = ten_min_df["Close"].astype(float).values

        def ema(data, period):
            if len(data) < period:
                # Not enough bars yet — use simple mean as best approximation
                return float(np.mean(data))
            multiplier = 2.0 / (period + 1)
            e = float(np.mean(data[:period]))
            for val in data[period:]:
                e = (float(val) - e) * multiplier + e
            return e

        n = len(closes)
        # EMAs — gracefully degrade when fewer bars available intraday
        ema20  = round(ema(closes, min(20,  n)), 2)
        ema50  = round(ema(closes, min(50,  n)), 2)
        ema100 = round(ema(closes, min(100, n)), 2)
        ema150 = round(ema(closes, min(150, n)), 2)
        ema200 = round(ema(closes, min(200, n)), 2)

        # RSI(14)
        deltas   = np.diff(closes)
        gains    = np.where(deltas > 0, deltas, 0)
        losses   = np.where(deltas < 0, -deltas, 0)
        period   = min(14, len(gains))
        avg_gain = float(np.mean(gains[-period:])) if period > 0 else 0
        avg_loss = float(np.mean(losses[-period:])) if period > 0 else 0
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs  = avg_gain / avg_loss
            rsi = round(100.0 - (100.0 / (1.0 + rs)), 2)

        # Intraday swing SL: last 6 bars (~1 hour), fallback to all bars
        lookback = min(6, n)
        recent_lows   = ten_min_df["Low"].astype(float).values[-lookback:]
        recent_highs  = ten_min_df["High"].astype(float).values[-lookback:]
        intraday_swing_low  = round(float(np.min(recent_lows)),  2)
        intraday_swing_high = round(float(np.max(recent_highs)), 2)

        return {
            "ema20_10m":  ema20,  "ema50_10m":  ema50,
            "ema100_10m": ema100, "ema150_10m": ema150, "ema200_10m": ema200,
            "rsi_10m": rsi,
            "intraday_swing_low":  intraday_swing_low,
            "intraday_swing_high": intraday_swing_high,
        }
    except Exception as e:
        print(f"[AI 10m] Error: {e}")
        return {}


def rsi(prices, period=14):
    """Calculates Relative Strength Index (RSI)."""
    if len(prices) < period + 1:
        return 50
    deltas = np.diff(prices)
    up = np.where(deltas > 0, deltas, 0)
    down = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(up[:period])
    avg_loss = np.mean(down[:period])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    current_rsi = 100 - (100 / (1 + rs))
    
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + up[i]) / period
        avg_loss = (avg_loss * (period - 1) + down[i]) / period
        if avg_loss == 0:
            current_rsi = 100
        else:
            rs = avg_gain / avg_loss
            current_rsi = 100 - (100 / (1 + rs))
            
    return current_rsi


def detect_liquidity_sweep(current_data):
    """Detect PDH/PDL liquidity sweep setups — BUY (PDL swept, recovering), SELL (PDH swept, rejecting), WATCH (near level)."""
    try:
        curr_close = float(current_data.get("curr_close") or 0)
        today_high = float(current_data.get("high")       or 0)
        today_low  = float(current_data.get("low")        or 0)
        today_open = float(current_data.get("open")       or curr_close)
        prev_high  = float(current_data.get("prev_high")  or 0)
        prev_low   = float(current_data.get("prev_low")   or 0)
        change_pct = float(current_data.get("change_pct") or 0)
        rel_vol    = float(current_data.get("rel_volume") or 1.0)
        momentum   = float(current_data.get("momentum")   or 0)

        if not all([curr_close, prev_high, prev_low]):
            return {"sweep_type":"NONE","sweep_side":None,"sweep_detail":"Insufficient data","pdh":prev_high,"pdl":prev_low}

        tol_l = prev_low  * 0.0005
        tol_h = prev_high * 0.0005

        # BUY SWEEP — sell-side liquidity grabbed, price recovering above PDL
        if (today_low < (prev_low - tol_l) and curr_close > prev_low
                and (change_pct > 0 or curr_close > today_open) and rel_vol >= 1.5):
            depth     = round(prev_low - today_low, 2)
            depth_pct = round(depth / prev_low * 100, 2)
            entry = round(curr_close, 2)
            sl    = round(max(today_low - max(depth*0.25, prev_low*0.003), entry*0.985), 2)
            risk  = round(entry - sl, 2) or round(entry*0.005,2)
            tgt   = round(entry + risk*2.0, 2)
            strong = rel_vol >= 2.5 and momentum > 0.1 and curr_close > today_open
            return {"sweep_type": "STRONG BUY SWEEP" if strong else "MODERATE BUY SWEEP",
                    "sweep_side":"BUY","sweep_detail":f"Swept PDL ₹{prev_low} by {depth_pct}% — recovered. Vol {rel_vol:.1f}x",
                    "sweep_entry":entry,"sweep_sl":sl,"sweep_target":tgt,
                    "sweep_depth":depth,"sweep_depth_pct":depth_pct,"sweep_rvol":rel_vol,
                    "pdl":round(prev_low,2),"pdh":round(prev_high,2)}

        # SELL SWEEP — buy-side liquidity grabbed, price rejecting below PDH
        if (today_high > (prev_high + tol_h) and curr_close < prev_high
                and (change_pct < 0 or curr_close < today_open) and rel_vol >= 1.5):
            depth     = round(today_high - prev_high, 2)
            depth_pct = round(depth / prev_high * 100, 2)
            entry = round(curr_close, 2)
            sl    = round(min(today_high + max(depth*0.25, prev_high*0.003), entry*1.015), 2)
            risk  = round(sl - entry, 2) or round(entry*0.005,2)
            tgt   = round(entry - risk*2.0, 2)
            strong = rel_vol >= 2.5 and momentum < -0.1 and curr_close < today_open
            return {"sweep_type": "STRONG SELL SWEEP" if strong else "MODERATE SELL SWEEP",
                    "sweep_side":"SELL","sweep_detail":f"Swept PDH ₹{prev_high} by {depth_pct}% — rejected. Vol {rel_vol:.1f}x",
                    "sweep_entry":entry,"sweep_sl":sl,"sweep_target":tgt,
                    "sweep_depth":depth,"sweep_depth_pct":depth_pct,"sweep_rvol":rel_vol,
                    "pdl":round(prev_low,2),"pdh":round(prev_high,2)}

        # WATCH ZONES — approaching key level, not yet confirmed
        if prev_low  > 0 and abs(curr_close - prev_low)  / prev_low  < 0.003:
            return {"sweep_type":"WATCH PDL","sweep_side":None,
                    "sweep_detail":f"Approaching PDL ₹{round(prev_low,2)} — watch for sweep+reversal",
                    "pdl":round(prev_low,2),"pdh":round(prev_high,2)}
        if prev_high > 0 and abs(curr_close - prev_high) / prev_high < 0.003:
            return {"sweep_type":"WATCH PDH","sweep_side":None,
                    "sweep_detail":f"Approaching PDH ₹{round(prev_high,2)} — watch for sweep+rejection",
                    "pdl":round(prev_low,2),"pdh":round(prev_high,2)}

        return {"sweep_type":"NONE","sweep_side":None,"sweep_detail":"No sweep detected",
                "pdl":round(prev_low,2),"pdh":round(prev_high,2)}
    except Exception as e:
        return {"sweep_type":"NONE","sweep_side":None,"sweep_detail":str(e)}


def detect_perfect_setup(symbol, ten_min_df, current_data):
    """
    High-Conviction Institutional Impulse Strategy:
    1. Trend: EMA 20 > EMA 50 > EMA 100 > EMA 200 (10m)
    2. Volume Catalyst: 4.0x Volume surge (Institutional Footprint)
    3. OI Catalyst: > 5% OI Buildup (Aggressive Positioning)
    4. Pivot Breakout: Price breaking recent 3-bar high/low
    """
    try:
        if ten_min_df is None or len(ten_min_df) < 5:   # FIX: was 50 — fails all morning
            return {"is_perfect": False, "reason": "Gathering Market Context..."}

        e20, e50, e100, e200 = current_data.get("ema20_10m"), current_data.get("ema50_10m"), current_data.get("ema100_10m"), current_data.get("ema200_10m")
        curr_p = current_data.get("curr_close")
        rvol = current_data.get("rel_volume", 1.0)
        oi_pct = current_data.get("oi", {}).get("avgInOI", 0)
        vols = ten_min_df["Volume"].astype(float).values
        highs = ten_min_df["High"].astype(float).values
        lows = ten_min_df["Low"].astype(float).values

        if not all([e20, e50, e100, e200, curr_p]):
            return {"is_perfect": False, "reason": "Waiting for Indicators..."}

        # 1. Structural Trend Confluence (EMA Tsunami)
        bullish_stack = curr_p > e20 > e50 > e100 > e200
        bearish_stack = curr_p < e20 < e50 < e100 < e200
        
        if not (bullish_stack or bearish_stack):
            return {"is_perfect": False, "reason": "No Trend Alignment"}

        # 2. Institutional Volume Catalyst (4x Surge)
        vol_catalyst_ok = rvol >= 4.0

        # 3. Position Aggression (OI Buildup)
        oi_catalyst_ok = abs(oi_pct) >= 5.0

        # 4. Micro-Pivot Breakout
        pivot_high = np.max(highs[-4:-1])
        pivot_low = np.min(lows[-4:-1])
        breakout_ok = (bullish_stack and curr_p > pivot_high) or (bearish_stack and curr_p < pivot_low)

        is_perfect = (bullish_stack or bearish_stack) and vol_catalyst_ok and oi_catalyst_ok and breakout_ok
        
        reasons = []
        if vol_catalyst_ok: reasons.append("Inst. Vol (4x)")
        if oi_catalyst_ok: reasons.append("Aggressive OI")
        if breakout_ok: reasons.append("Trend Breakout")

        setup_type = "None"
        if is_perfect:
            setup_type = "INSTITUTIONAL IMPULSE"

        return {
            "is_perfect": bool(is_perfect),
            "setup_score": int(sum([vol_catalyst_ok, oi_catalyst_ok, breakout_ok])),
            "reason": " + ".join(reasons) if reasons else "Scanning for Institutions...",
            "setup_type": setup_type,
            "swing_level": float(np.min(lows[-5:]) if bullish_stack else np.max(highs[-5:]))
        }
    except Exception as e:
        print(f"[SETUP] Error: {e}")
        return {"is_perfect": False, "reason": f"Error: {e}"}


# Mapping dictionary for Yahoo symbol -> TradingView symbol
TV_SYMBOL_MAP = {
    "BAJAJ-AUTO": "BAJAJ_AUTO",
    "LTIM": "LTM",
    "TATAMOTORS": "TMCV"
}

# -- Trade Manager for Automated "Trade of the Day" ---------------------------

def calculate_trade_levels(stock):
    """Calculate Entry, SL, Target using technical swing levels or ATR fallback."""
    try:
        entry = stock["curr_close"]
        ps = stock.get("perfect_setup", {})
        swing_level = ps.get("swing_level")
        
        # Determine side
        side = "BUY"
        if stock.get("signal") == "SELL" or stock.get("ai_signal") == "SELL" or "Bearish" in ps.get("setup_type", ""):
            side = "SELL"

        if swing_level:
            # Use technical swing level with slightly wider buffer (0.15%)
            buffer = entry * 0.0015
            if side == "BUY":
                # Entry 100, Swing 99.5. SL = 99.35.
                sl = round(swing_level - buffer, 2)
                # Ensure SL is not > 2% for safety
                if (entry - sl) / entry > 0.02:
                    sl = round(entry * 0.98, 2)
                
                risk = entry - sl
                target = round(entry + (risk * 2.0), 2)
            else:
                sl = round(swing_level + buffer, 2)
                if (sl - entry) / entry > 0.02:
                    sl = round(entry * 1.02, 2)
                
                risk = sl - entry
                target = round(entry - (risk * 2.0), 2)
        else:
            # Fallback to ATR-based logic
            daily_atr = stock.get("ai_atr", entry * 0.01)
            scaled_atr = daily_atr * 0.25 
            sl_dist = scaled_atr * 1.5
            tgt_dist = sl_dist * 2.0
            
            if side == "BUY":
                sl = round(entry - sl_dist, 2)
                target = round(entry + tgt_dist, 2)
            else:
                sl = round(entry + sl_dist, 2)
                target = round(entry - tgt_dist, 2)

        return {
            "entry": entry,
            "sl": sl,
            "target": target,
            "side": side,
            "shares": 10,
            "status": "OPEN",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[TRADE] Error calculating levels: {e}")
        return None

def update_automated_trade(all_stocks):
    """Main logic: select trade if none exists, or update active trade."""
    global _active_trade_store
    
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    # 1. Check for active trade
    active = None
    if MONGO_OK:
        active = trade_state_col.find_one({"status": "OPEN"})
        # Migration/Safety Check: Reset any trade with unrealistic target (> 4% from entry)
        if active:
            entry_p = active.get("entry", 1)
            tgt_p = active.get("target", 1)
            dist_p = abs(tgt_p - entry_p) / entry_p * 100
            if dist_p > 4:
                print(f"[TRADE] Resetting unrealistic active trade for {active['symbol']} (Dist: {dist_p:.1f}%)")
                trade_state_col.delete_one({"_id": active["_id"]})
                active = None
    else:
        active = _active_trade_store
        if active:
            entry_p = active.get("entry", 1)
            tgt_p = active.get("target", 1)
            dist_p = abs(tgt_p - entry_p) / entry_p * 100
            if dist_p > 4:
                _active_trade_store = None
                active = None

    # 2. If no active trade, check if we've already traded today
    if not active:
        if MONGO_OK:
            already_done = journal_col.find_one({"date": today_str})
        else:
            already_done = any(t["date"] == today_str for t in _journal_store)
        
        if already_done:
            return # Only one trade per day
            
        # Do not initiate new trades after 2:30 PM (14:30)
        if now.hour > 14 or (now.hour == 14 and now.minute >= 30):
            return
            
        # 3. Try to pick a stock from watchlist
        watchlist = [s for s in all_stocks if s.get("watchlist_entry_time")]
        if not watchlist:
            return
            
        # AI Selection: Rank by Momentum, Volume Surge, and OI Buildup
        def rank_score(s):
            mom = s.get("momentum", 0)
            rvol = s.get("rel_volume", 1.0)
            oi_pct = s.get("oi", {}).get("avgInOI", 0)
            is_perfect = s.get("perfect_setup", {}).get("is_perfect")
            
            # 1. Exclusive Qualification: Must have Institutional Presence
            if not is_perfect:
                return -100

            # 2. Strict Confidence Multipliers
            # Scoring: 30% Vol Surge, 30% OI Surge, 40% Velocity
            score = (rvol * 3) + (abs(oi_pct) * 0.3) + (abs(mom) * 4)
            return score
            
        watchlist.sort(key=rank_score, reverse=True)
        
        # Priority 1: Perfect Setups
        perfect_candidates = [s for s in watchlist if s.get("perfect_setup", {}).get("is_perfect")]
        if perfect_candidates:
            perfect_candidates.sort(key=lambda x: x.get("perfect_setup", {}).get("setup_score", 0), reverse=True)
            top_stock = perfect_candidates[0]
        elif watchlist and rank_score(watchlist[0]) >= 0:
            top_stock = watchlist[0]
        else:
            return
            
        trade = calculate_trade_levels(top_stock)
        if trade:
            trade["symbol"] = top_stock["symbol"]
            trade["name"] = top_stock["name"]
            
            # Generate Selection Reason
            mom = top_stock.get('momentum', 0)
            rvol = top_stock.get('rel_volume', 1.0)
            oi_pct = top_stock.get('oi', {}).get('avgInOI', 0)
            side = trade["side"]
            
            is_perfect = top_stock.get("perfect_setup", {}).get("is_perfect")
            verb = "Bullish" if side == "BUY" else "Bearish"
            
            if is_perfect:
                reason = f"★ PERFECT {verb.upper()} SETUP: {top_stock['perfect_setup']['reason']}"
            else:
                reason = f"Strong {verb} Setup: Momentum ({'+' if mom > 0 else ''}{mom:.2f}%)"
                if rvol > 1.2:
                    reason += f" + Volume Surge ({rvol}x)"
                if abs(oi_pct) > 2:
                    reason += f" + OI Buildup ({oi_pct}%)"
                
            trade["selection_reason"] = reason
            
            if MONGO_OK:
                trade_state_col.insert_one(trade)
            else:
                _active_trade_store = trade
            print(f"[TRADE] Automatically entered {trade['side']} trade for {trade['symbol']} at {trade['entry']}. Reason: {reason}")
            return

    # 4. Update Active Trade performance
    if active:
        # Find latest data for this stock
        latest = next((s for s in all_stocks if s["symbol"] == active["symbol"]), None)
        if not latest:
            return
            
        curr_p = latest["curr_close"]
        side = active["side"]
        entry = active["entry"]
        sl = active["sl"]
        tgt = active["target"]
        shares = active["shares"]

        # Calculate P/L
        if side == "BUY":
            p_l = (curr_p - entry) * shares
            hit_sl = curr_p <= sl
            hit_tgt = curr_p >= tgt
        else:
            p_l = (entry - curr_p) * shares
            hit_sl = curr_p >= sl
            hit_tgt = curr_p <= tgt

        # Update active trade in DB
        update_doc = {
            "curr_price": curr_p,
            "p_l": round(p_l, 2),
            "p_l_pct": round((p_l / (entry * shares)) * 100, 2)
        }
        
        # Check for exit conditions
        # EOD: Close at 14:30 (2:30 PM)
        is_eod = now.hour > 14 or (now.hour == 14 and now.minute >= 30)
        
        exit_triggered = False
        exit_reason = ""
        if hit_sl:
            exit_triggered = True
            exit_reason = "STOP LOSS HIT"
        elif hit_tgt:
            exit_triggered = True
            exit_reason = "TARGET HIT"
        elif is_eod:
            exit_triggered = True
            exit_reason = "EOD SQUARE OFF"

        if exit_triggered:
            active.update(update_doc)
            active["status"] = "CLOSED"
            active["exit_price"] = curr_p
            active["exit_reason"] = exit_reason
            active["exit_time"] = now.isoformat()
            
            # Save to Journal
            if MONGO_OK:
                journal_col.insert_one(active)
                trade_state_col.delete_one({"_id": active["_id"]})
            else:
                _journal_store.append(active)
                _active_trade_store = None
            print(f"[TRADE] Closed trade for {active['symbol']} ({exit_reason}). P/L: {active['p_l']}")
        else:
            # Just update live state
            if MONGO_OK:
                trade_state_col.update_one({"_id": active["_id"]}, {"$set": update_doc})
            else:
                active.update(update_doc)
                _active_trade_store = active

def process_stock_data(name, symbol, hist_df, tv_data, ten_min_df=None):
    """Process a single stock using its pre-fetched daily history, 10m history and live TV data."""
    try:
        base_sym = symbol.replace(".NS", "")
        if hist_df is None or hist_df.empty or len(hist_df) < 2:
            return None

        # Clean history dataframe (drop NaNs)
        hist_df = hist_df.dropna(subset=["Close"])
        if len(hist_df) < 2:
             return None

        # --- Use 60-day daily history ---
        prev_close  = float(hist_df["Close"].iloc[-2])
        prev_open   = float(hist_df["Open"].iloc[-2])
        prev_high   = float(hist_df["High"].iloc[-2])
        prev_low    = float(hist_df["Low"].iloc[-2])
        prev_volume = int(hist_df["Volume"].iloc[-2])

        # --- Real-time price from TradingView ---
        tv_sym = TV_SYMBOL_MAP.get(base_sym, base_sym)
        tv_rec = tv_data.get(f"NSE:{tv_sym}")

        if tv_rec:
             # TV columns: ["name", "close", "change", "open", "high", "low", "volume"]
             curr_close = float(tv_rec[1])
             change_pct = round(float(tv_rec[2]), 2)
             open_price = float(tv_rec[3])
             high       = float(tv_rec[4])
             low        = float(tv_rec[5])
             volume     = int(tv_rec[6])
        else:
             # Intelligent Fallback: Try 10m intraday data first if Today's bar is available
             found_intraday = False
             if ten_min_df is not None and not ten_min_df.empty:
                 today_str = datetime.now().strftime("%Y-%m-%d")
                 today_data = ten_min_df[ten_min_df.index.strftime('%Y-%m-%d') == today_str]
                 if not today_data.empty:
                     latest = today_data.iloc[-1]
                     curr_close = float(latest["Close"])
                     open_price = float(today_data.iloc[0]["Open"])
                     high       = float(today_data["High"].max())
                     low        = float(today_data["Low"].min())
                     volume     = int(today_data["Volume"].sum())
                     change_pct = round((curr_close - prev_close) / prev_close * 100, 2) if prev_close else 0
                     found_intraday = True

             if not found_intraday:
                 # Fallback to current daily bar (might be stale if yf is slow)
                 curr_close = float(hist_df["Close"].iloc[-1])
                 change_pct = round((curr_close - prev_close) / prev_close * 100, 2) if prev_close else 0
                 open_price = float(hist_df["Open"].iloc[-1])
                 high       = float(hist_df["High"].iloc[-1])
                 low        = float(hist_df["Low"].iloc[-1])
                 volume     = int(hist_df["Volume"].iloc[-1])


        pred       = predict_next_day(hist_df)

        # Backtest: check last 20 days for +/-2% signals
        backtest = []
        for i in range(2, min(22, len(hist_df))):
            p = float(hist_df["Close"].iloc[i-2])
            c = float(hist_df["Close"].iloc[i-1])
            n = float(hist_df["Close"].iloc[i])
            chg = (c - p) / p * 100
            if abs(chg) >= 2:
                outcome = round((n - c) / c * 100, 2)
                backtest.append({
                    "date": hist_df.index[i-1].strftime("%Y-%m-%d"),
                    "signal": "BUY" if chg > 0 else "SELL",
                    "change_pct": round(chg, 2),
                    "next_day_outcome": outcome,
                    "profitable": (chg > 0 and outcome > 0) or (chg < 0 and outcome < 0)
                })

        bt_total = len(backtest)
        bt_wins  = sum(1 for b in backtest if b["profitable"])
        bt_avg   = round(sum(b["next_day_outcome"] for b in backtest) / bt_total, 2) if bt_total > 0 else 0

        # --- Resistance & Support (Standard Pivot Points) ---
        # Based on previous day's High, Low, Close
        P = (prev_high + prev_low + prev_close) / 3
        R1 = (2 * P) - prev_low
        S1 = (2 * P) - prev_high

        # --- Volume Analytics ---
        avg_vol = float(hist_df["Volume"].tail(20).mean()) if len(hist_df) >= 2 else 0
        rel_vol = round(volume / avg_vol, 2) if avg_vol > 0 else 1.0

        result = {
            "name": name,
            "symbol": symbol.replace(".NS", ""),
            "prev_close": round(prev_close, 2),
            "prev_open": round(prev_open, 2),
            "prev_high": round(prev_high, 2),
            "prev_low": round(prev_low, 2),
            "prev_volume": prev_volume,
            "curr_close": round(float(curr_close), 2) if curr_close is not None else 0,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": volume,
            "avg_volume": round(avg_vol, 0),
            "rel_volume": rel_vol,
            "change_pct": round(float(change_pct), 2) if change_pct is not None else 0,
            "timestamp": datetime.now().isoformat(),
            "alerted": abs(change_pct) >= 2
        }
        
        # Add momentum BEFORE using it in AI levels
        result["momentum"] = update_momentum(result["symbol"], result["curr_close"])
        
        # --- Add AI Indicator levels (Unified Signal Logic) ---
        ai = compute_ai_levels(hist_df, curr_close, high, low, open_price, result["momentum"])
        if ai:
            result.update(ai)
        else:
            result.update({
                "ai_signal": "--", "ai_entry": None, "ai_sl": None,
                "ai_target": None, "ai_rsi": None, "ai_atr": None,
                "ai_ema9": None, "ai_ema21": None, "ai_rr": None, "ai_reason": "--",
                "ai_trend": "Neutral", "ai_trend_reason": "--",
                "ai_reversal_timeframe": "N/A", "ai_option_setup": "None", "ai_target_date": "--", "ai_trade_timing": "--"
            })
            
        # Add 10-minute Indicators
        intraday = compute_intraday_indicators(ten_min_df)
        if intraday:
            result.update(intraday)
        else:
            result.update({
                "ema20_10m": None, "ema50_10m": None, "ema100_10m": None,
                "ema150_10m": None, "ema200_10m": None, "rsi_10m": None
            })

        # --- Master Signal Unification ---
        # 1. Perfect Setup (Institutional Impulse) has the highest priority
        result["perfect_setup"] = detect_perfect_setup(result["symbol"], ten_min_df, result)
        is_perfect = result["perfect_setup"]["is_perfect"]
        
        # 2. Derive Master Signal
        if is_perfect:
            result["signal"] = "STRONG BUY" if result["perfect_setup"]["setup_type"] == "INSTITUTIONAL IMPULSE" else "BUY"
            result["alerted"] = True
            result["alert_msg"] = f"PERFECT SETUP: {result['perfect_setup']['setup_type']}"
        elif result.get("ai_signal") != "NEUTRAL" and result.get("ai_signal") != "--":
            # AI Signal is secondary, check for anti-contradiction (momentum vs RSI)
            ai_sig = result["ai_signal"]
            # If price up 2% but AI says SELL, keep as NEUTRAL/HOLD or OVERBOUGHT instead of fighting the trend
            if ai_sig == "SELL" and result["change_pct"] >= 1.5:
                result["signal"] = "OVEREXTENDED"
            elif ai_sig == "BUY" and result["change_pct"] <= -1.5:
                result["signal"] = "OVERSOLD"
            else:
                result["signal"] = ai_sig
        else:
            # Fallback to legacy percent change only if above 2%
            result["signal"] = "WATCH" if abs(result["change_pct"]) >= 2 else "NEUTRAL"
        result["data_hash"] = data_hash(result)
        
        if abs(result["momentum"]) >= 0.5:
             result["alerted"] = True # Trigger alert for high momentum
        
        # Add OI Alert tracking
        base_sym = symbol.replace(".NS", "")
        oi_data = _oi_spurts_cache.get(base_sym)
        if oi_data:
            result["oi"] = oi_data
            oi_pct = oi_data.get("avgInOI", 0)
            
            # Determine OI Action
            price_chg = result["change_pct"]
            if oi_pct > 0 and price_chg > 0:
                result["oi_action"] = "Long Buildup"
            elif oi_pct > 0 and price_chg < 0:
                result["oi_action"] = "Short Buildup"
            elif oi_pct < 0 and price_chg < 0:
                result["oi_action"] = "Long Unwinding"
            elif oi_pct < 0 and price_chg > 0:
                result["oi_action"] = "Short Covering"
            else:
                result["oi_action"] = "Neutral"

            if oi_pct >= 5.0:
                result["alerted"] = True
                result["alert_msg"] = f"OI SURGE +{oi_pct}%"
            elif oi_pct <= -5.0:
                result["alerted"] = True
                result["alert_msg"] = f"OI DROP {oi_pct}%"
        else:
              result["oi_action"] = "Neutral"

        # Add Strike-level OI Details
        result["oi_strikes"] = _oi_contracts_cache.get(base_sym, [])
        if result["oi_strikes"]:
            # Pick top strike for the main table
            result["top_oi_strike"] = result["oi_strikes"][0]["strike"]
        else:
            result["top_oi_strike"] = "--"

        # --- Latch Signal Timing & Levels ---
        sym = result["symbol"]
        prev_state = _stock_state_cache_v2.get(sym, {"trend": "Neutral", "signal_time": None, "latched_levels": None})

        curr_signal = result.get("signal", "NEUTRAL")
        curr_side = "BUY" if "BUY" in curr_signal else ("SELL" if "SELL" in curr_signal else None)

        latched = prev_state.get("latched_levels")

        if latched and curr_side and latched.get("side") == curr_side:
            # ── LOCKED: signal still active on same side — always serve latched values ──
            # BUG FIX: previous code only applied latched values in one branch;
            # the "same side still active" else-branch never wrote them into result.
            result["ai_entry"]       = latched["entry"]
            result["ai_sl"]          = latched["sl"]
            result["ai_target"]      = latched["target"]
            result["ai_rr"]          = 2.0
            result["ai_signal_time"] = prev_state["signal_time"]
            result["entry_locked"]   = True   # flag for frontend to show lock icon

        elif curr_side:
            # ── NEW SIGNAL: latch fresh levels right now ─────────────────────────────
            signal_time = datetime.now().strftime("%H:%M")   # IST HH:MM for display

            entry = round(result["curr_close"], 2)

            # Prefer intraday swing SL (tight, realistic) over daily ATR
            swing_low  = result.get("intraday_swing_low")
            swing_high = result.get("intraday_swing_high")

            if curr_side == "BUY":
                if swing_low and swing_low < entry:
                    raw_sl = swing_low - (entry * 0.001)   # 0.1% below swing low
                else:
                    raw_sl = entry - (entry * 0.008)        # fallback: 0.8% below entry
                # Hard cap: SL never more than 1.5% below entry (intraday rule)
                min_sl = entry * 0.985
                sl = round(max(raw_sl, min_sl), 2)
                risk   = round(entry - sl, 2)
                target = round(entry + risk * 2.0, 2)
            else:  # SELL
                if swing_high and swing_high > entry:
                    raw_sl = swing_high + (entry * 0.001)
                else:
                    raw_sl = entry + (entry * 0.008)
                # Hard cap: SL never more than 1.5% above entry
                max_sl = entry * 1.015
                sl = round(min(raw_sl, max_sl), 2)
                risk   = round(sl - entry, 2)
                target = round(entry - risk * 2.0, 2)

            if risk <= 0:
                risk = round(entry * 0.005, 2)   # absolute minimum 0.5%
                sl     = round(entry - risk if curr_side == "BUY" else entry + risk, 2)
                target = round(entry + risk * 2.0 if curr_side == "BUY" else entry - risk * 2.0, 2)

            new_latched = {"side": curr_side, "entry": entry, "sl": sl, "target": target}
            _stock_state_cache_v2[sym] = {
                "trend": curr_side,
                "signal_time": signal_time,
                "latched_levels": new_latched,
            }
            result["ai_entry"]       = entry
            result["ai_sl"]          = sl
            result["ai_target"]      = target
            result["ai_rr"]          = 2.0
            result["ai_signal_time"] = signal_time
            result["entry_locked"]   = True

        else:
            # Signal gone — reset latch
            _stock_state_cache_v2[sym] = {"trend": "Neutral", "signal_time": None, "latched_levels": None}
            result["ai_signal_time"] = None
            result["entry_locked"]   = False
              
        # Add Sector
        result["sector"] = get_sector(result["symbol"])

        # --- Liquidity Sweep Detection ---
        sweep = detect_liquidity_sweep(result)
        result["liquidity_sweep"] = sweep

        # Promote sweep signal to master signal
        if sweep.get("sweep_side") == "BUY":
            if result.get("signal") not in ("STRONG BUY",):
                result["signal"] = "STRONG BUY" if "STRONG" in sweep.get("sweep_type","") else "BUY"
            if not result.get("ai_entry"):
                result["ai_entry"]  = sweep.get("sweep_entry")
                result["ai_sl"]     = sweep.get("sweep_sl")
                result["ai_target"] = sweep.get("sweep_target")
        elif sweep.get("sweep_side") == "SELL":
            if result.get("signal") not in ("SELL",):
                result["signal"] = "SELL"
            if not result.get("ai_entry"):
                result["ai_entry"]  = sweep.get("sweep_entry")
                result["ai_sl"]     = sweep.get("sweep_sl")
                result["ai_target"] = sweep.get("sweep_target")

        # --- Watchlist Entry Latch ---
        is_sweep_confirmed = sweep.get("sweep_side") is not None
        if is_perfect or is_sweep_confirmed:
            if sym not in _watchlist_state_cache_v2:
                _watchlist_state_cache_v2[sym] = datetime.now().isoformat()
            result["watchlist_entry_time"] = _watchlist_state_cache_v2[sym]
        else:
            if sym in _watchlist_state_cache_v2:
                del _watchlist_state_cache_v2[sym]
            result["watchlist_entry_time"] = None
        return result
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        return None


def save_to_db(data):
    """Save only if data has changed (hash comparison)."""
    if MONGO_OK:
        existing = stocks_col.find_one({"symbol": data["symbol"]}, {"data_hash": 1})
        if existing and existing.get("data_hash") == data.get("data_hash"):
            return False
        stocks_col.update_one(
            {"symbol": data["symbol"]},
            {"$set": data},
            upsert=True
        )
        history_col.insert_one({**data, "_ts": datetime.now()})
        return True
    else:
        old = _memory_store.get(data["symbol"])
        if old and old.get("data_hash") == data.get("data_hash"):
            return False
        _memory_store[data["symbol"]] = data
        return True


def get_from_db():
    if MONGO_OK:
        docs = list(stocks_col.find({}, {"_id": 0}))
        return docs
    return list(_memory_store.values())


# -- News generation (ChatGPT or fallback) -----------------------------------

def generate_news_for_stock(symbol, name, change_pct, signal, curr_close):
    """Generate AI news/analysis for a stock. Uses ChatGPT if available, else fallback."""
    # Check cache first (valid for 30 min)
    cache_key = symbol
    if MONGO_OK:
        cached = news_col.find_one({"symbol": cache_key}, {"_id": 0})
        if cached and cached.get("expires_at"):
            if datetime.fromisoformat(cached["expires_at"]) > datetime.now():
                return cached["news"]
    elif cache_key in _news_cache:
        cached = _news_cache[cache_key]
        if datetime.fromisoformat(cached["expires_at"]) > datetime.now():
            return cached["news"]

    news_items = []

    if openai_client:
        try:
            prompt = f"""You are an Indian stock market analyst. Give me 3 brief latest news headlines and analysis for {name} ({symbol}.NS) on NSE India.
The stock is currently at Rs.{curr_close}, with a {change_pct}% change today. Signal: {signal}.

Format each as a JSON array with objects having: "headline" (string), "summary" (1-2 sentence analysis), "sentiment" ("positive"/"negative"/"neutral"), "time" (like "2h ago" or "Today").
Return ONLY the JSON array, no other text."""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )
            content = response.choices[0].message.content.strip()
            # Parse JSON from response
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            news_items = json.loads(content)
        except Exception as e:
            print(f"[NEWS] ChatGPT error for {symbol}: {e}")
            news_items = _fallback_news(name, symbol, change_pct, signal, curr_close)
    else:
        news_items = _fallback_news(name, symbol, change_pct, signal, curr_close)

    # Cache result
    cache_doc = {
        "symbol": cache_key,
        "news": news_items,
        "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat()
    }
    if MONGO_OK:
        news_col.update_one({"symbol": cache_key}, {"$set": cache_doc}, upsert=True)
    else:
        _news_cache[cache_key] = cache_doc

    return news_items


def _fallback_news(name, symbol, change_pct, signal, curr_close):
    """Generate analysis-style news without ChatGPT."""
    direction = "gained" if change_pct > 0 else "declined" if change_pct < 0 else "remained flat"
    strength = "sharp" if abs(change_pct) >= 3 else "moderate" if abs(change_pct) >= 1.5 else "mild"

    items = []
    # Technical analysis style headline
    if abs(change_pct) >= 2:
        items.append({
            "headline": f"{name} sees {strength} {abs(change_pct)}% {'rally' if change_pct > 0 else 'decline'} in today's session",
            "summary": f"{symbol} {direction} {abs(change_pct)}% to Rs.{curr_close}. {'Buying interest seen at current levels with strong volume support.' if change_pct > 0 else 'Selling pressure continues with traders booking profits at higher levels.'}",
            "sentiment": "positive" if change_pct > 0 else "negative",
            "time": "Today"
        })
    else:
        items.append({
            "headline": f"{name} trades in narrow range near Rs.{curr_close}",
            "summary": f"{symbol} shows limited movement with {abs(change_pct)}% change. Stock consolidating near current levels with neutral momentum indicators.",
            "sentiment": "neutral",
            "time": "Today"
        })

    # Signal-based analysis
    if signal == "BUY":
        items.append({
            "headline": f"Technical breakout: {name} crosses 2% threshold on NSE",
            "summary": f"F&O stock {symbol} has triggered a buy signal with {change_pct}% gain. RSI and MACD indicators suggest continued bullish momentum in the near term.",
            "sentiment": "positive",
            "time": "Today"
        })
    elif signal == "SELL":
        items.append({
            "headline": f"Bearish signal: {name} drops below key support levels",
            "summary": f"F&O stock {symbol} triggered a sell alert with {abs(change_pct)}% decline. Traders advised to watch support levels closely for potential reversal.",
            "sentiment": "negative",
            "time": "Today"
        })

    # General sector/market context
    items.append({
        "headline": f"NSE F&O Watch: {name} - Analyst outlook and key levels",
        "summary": f"Market analysts tracking {symbol} at Rs.{curr_close}. Key resistance at Rs.{round(curr_close * 1.02, 2)} and support at Rs.{round(curr_close * 0.98, 2)}. Volume patterns suggest institutional {'accumulation' if change_pct > 0 else 'distribution'}.",
        "sentiment": "neutral",
        "time": "Recent"
    })

    return items


def fetch_oi_spurts():
    """Fetch NSE OI Spurts data once every 5 minutes."""
    global _oi_spurts_cache, _oi_contracts_cache, _last_oi_spurts_update
    if (datetime.now() - _last_oi_spurts_update).total_seconds() < 300:
        return
        
    print("[SCAN] Fetching NSE OI Spurts (Underlyings & Contracts)...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        
        # 1. Underlyings
        r1 = session.get("https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings", headers=headers, timeout=5)
        if r1.status_code == 200:
            data = r1.json()
            if "data" in data:
                new_underlyings = {}
                for item in data["data"]:
                    sym = item.get("symbol")
                    if sym:
                        new_underlyings[sym] = {
                            "latestOI": item.get("latestOI", 0),
                            "prevOI": item.get("prevOI", 0),
                            "changeInOI": item.get("changeInOI", 0),
                            "avgInOI": item.get("avgInOI", 0),
                            "volume": item.get("volume", 0),
                            "underlyingValue": item.get("underlyingValue", 0)
                        }
                _oi_spurts_cache = new_underlyings
        
        # 2. Contracts (Strikes)
        r2 = session.get("https://www.nseindia.com/api/live-analysis-oi-spurts-contracts", headers=headers, timeout=5)
        if r2.status_code == 200:
            data = r2.json()
            if "data" in data:
                new_contracts = {}
                for item in data["data"]:
                    # Item example: {"symbol": "RELIANCE", "strikePrice": 2500, "optionType": "CE", "latestOI": ...}
                    # Construct strike display like "2500 CE"
                    sym = item.get("symbol")
                    if not sym: continue
                    
                    strike_val = item.get("strikePrice", 0)
                    opt_type = item.get("optionType", "")
                    strike_label = f"{strike_val} {opt_type}" if opt_type != "Others" else f"{strike_val}"
                    
                    # Calculate action for this specific strike
                    oi_chg = item.get("avgInOI", 0)
                    price_chg = item.get("p_change", 0)
                    action = "Neutral"
                    if oi_chg > 0 and price_chg > 0: action = "Long Buildup"
                    elif oi_chg > 0 and price_chg < 0: action = "Short Buildup"
                    elif oi_chg < 0 and price_chg < 0: action = "Long Unwinding"
                    elif oi_chg < 0 and price_chg > 0: action = "Short Covering"
                    
                    if sym not in new_contracts:
                        new_contracts[sym] = []
                    
                    new_contracts[sym].append({
                        "strike": strike_label,
                        "oi_chg": round(oi_chg, 2),
                        "price_chg": round(price_chg, 2),
                        "action": action,
                        "volume": item.get("volume", 0)
                    })
                
                # Sort contracts by absolute OI change for each symbol
                for s in new_contracts:
                    new_contracts[s].sort(key=lambda x: abs(x["oi_chg"]), reverse=True)
                
                _oi_contracts_cache = new_contracts
                
        _last_oi_spurts_update = datetime.now()
        print(f"[DONE] OI Summary updated for {len(_oi_spurts_cache)} stocks and {len(_oi_contracts_cache)} symbols")
        
    except Exception as e:
        print(f"[ERROR] OI Spurts fetch failed: {e}")


# -- Momentum Tracking ------------------------------------------------------
_price_history = {} # symbol -> deque of (timestamp, price)
from collections import deque

def update_momentum(symbol, price):
    now = time.time()
    if symbol not in _price_history:
        _price_history[symbol] = deque(maxlen=60) # Store last 60 ticks (approx 2 mins)
    _price_history[symbol].append((now, price))
    
    # Calculate 1-min momentum
    one_min_ago = now - 60
    old_price = None
    for ts, p in _price_history[symbol]:
        if ts >= one_min_ago:
            old_price = p
            break
    
    if old_price and old_price > 0:
        return round(((price - old_price) / old_price * 100), 2)
    return 0


# -- Background scanner with concurrent fetching ----------------------------
_last_scan = {"time": None, "data": [], "changed_symbols": []}
_scan_lock = threading.Lock()
_scanning = False


def scan_all():
    global _scanning
    _scanning = True
    print(f"[SCAN] Bulk scanning {len(FO_STOCKS)} stocks... (TradingView Live + yfinance 60d)")
    
    results = []
    changed = []

    try:
        # 1. Fetch live real-time metrics for ALL NSE stocks via TradingView
        print("[SCAN] Step 1: Fetching TradingView metrics...")
        url = "https://scanner.tradingview.com/india/scan"
        payload = {
            "filter": [{"left": "exchange", "operation": "equal", "right": "NSE"}],
            "columns": ["name", "close", "change", "open", "high", "low", "volume", "Recommend.All"],
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [0, 5000]
        }
        
        tv_data_map = {}
        try:
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                tv_response = resp.json().get('data', [])
                tv_data_map = {x['s']: x['d'] for x in tv_response}
                print(f"[SCAN] Step 1 OK: {len(tv_data_map)} stocks found on TV")
            else:
                print(f"[SCAN ERROR] TV Status {resp.status_code}")
        except Exception as te:
            print(f"[SCAN ERROR] TV Fetch Failed: {te}")

        # 2. Setup symbols
        all_symbols = [sym for _, sym in FO_STOCKS]

        # 3. Fetch 60-day history (Daily)
        global _daily_history_cache, _last_history_update
        hist_data = _daily_history_cache
        if _daily_history_cache is None or (datetime.now() - _last_history_update).total_seconds() > 3600:
            print(f"[SCAN] Step 2: Refreshing daily history in chunks...")
            try:
                # Chunking to prevent yfinance hangs + adding timeout
                all_df = []
                chunk_size = 30
                for i in range(0, len(all_symbols), chunk_size):
                    chunk = all_symbols[i:i+chunk_size]
                    print(f"  > Downloading daily chunk {i//chunk_size + 1} ({len(chunk)} stocks)...")
                    try:
                        d = yf.download(chunk, period="60d", interval="1d", group_by="ticker", 
                                        threads=True, progress=False, auto_adjust=True, ignore_tz=True, timeout=25)
                        if not d.empty: all_df.append(d)
                    except Exception as ce:
                        print(f"  [CHUNK ERROR] Daily Batch {i//chunk_size + 1} failed/timed out: {ce}")
                
                if all_df:
                    hist_data = pd.concat(all_df, axis=1)
                    _daily_history_cache = hist_data
                    _last_history_update = datetime.now()
                    # Debug: print column structure so we can verify extraction works
                    col_info = f"columns type: {type(hist_data.columns).__name__}"
                    if hasattr(hist_data.columns, 'levels'):
                        col_info += f", levels: {[list(l[:3]) for l in hist_data.columns.levels]}"
                    print(f"[SCAN] Step 2 OK: Daily history refreshed ({len(all_df)} batches) | {col_info}")
            except Exception as e:
                print(f"[ERROR] Step 2 Fail (Daily History): {e}")
                if hist_data is None or (hasattr(hist_data, 'empty') and hist_data.empty):
                    print("[SCAN ERROR] No historical data available, attempting to use cache...")
                    if _daily_history_cache is not None:
                        hist_data = _daily_history_cache
                    else:
                        print("[SCAN ERROR] Absolute failure: No cache available.")
                        _scanning = False
                        return 

        # 4. Fetch 5-minute history (Intraday) - will be resampled to 10m
        global _ten_min_history_cache, _last_ten_min_update
        ten_min_data = _ten_min_history_cache
        if _ten_min_history_cache is None or (datetime.now() - _last_ten_min_update).total_seconds() > 600:
            print("[SCAN] Step 3: Refreshing intraday history in chunks...")
            try:
                all_tm = []
                chunk_size = 30
                for i in range(0, len(all_symbols), chunk_size):
                    chunk = all_symbols[i:i+chunk_size]
                    print(f"  > Downloading intraday chunk {i//chunk_size + 1}...")
                    try:
                        d = yf.download(chunk, period="7d", interval="5m", group_by="ticker", 
                                        threads=True, progress=False, auto_adjust=True, ignore_tz=True, timeout=25)
                        if not d.empty: all_tm.append(d)
                    except Exception as ice:
                        print(f"  [CHUNK ERROR] Intraday Batch {i//chunk_size + 1} failed/timed out: {ice}")
                
                if all_tm:
                    ten_min_data = pd.concat(all_tm, axis=1)
                    _ten_min_history_cache = ten_min_data
                    _last_ten_min_update = datetime.now()
                    print("[SCAN] Step 3 OK: Intraday history refreshed")
            except Exception as e:
                print(f"[ERROR] Step 3 Fail (Intraday): {e}")

        def _get_stock_df(bulk_df, symbol):
            """Safely extract single-stock DataFrame from yfinance bulk download."""
            if bulk_df is None or bulk_df.empty:
                return None
            try:
                cols = bulk_df.columns
                if hasattr(cols, 'levels'):
                    # MultiIndex: yfinance group_by='ticker' gives (Price, Symbol) structure
                    # Try (field, symbol) — levels[0]=fields, levels[1]=symbols
                    if len(cols.levels) == 2:
                        if symbol in cols.levels[1]:
                            # Standard: columns are (Price, Ticker) — get all prices for symbol
                            df = bulk_df.xs(symbol, axis=1, level=1)
                            return df if not df.empty else None
                        elif symbol in cols.levels[0]:
                            # Reversed: columns are (Ticker, Price)
                            df = bulk_df[symbol]
                            return df if not df.empty else None
                else:
                    # Flat columns — single ticker or already extracted
                    if symbol in cols:
                        return bulk_df[[symbol]]
                    if set(['Open','High','Low','Close','Volume']).issubset(set(cols)):
                        return bulk_df
            except Exception as e:
                print(f"[EXTRACT] {symbol}: {e}")
            return None

        def _process(item):
            name, symbol = item
            try:
                stock_df = _get_stock_df(hist_data, symbol)
                tm_df    = _get_stock_df(ten_min_data, symbol)
                return process_stock_data(name, symbol, stock_df, tv_data_map, tm_df)
            except Exception as e:
                print(f"[PROCESS ERROR] {symbol}: {e}")
                return None

        # ThreadPool just to speed up processing/DB saving, data is already in memory
        print(f"[SCAN] Step 4: Processing {len(FO_STOCKS)} stocks incrementally...")
        fail_count = 0
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(_process, item): item for item in FO_STOCKS}
            for future in as_completed(futures):
                try:
                    data = future.result()
                    if data:
                        was_changed = save_to_db(data)
                        if was_changed:
                            changed.append(data["symbol"])
                        
                        # Incremental Update: Add to results and update the "Live" cache immediately
                        results.append(data)
                        with _scan_lock:
                            # Keep most recent data for each symbol
                            _last_scan["time"] = datetime.now().isoformat()
                            # Efficiently update the cache without waiting for all 200
                            existing_map = {r['symbol']: r for r in _last_scan["data"]}
                            existing_map[data['symbol']] = data
                            _last_scan["data"] = list(existing_map.values())
                    else:
                        fail_count += 1
                except Exception as fe:
                    fail_count += 1
                    print(f"[THREAD ERROR] {fe}")
        print(f"[SCAN] Step 4 OK: Incremental processing complete ({len(results)} stocks)")

    except Exception as e:
        print(f"[SCAN ERROR] Critical failure: {e}")

    with _scan_lock:
        _last_scan["time"] = datetime.now().isoformat()
        _last_scan["data"] = results
        _last_scan["changed_symbols"] = changed

    # -- Trigger Automation Logic --
    try:
        update_automated_trade(results)
    except Exception as e:
        print(f"[TRADE ERROR] {e}")

    _scanning = False
    alert_count = sum(1 for r in results if r['alerted'])
    
    # Final Status Summary
    save_status = f"{len(changed)} updated" if changed else "No changes"
    timestamp_str = datetime.now().strftime("%H:%M:%S")
    err_str = f" | {fail_count} failed" if fail_count > 0 else ""
    print(f"[OK] Scan @ {timestamp_str} | {len(results)} stocks | {save_status}{err_str} | {alert_count} alerts")


def background_scanner():
    while True:
        try:
            scan_all()
            fetch_global_markets()
            fetch_oi_spurts()
        except Exception as e:
            print(f"Scanner error: {e}")
        interval = 15 if is_market_open() else 1800
        time.sleep(interval)


# -- Markets Cache -----------------------------------------------------------
_last_markets_update = datetime.min

def fetch_global_markets():
    global _market_data, _last_markets_update
    if (datetime.now() - _last_markets_update).total_seconds() < 300:
        return

    print("[SCAN] Fetching Global Markets (Indices/Commodities)...")
    import math
    new_market_results = []

    for name, sym in GLOBAL_MARKETS:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period="5d", interval="1d")
            if df is None or df.empty:
                continue
            # Drop rows with NaN close
            df = df.dropna(subset=["Close"])
            if len(df) < 1:
                continue

            curr = float(df["Close"].iloc[-1])
            if math.isnan(curr) or curr <= 0:
                continue

            if len(df) >= 2:
                prev = float(df["Close"].iloc[-2])
                if math.isnan(prev) or prev <= 0:
                    prev = curr
            else:
                prev = curr

            change = round(((curr - prev) / prev * 100), 2) if prev > 0 else 0.0
            new_market_results.append({
                "name": name, "symbol": sym,
                "price": round(curr, 2), "change_pct": change
            })
        except Exception as e:
            print(f"[WARN] Global market {name} ({sym}) failed: {e}")
            continue

    if new_market_results:
        # Merge with existing data (keep old entries if new fetch missed them)
        merged = {m["name"]: m for m in _market_data}
        for res in new_market_results:
            merged[res["name"]] = res
        _market_data = list(merged.values())
        _last_markets_update = datetime.now()
        print(f"[DONE] Global markets updated: {len(new_market_results)} fetched, {len(_market_data)} total")


# -- API Routes --------------------------------------------------------------

@app.route("/")
def serve_frontend():
    return send_from_directory(FRONTEND_DIR, "index.html")



@app.route("/api/stocks")
def get_stocks():
    filter_type = request.args.get("filter", "all")
    sort_by = request.args.get("sort", "name")
    sort_dir = request.args.get("dir", "asc")
    search = request.args.get("search", "").lower()

    with _scan_lock:
        data = list(_last_scan["data"])
    if not data:
        data = get_from_db()

    if filter_type == "alerts":
        data = [d for d in data if d.get("alerted")]
    elif filter_type == "buy":
        data = [d for d in data if d.get("signal") == "BUY"]
    elif filter_type == "sell":
        data = [d for d in data if d.get("signal") == "SELL"]

    if search:
        data = [d for d in data if search in d.get("name", "").lower() or search in d.get("symbol", "").lower()]

    reverse = sort_dir == "desc"
    try:
        data.sort(key=lambda x: x.get(sort_by, "") or "", reverse=reverse)
    except Exception:
        pass

    return safe_jsonify({
        "stocks": data,
        "total": len(data),
        "alerts": sum(1 for d in data if d.get("alerted")),
        "buy_count": sum(1 for d in data if d.get("signal") == "BUY"),
        "sell_count": sum(1 for d in data if d.get("signal") == "SELL"),
        "last_scan": _last_scan["time"],
        "market_open": is_market_open(),
        "scanning": _scanning,
        "changed_symbols": _last_scan.get("changed_symbols", [])
    })




@app.route("/api/stock/<symbol>")
def get_stock_details(symbol):
    data = get_from_db()
    for s in data:
        if s["symbol"] == symbol:
            s["oi"] = _oi_spurts_cache.get(symbol)
            return safe_jsonify(s)
    return jsonify({"error": "Stock not found"}), 404
    

@app.route("/api/news/<symbol>")
def get_news(symbol):
    """Fetch AI-generated news for a specific stock."""
    # Find stock info first
    if MONGO_OK:
        stock = stocks_col.find_one({"symbol": symbol}, {"name": 1, "change_pct": 1, "signal": 1, "curr_close": 1})
    else:
        stock = _memory_store.get(symbol)
    
    if not stock:
        return jsonify({"error": "Stock not found"}), 404
    
    news = generate_news_for_stock(
        symbol, 
        stock.get("name", symbol), 
        stock.get("change_pct", 0), 
        stock.get("signal", "NEUTRAL"), 
        stock.get("curr_close", 0)
    )
    return safe_jsonify({"symbol": symbol, "news": news})


@app.route("/api/market/status")
def market_status():
    """Return live status of indices and commodities."""
    return safe_jsonify({
        "markets": _market_data,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/trade/active")
def get_active_trade():
    """Get the current automated trade of the day."""
    if MONGO_OK:
        active = trade_state_col.find_one({"status": "OPEN"}, {"_id": 0})
    else:
        active = _active_trade_store
    return safe_jsonify(active)


@app.route("/api/trade/journal")
def get_trade_journal():
    """Get all past automated trades."""
    if MONGO_OK:
        journal = list(journal_col.find({}, {"_id": 0}))
    else:
        journal = _journal_store
    
    total_pl = sum(t.get("p_l", 0) for t in journal)
    return safe_jsonify({
        "trades": journal,
        "total_pl": round(total_pl, 2)
    })


@app.route("/api/trade/journal/add", methods=["POST"])
def add_journal_entry():
    """Manually add a stock to the trading journal for backtesting."""
    try:
        data = request.get_json()
        if not data or not data.get("symbol"):
            return jsonify({"error": "symbol is required"}), 400

        symbol = data["symbol"]
        side   = data.get("side", "BUY")
        entry  = float(data.get("entry", 0))
        sl     = float(data.get("sl", 0))
        target = float(data.get("target", 0))
        notes  = data.get("notes", "")
        name   = data.get("name", symbol)

        # Compute basic P/L placeholder (0 until exit is logged)
        entry_doc = {
            "symbol":      symbol,
            "name":        name,
            "side":        side,
            "entry":       round(entry, 2),
            "sl":          round(sl, 2),
            "target":      round(target, 2),
            "exit_price":  None,
            "p_l":         0,
            "p_l_pct":     0,
            "exit_reason": "MANUAL / BACKTEST",
            "status":      "BACKTEST",
            "notes":       notes,
            "date":        datetime.now().strftime("%Y-%m-%d"),
            "timestamp":   datetime.now().isoformat(),
        }

        if MONGO_OK:
            journal_col.insert_one(entry_doc)
        else:
            _journal_store.append(entry_doc)

        print(f"[JOURNAL] Manual entry added: {side} {symbol} @ {entry} | SL:{sl} TGT:{target}")
        return jsonify({"status": "ok", "message": f"{symbol} added to journal"}), 201

    except Exception as e:
        print(f"[JOURNAL] Error adding manual entry: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/trade/take", methods=["POST"])
def take_manual_trade():
    """Manual trigger to take a specific trade from the dashboard."""
    global _active_trade_store
    try:
        data = request.get_json()
        symbol = data.get("symbol")
        if not symbol:
            return jsonify({"error": "symbol is required"}), 400

        # Fetch latest data for this stock
        all_stocks = get_from_db()
        target_stock = next((s for s in all_stocks if s["symbol"] == symbol), None)
        
        if not target_stock:
            return jsonify({"error": "Stock data not found"}), 404

        # Clear any existing open trade FIRST
        if MONGO_OK:
            trade_state_col.delete_many({"status": "OPEN"})
        else:
            _active_trade_store = None

        # Calculate levels
        trade = calculate_trade_levels(target_stock)
        if not trade:
            return jsonify({"error": "Could not calculate trade levels"}), 500
            
        trade["symbol"] = target_stock["symbol"]
        trade["name"] = target_stock["name"]
        
        # Reason
        reason = target_stock.get("perfect_setup", {}).get("reason", "Technical Setup")
        trade["selection_reason"] = f"Manual Entry: {reason}"
        
        if MONGO_OK:
            trade_state_col.insert_one(trade)
        else:
            _active_trade_store = trade
            
        print(f"[TRADE] Manually entered {trade['side']} trade for {trade['symbol']} via Dashboard.")
        return jsonify({"status": "ok", "message": f"Trade taken for {symbol}"}), 200

    except Exception as e:
        print(f"[TRADE] Error taking manual trade: {e}")
        return jsonify({"error": str(e)}), 500
# Removed duplicate route - see line 2680 for the actual implementation


@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    if _scanning:
        return jsonify({"status": "already_scanning"})
    threading.Thread(target=scan_all, daemon=True).start()
    return jsonify({"status": "scan_started"})


@app.route("/api/status")
def status():
    return jsonify({
        "market_open": is_market_open(),
        "last_scan": _last_scan["time"],
        "total_stocks": len(FO_STOCKS),
        "mongo": MONGO_OK,
        "scanning": _scanning
    })


@app.route("/api/market-news")
def get_market_news():
    """Fetch general Indian market news (static/hardcoded)."""
    news_items = [
        {
            "headline": "Indian markets trade with volatility", 
            "summary": "Nifty and Sensex show mixed trends amid global cues. Investors watch key support levels at 23,800 and 23,500.", 
            "sentiment": "neutral", 
            "time": "Updated recently"
        },
        {
            "headline": "FIIs turn net buyers in cash segment",
            "summary": "Foreign institutional investors have shown renewed interest in Indian equities after a brief period of selling.",
            "sentiment": "positive",
            "time": "2h ago"
        },
        {
            "headline": "Sector rotation observed in Midcap space",
            "summary": "Auto and Banking sectors see strong momentum while IT remains cautious ahead of earnings.",
            "sentiment": "neutral",
            "time": "3h ago"
        }
    ]
    return safe_jsonify(news_items)


@app.route("/api/marquee-data")
def get_marquee_data():
    """Return combined Expert Portfolios + Global Markets for scrolling marquee."""
    # Expert Portfolios: top 8 gainers + top 7 losers from scanned stocks
    all_stocks = get_from_db()
    sorted_up = sorted([s for s in all_stocks if s.get('change_pct', 0) > 0],
                       key=lambda x: x.get('change_pct', 0), reverse=True)[:8]
    sorted_dn = sorted([s for s in all_stocks if s.get('change_pct', 0) < 0],
                       key=lambda x: x.get('change_pct', 0))[:7]
    expert = [{
        "name": s["name"], "symbol": s["symbol"],
        "price": s.get("curr_close", 0), "change_pct": s.get("change_pct", 0)
    } for s in sorted_up + sorted_dn]

    return safe_jsonify({
        "expert_portfolios": expert,
        "global_markets": _market_data,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/sector_analysis")
def get_sector_analysis():
    """Aggregate live stock data by sector for performance analysis."""
    all_stocks = get_from_db()
    if not all_stocks:
        return jsonify({"sectors": []})

    sectors_data = {}
    
    for s in all_stocks:
        sec = s.get("sector", "Others")
        if sec not in sectors_data:
            sectors_data[sec] = {
                "name": sec,
                "count": 0,
                "advances": 0,
                "declines": 0,
                "total_chg": 0,
                "top_gainer": {"symbol": "--", "chg": -999},
                "top_loser": {"symbol": "--", "chg": 999},
                "avg_chg": 0
            }
        
        sd = sectors_data[sec]
        sd["count"] += 1
        chg = s.get("change_pct", 0)
        sd["total_chg"] += chg
        
        if chg > 0: sd["advances"] += 1
        elif chg < 0: sd["declines"] += 1
        
        if chg > sd["top_gainer"]["chg"]:
            sd["top_gainer"] = {"symbol": s["symbol"], "chg": round(chg, 2)}
        if chg < sd["top_loser"]["chg"]:
            sd["top_loser"] = {"symbol": s["symbol"], "chg": round(chg, 2)}

    # Finalize averages
    result_list = []
    for sec_name, sd in sectors_data.items():
        sd["avg_chg"] = round(sd["total_chg"] / sd["count"], 2) if sd["count"] > 0 else 0
        result_list.append(sd)

    # Sort by avg performance
    result_list.sort(key=lambda x: x["avg_chg"], reverse=True)
    
    return safe_jsonify({
        "sectors": result_list,
        "timestamp": datetime.now().isoformat()
    })



# -- Nifty Analysis Cache ----------------------------------------------------
_nifty_cache = {}
_last_nifty_update = datetime.min

@app.route("/api/nifty-analysis")
def get_nifty_analysis():
    """Return comprehensive Nifty 50 analysis: levels, EMAs, RSI, OI, sectors, news."""
    global _nifty_cache, _last_nifty_update

    # Cache for 10 seconds
    if _nifty_cache and (datetime.now() - _last_nifty_update).total_seconds() < 10:
        return safe_jsonify(_nifty_cache[1])

    result = {}
    try:
        import math

        # ── Fetch Nifty daily history (1 year for 52w + 60d for levels) ──────
        ticker = yf.Ticker("^NSEI")
        df_1y = ticker.history(period="1y", interval="1d").dropna(subset=["Close"])
        df_60 = df_1y.tail(60) if len(df_1y) >= 60 else df_1y
        
        # REAL-TIME PRICE FIX: Use 1-minute data for the latest price
        df_live = ticker.history(period="1d", interval="1m")
        
        if df_60.empty:
            return safe_jsonify({"error": "No Nifty historical data available"})

        closes = df_60["Close"].astype(float).values
        highs_arr  = df_60["High"].astype(float).values
        lows_arr   = df_60["Low"].astype(float).values

        # Use live data for current price metrics if available, else daily
        if not df_live.empty:
            curr_close  = round(float(df_live["Close"].iloc[-1]), 2)
            open_price  = round(float(df_live["Open"].iloc[0]), 2) # Today's open
            day_high    = round(float(df_live["High"].max()), 2)
            day_low     = round(float(df_live["Low"].min()), 2)
        else:
            curr_close = round(float(closes[-1]), 2)
            open_price = round(float(df_60["Open"].iloc[-1]), 2)
            day_high   = round(float(df_60["High"].iloc[-1]), 2)
            day_low    = round(float(df_60["Low"].iloc[-1]), 2)

        prev_close  = round(float(closes[-2]), 2) # Yesterday's close
        change_pct  = round((curr_close - prev_close) / prev_close * 100, 2) if prev_close else 0

        # ── Previous day H/L/C for Pivot Points ──────────────────────────────
        ph = float(highs_arr[-2])
        pl = float(lows_arr[-2])
        pc = float(closes[-2])

        pivot   = round((ph + pl + pc) / 3, 2)
        r1      = round((2 * pivot) - pl, 2)
        r2      = round(pivot + (ph - pl), 2)
        r3      = round(ph + 2 * (pivot - pl), 2)
        s1      = round((2 * pivot) - ph, 2)
        s2      = round(pivot - (ph - pl), 2)
        s3      = round(pl - 2 * (ph - pivot), 2)

        # ── 52-week High / Low ────────────────────────────────────────────────
        all_closes_1y = df_1y["Close"].astype(float).values
        all_highs_1y  = df_1y["High"].astype(float).values
        all_lows_1y   = df_1y["Low"].astype(float).values
        w52_high = round(float(np.max(all_highs_1y)), 2)
        w52_low  = round(float(np.min(all_lows_1y)), 2)

        # ── EMA Helper ────────────────────────────────────────────────────────
        def ema(data, period):
            if len(data) < period:
                return float(np.mean(data))
            multiplier = 2.0 / (period + 1)
            e = float(np.mean(data[:period]))
            for val in data[period:]:
                e = (float(val) - e) * multiplier + e
            return e

        ema9   = round(ema(closes, 9), 2)
        ema21  = round(ema(closes, 21), 2)
        ema50  = round(ema(closes, 50), 2)
        ema200 = round(ema(closes, min(200, len(closes))), 2)

        # ── RSI(14) ───────────────────────────────────────────────────────────
        deltas  = np.diff(closes)
        gains   = np.where(deltas > 0, deltas, 0)
        losses  = np.where(deltas < 0, -deltas, 0)
        avg_g   = float(np.mean(gains[-14:])) if len(gains) >= 14 else float(np.mean(gains))
        avg_l   = float(np.mean(losses[-14:])) if len(losses) >= 14 else float(np.mean(losses))
        rsi14   = round(100.0 - (100.0 / (1.0 + avg_g / avg_l)), 2) if avg_l > 0 else 100.0

        # ── ATR(14) ───────────────────────────────────────────────────────────
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs_arr[i] - lows_arr[i],
                     abs(highs_arr[i] - closes[i-1]),
                     abs(lows_arr[i]  - closes[i-1]))
            trs.append(tr)
        atr14 = round(float(np.mean(trs[-14:])) if len(trs) >= 14 else float(np.mean(trs)), 2)

        # ── Market State ──────────────────────────────────────────────────────
        price_above_ema50  = curr_close > ema50
        price_above_ema200 = curr_close > ema200
        ema9_above_ema21   = ema9 > ema21
        ema21_above_ema50  = ema21 > ema50

        # Sideways detection: price within 1x ATR of EMA50
        in_band = abs(curr_close - ema50) < atr14 * 1.0

        if in_band and not ema9_above_ema21:
            market_state   = "Sideways"
            trend_reason   = f"Nifty is consolidating near EMA50 ({ema50}) within ±{atr14:.0f} pts band. No clear directional bias."
            state_color    = "#ffab00"
        elif price_above_ema50 and price_above_ema200 and ema9_above_ema21 and ema21_above_ema50:
            market_state   = "Trending Up"
            trend_reason   = f"All EMAs aligned bullishly (EMA9 > EMA21 > EMA50). Nifty trading above EMA200 ({ema200}). Strong uptrend."
            state_color    = "#00e676"
        elif not price_above_ema50 and not ema9_above_ema21:
            market_state   = "Trending Down"
            trend_reason   = f"EMA9 ({ema9}) < EMA21 ({ema21}). Nifty below EMA50 ({ema50}). Bears in control."
            state_color    = "#ff3d71"
        elif price_above_ema50 and not ema9_above_ema21:
            market_state   = "Sideways / Caution"
            trend_reason   = f"Nifty above EMA50 but EMA9 crossing below EMA21 — potential distribution or pullback forming."
            state_color    = "#ffab00"
        else:
            market_state   = "Sideways"
            trend_reason   = f"Mixed signals. EMA crossovers inconclusive. Wait for a clean breakout above {r1} or breakdown below {s1}."
            state_color    = "#94a3b8"

        # ── Momentum Signal ───────────────────────────────────────────────────
        mom_val = update_momentum("^NSEI", curr_close)
        if abs(mom_val) >= 0.3:
            momentum_signal = "Strong Momentum ▲" if mom_val > 0 else "Strong Momentum ▼"
            mom_color = "#00e676" if mom_val > 0 else "#ff3d71"
        elif abs(mom_val) >= 0.1:
            momentum_signal = "Moderate" 
            mom_color = "#ffab00"
        else:
            momentum_signal = "Neutral / Flat"
            mom_color = "#94a3b8"

        # ── OI Data (NIFTY from NSE cache) ────────────────────────────────────
        nifty_oi = _oi_spurts_cache.get("NIFTY")
        nifty_oi_contracts = _oi_contracts_cache.get("NIFTY", [])[:5]

        # ── Sector Pulse (from live stock data) ───────────────────────────────
        all_stocks_db = get_from_db()
        sector_map = {}
        for s in all_stocks_db:
            sec = s.get("sector", "Others")
            chg = s.get("change_pct", 0) or 0
            if sec not in sector_map:
                sector_map[sec] = {"total": 0, "count": 0, "advances": 0, "declines": 0}
            sector_map[sec]["total"] += chg
            sector_map[sec]["count"] += 1
            if chg > 0: sector_map[sec]["advances"] += 1
            elif chg < 0: sector_map[sec]["declines"] += 1

        sector_pulse = []
        for sec_name, sd in sector_map.items():
            avg = round(sd["total"] / sd["count"], 2) if sd["count"] > 0 else 0
            bull = sd["advances"] > sd["declines"]
            sector_pulse.append({
                "name": sec_name,
                "avg_chg": avg,
                "advances": sd["advances"],
                "declines": sd["declines"],
                "count": sd["count"],
                "impact": "Lifting" if avg > 0.3 else ("Dragging" if avg < -0.3 else "Neutral"),
                "impact_color": "#00e676" if avg > 0.3 else ("#ff3d71" if avg < -0.3 else "#94a3b8")
            })
        sector_pulse.sort(key=lambda x: abs(x["avg_chg"]), reverse=True)

        # ── Chart Data (last 30 daily bars) ──────────────────────────────────
        chart_df = df_1y.tail(30)
        chart_closes = [round(float(c), 2) for c in chart_df["Close"].tolist()]
        chart_opens  = [round(float(c), 2) for c in chart_df["Open"].tolist()]
        chart_highs  = [round(float(c), 2) for c in chart_df["High"].tolist()]
        chart_lows   = [round(float(c), 2) for c in chart_df["Low"].tolist()]
        chart_dates  = [int(d.timestamp()) for d in chart_df.index]

        # ── Fallback News for Nifty ───────────────────────────────────────────
        direction = "gained" if change_pct > 0 else "declined"
        news = [
            {
                "headline": f"Nifty 50 {direction} {abs(change_pct):.2f}% — Market {'Bullish' if change_pct > 0 else 'Bearish'} Outlook",
                "summary": f"Market is in a {market_state} phase. {trend_reason}",
                "sentiment": "positive" if change_pct > 0 else ("negative" if change_pct < 0 else "neutral"),
                "time": "Today"
            },
            {
                "headline": f"Key levels: Support at {s1} | Resistance at {r1}",
                "summary": f"Pivot Point: {pivot}. R1: {r1}, R2: {r2}. S1: {s1}, S2: {s2}. RSI at {rsi14} suggests {'overbought conditions' if rsi14 > 70 else ('oversold conditions — watch for bounce' if rsi14 < 30 else 'neutral momentum')}.",
                "sentiment": "neutral",
                "time": "Today"
            },
            {
                "headline": f"Sector Analysis: {sector_pulse[0]['name'] if sector_pulse else 'Banking'} sector {'leading' if (sector_pulse and sector_pulse[0]['avg_chg'] > 0) else 'dragging'} Nifty",
                "summary": f"Top contributing sector: {sector_pulse[0]['name'] if sector_pulse else 'N/A'} ({'+' if sector_pulse and sector_pulse[0]['avg_chg'] > 0 else ''}{sector_pulse[0]['avg_chg'] if sector_pulse else 0}%). EMA50 at {ema50}, EMA200 at {ema200}. 52W High: {w52_high}, 52W Low: {w52_low}.",
                "sentiment": "neutral",
                "time": "Today"
            }
        ]

        result = {
            "price": curr_close,
            "prev_close": prev_close,
            "open": open_price,
            "high": day_high,
            "low": day_low,
            "change_pct": change_pct,
            "pivot": pivot,
            "r1": r1, "r2": r2, "r3": r3,
            "s1": s1, "s2": s2, "s3": s3,
            "w52_high": w52_high,
            "w52_low": w52_low,
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "ema200": ema200,
            "rsi14": rsi14,
            "atr14": atr14,
            "market_state": market_state,
            "state_color": state_color,
            "trend_reason": trend_reason,
            "momentum_val": round(mom_val, 3),
            "momentum_signal": momentum_signal,
            "mom_color": mom_color,
            "nifty_oi": nifty_oi,
            "nifty_oi_contracts": nifty_oi_contracts,
            "sector_pulse": sector_pulse[:10],
            "news": news,
            "chart_closes": chart_closes,
            "chart_opens": chart_opens,
            "chart_highs": chart_highs,
            "chart_lows": chart_lows,
            "chart_dates": chart_dates,
            "timestamp": datetime.now().isoformat()
        }

        # --- Real-Time Update via TradingView (Fixes YFinance delay) ---
        try:
            tv_url = "https://scanner.tradingview.com/india/scan"
            tv_payload = {
                "symbols": {"tickers": ["NSE:NIFTY"]},
                "columns": ["close", "change", "open", "high", "low"]
            }
            tv_res = requests.post(tv_url, json=tv_payload, timeout=3).json()
            if "data" in tv_res and len(tv_res["data"]) > 0:
                tv_data = tv_res["data"][0]["d"]
                result["price"] = tv_data[0]
                result["change_pct"] = tv_data[1]
                result["open"] = tv_data[2]
                result["high"] = tv_data[3]
                result["low"] = tv_data[4]
                # Log the update source
                result["source"] = "TradingView Real-Time"
        except Exception as e:
            print(f"Error fetching TV Nifty: {e}")
            result["source"] = "yfinance (Daily Fallback)"

        # Store in cache
        _last_nifty_update = datetime.now()
        _nifty_cache = (_last_nifty_update, result)
        print(f"[NIFTY] Analysis updated: {result['price']} | {market_state} | RSI:{rsi14}")

    except Exception as e:
        import traceback
        print(f"[ERROR] Nifty analysis failed: {e}")
        traceback.print_exc()
        return safe_jsonify({"error": str(e)}), 500

    return safe_jsonify(result)



# -- Global Backtest Integration --------------------------------------------

# -- Global Backtest Integration --------------------------------------------

def refresh_global_backtest():
    global _backtest_cache, _last_backtest_update
    from backtest import run_backtest, NIFTY_50_SYMBOLS
    
    # Init from DB if exists
    if MONGO_OK:
        try:
            latest = backtest_col.find_one(sort=[("timestamp", -1)])
            if latest:
                _backtest_cache = latest["results"]
                _last_backtest_update = latest["timestamp"]
                print("[BACKTEST] Loaded cached results from MongoDB")
        except: pass

    is_first_run = True
    while True:
        try:
            # First run is 3 days for speed, subsequent are 14 days
            days = 3 if is_first_run and not _backtest_cache else 14
            print(f"[BACKTEST] Running {days}-day validation (Nifty 50 subset)...")
            
            results = run_backtest(days=days, symbols=NIFTY_50_SYMBOLS)
            _backtest_cache = results
            _last_backtest_update = datetime.now()
            
            if MONGO_OK:
                backtest_col.insert_one({
                    "timestamp": _last_backtest_update,
                    "results": results,
                    "type": "nifty50_global"
                })
            
            print(f"[BACKTEST] Global results updated ({results['win_rate']}% WR)")
            is_first_run = False
        except Exception as e:
            print(f"[BACKTEST ERROR] {e}")
        
        # Refresh every 15 mins (was 6 hours) to keep validation box live
        time.sleep(900)

@app.route('/api/backtest/results')
def get_backtest_results():
    if not _backtest_cache:
        return jsonify({"status": "processing", "message": "Backtest is running..."}), 202
    return safe_jsonify({
        "status": "success",
        "last_updated": _last_backtest_update.isoformat(),
        "results": _backtest_cache
    })

# ── Serve login.html ─────────────────────────────────────────────────
@app.route("/login")
@app.route("/login.html")
def serve_login():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "login.html")

# ── Auth API routes ───────────────────────────────────────────────────
@app.route("/api/auth/me")
@require_auth
def auth_me():
    """Return current user info + role."""
    email = (request.user_payload.get("email") or
             (request.user_payload.get("user_metadata") or {}).get("email") or "")
    return jsonify({
        "email": email,
        "role": request.user_role,
        "user_id": request.user_payload.get("sub"),
    })

@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    """Verify a token and return role — called by frontend on load."""
    body = request.get_json(silent=True) or {}
    token = body.get("token", "")
    payload = _verify_token(token)
    if not payload:
        return jsonify({"valid": False}), 401
    email = (payload.get("email") or
             (payload.get("user_metadata") or {}).get("email") or "")
    return jsonify({
        "valid": True,
        "email": email,
        "role": _get_user_role(payload),
        "user_id": payload.get("sub"),
    })

# ── Admin-only: user management ───────────────────────────────────────
@app.route("/api/admin/users")
@require_admin
def admin_list_users():
    """List all registered users from Supabase."""
    if not _supabase_admin:
        return jsonify({"error": "Supabase not configured"}), 503
    try:
        resp = _supabase_admin.auth.admin.list_users()
        users = []
        for u in (resp or []):
            users.append({
                "id":           u.id,
                "email":        u.email,
                "created_at":   str(u.created_at),
                "last_sign_in": str(u.last_sign_in_at),
                "confirmed":    u.email_confirmed_at is not None,
                "role":         "admin" if u.email == ADMIN_EMAIL else "user",
            })
        return jsonify({"users": users, "total": len(users)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<user_id>", methods=["DELETE"])
@require_admin
def admin_delete_user(user_id):
    """Delete a user from Supabase (admin only)."""
    if not _supabase_admin:
        return jsonify({"error": "Supabase not configured"}), 503
    try:
        _supabase_admin.auth.admin.delete_user(user_id)
        return jsonify({"status": "deleted", "user_id": user_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/stats")
@require_admin
def admin_stats():
    """Return platform stats — admin only."""
    today = datetime.now().strftime("%Y-%m-%d")
    stats = {
        "date": today,
        "total_fo_stocks": len(FO_STOCKS),
        "admin_email": ADMIN_EMAIL,
        "supabase_connected": _supabase_admin is not None,
        "mongo_connected": MONGO_OK,
        "agent_open_trades": 0,
        "scanner_running": _agent_running if '_agent_running' in globals() else False,
    }
    return jsonify(stats)

# ── Fix chart API (use daily cache, not slow yfinance 1m) ─────────────
@app.route("/api/stock/<symbol>/chart/1d")
def get_stock_chart_1d(symbol):
    try:
        hist = None
        if _daily_history_cache is not None:
            try:
                sym_ns = symbol + ".NS"
                cols = _daily_history_cache.columns
                if hasattr(cols, 'levels') and len(cols.levels) == 2:
                    if sym_ns in cols.levels[1]:
                        hist = _daily_history_cache.xs(sym_ns, axis=1, level=1)
                    elif sym_ns in cols.levels[0]:
                        hist = _daily_history_cache[sym_ns]
            except Exception: pass
        if hist is not None and not hist.empty:
            hist = hist.dropna(subset=["Close"])
            return jsonify({
                "closes": [round(float(c), 2) for c in hist["Close"]],
                "opens":  [round(float(c), 2) for c in hist["Open"]],
                "highs":  [round(float(c), 2) for c in hist["High"]],
                "lows":   [round(float(c), 2) for c in hist["Low"]],
                "times":  [int(d.timestamp()) for d in hist.index],
                "source": "cache"
            })
        ticker = yf.Ticker(f"{symbol}.NS")
        df = ticker.history(period="60d", interval="1d")
        if df.empty: return jsonify({"error": "No data"}), 404
        df = df.dropna(subset=["Close"])
        return jsonify({
            "closes": [round(float(c), 2) for c in df["Close"]],
            "opens":  [round(float(c), 2) for c in df["Open"]],
            "highs":  [round(float(c), 2) for c in df["High"]],
            "lows":   [round(float(c), 2) for c in df["Low"]],
            "times":  [int(t.timestamp()) for t in df.index],
            "source": "yfinance"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
#  AI AGENT  — Professional v3  (ONE trade · BUY LOW · SELL TOP)
# ═══════════════════════════════════════════════════════════════════════
_ag_cfg = {
    "broker_mode":"paper","capital":100000.0,"max_risk_pct":0.5,
    "max_open_trades":1,"min_score":3,"no_entry_after":"14:00",
    "force_exit_at":"15:10","trailing_enabled":True,"trail_trigger_pct":0.7,
    "trail_step_pct":0.4,"max_daily_loss_pct":2.0,"max_consec_losses":2,
    "cooldown_min":45,"buy_max_rsi":50,"sell_min_rsi":50,
    "buy_max_chg_pct":2.5,"sell_min_chg_pct":-2.5,
    "use_oi_confirmation":True,"min_oi_change":5.0,
    "kite_api_key":os.environ.get("KITE_API_KEY",""),
    "kite_access_token":os.environ.get("KITE_ACCESS_TOKEN",""),
    "anthropic_api_key":os.environ.get("ANTHROPIC_API_KEY",""),
}
_ag_open: list = []; _agent_running = False; _agent_paused = False
_ag_lock = threading.Lock(); _ag_sse_queues: list = []
_ag_last_trade_time = datetime.min; _ag_traded_today: set = set()

def _ag_save(t):
    if MONGO_OK: agent_trades_col.replace_one({"trade_id":t["trade_id"]},t,upsert=True)
    else:
        global _ag_mem_trades
        _ag_mem_trades=[x for x in _ag_mem_trades if x["trade_id"]!=t["trade_id"]]
        _ag_mem_trades.append(t)
        # Save to CSV
        _save_to_csv(AGENT_TRADES_CSV, _ag_mem_trades, [
            'trade_id', 'symbol', 'name', 'side', 'entry', 'sl', 'target', 'qty', 'status',
            'open_time', 'exit_time', 'exit_price', 'exit_reason', 'p_l', 'p_l_pct',
            'broker_mode', 'order_id', 'score', 'rsi_at_entry', 'chg_at_entry', 'confidence',
            'ai_reason', 'curr_price', 'peak_price', 'trail_sl'
        ])
def _ag_archive(t):
    if MONGO_OK: agent_journal_col.insert_one({**t}); agent_trades_col.delete_one({"trade_id":t["trade_id"]})
    else:
        _ag_mem_journal.append(t)
        # Save journal to CSV
        _save_to_csv(AGENT_JOURNAL_CSV, _ag_mem_journal, [
            'trade_id', 'symbol', 'name', 'side', 'entry', 'sl', 'target', 'qty', 'status',
            'open_time', 'exit_time', 'exit_price', 'exit_reason', 'p_l', 'p_l_pct',
            'broker_mode', 'order_id', 'score', 'rsi_at_entry', 'chg_at_entry', 'confidence',
            'ai_reason', 'curr_price', 'peak_price', 'trail_sl'
        ])
        # Remove from open trades CSV
        global _ag_mem_trades
        _ag_mem_trades=[x for x in _ag_mem_trades if x["trade_id"]!=t["trade_id"]]
        _save_to_csv(AGENT_TRADES_CSV, _ag_mem_trades, [
            'trade_id', 'symbol', 'name', 'side', 'entry', 'sl', 'target', 'qty', 'status',
            'open_time', 'exit_time', 'exit_price', 'exit_reason', 'p_l', 'p_l_pct',
            'broker_mode', 'order_id', 'score', 'rsi_at_entry', 'chg_at_entry', 'confidence',
            'ai_reason', 'curr_price', 'peak_price', 'trail_sl'
        ])
def _ag_log(sym,dec,stk):
    doc={"ts":datetime.now().isoformat(),"symbol":sym,"action":dec.get("action"),
         "score":dec.get("score"),"reason":dec.get("reason"),
         "entry":dec.get("entry"),"sl":dec.get("sl"),"target":dec.get("target"),
         "rsi":dec.get("rsi"),"chg":dec.get("chg"),"qty":dec.get("qty")}
    if MONGO_OK: agent_log_col.insert_one(doc)
    else:
        _ag_mem_log.append(doc)
        if len(_ag_mem_log)>200: _ag_mem_log.pop(0)
        # Save log to CSV (keep last 200 entries)
        _save_to_csv(AGENT_LOG_CSV, _ag_mem_log[-200:], [
            'ts', 'symbol', 'action', 'score', 'reason', 'entry', 'sl', 'target', 'rsi', 'chg', 'qty'
        ])
def _ag_load():
    global _ag_open
    if MONGO_OK: _ag_open=list(agent_trades_col.find({"status":"OPEN"},{"_id":0}))
    else: _ag_open=[t for t in _ag_mem_trades if t.get("status")=="OPEN"]
def _ag_day_pl():
    today=datetime.now().strftime("%Y-%m-%d")
    if MONGO_OK: docs=list(agent_journal_col.find({"exit_time":{"$regex":f"^{today}"}}))
    else: docs=[t for t in _ag_mem_journal if t.get("exit_time","").startswith(today)]
    return sum(t.get("p_l",0) for t in docs)
def _ag_consec():
    if MONGO_OK: recent=list(agent_journal_col.find({},{"p_l":1},sort=[("exit_time",-1)],limit=5))
    else: recent=sorted(_ag_mem_journal,key=lambda x:x.get("exit_time",""),reverse=True)[:5]
    c=0
    for t in recent:
        if t.get("p_l",0)<0: c+=1
        else: break
    return c
def _ag_push(evt,data):
    msg=f"data: {json.dumps({'type':evt,'payload':data})}\n\n"
    dead=[]
    for q in _ag_sse_queues:
        try: q.put_nowait(msg)
        except: dead.append(q)
    for q in dead:
        try: _ag_sse_queues.remove(q)
        except: pass
def _ag_order(sym,side,qty,price):
    if _ag_cfg["broker_mode"]=="zerodha":
        from kiteconnect import KiteConnect
        kite=KiteConnect(api_key=_ag_cfg["kite_api_key"])
        kite.set_access_token(_ag_cfg["kite_access_token"])
        tx=kite.TRANSACTION_TYPE_BUY if side=="BUY" else kite.TRANSACTION_TYPE_SELL
        oid=kite.place_order(variety=kite.VARIETY_REGULAR,exchange=kite.EXCHANGE_NSE,
            tradingsymbol=sym,transaction_type=tx,quantity=qty,
            product=kite.PRODUCT_MIS,order_type=kite.ORDER_TYPE_MARKET)
        return str(oid)
    oid=f"PAPER-{sym}-{int(time.time())}"; print(f"[PAPER] {side} {qty}×{sym} @ ₹{price:.2f}"); return oid
def _ag_ltp(sym):
    with _scan_lock:
        for s in _last_scan.get("data",[]):
            if s.get("symbol")==sym: return float(s.get("curr_close",0))
    return None
def _ag_score(stk):
    score=0; reasons=[]
    sig=stk.get("signal",""); ai_s=stk.get("ai_signal","")
    rsi=float(stk.get("ai_rsi") or 50); rvol=float(stk.get("rel_volume") or 1.0)
    mom=float(stk.get("momentum") or 0); oi=float((stk.get("oi") or {}).get("avgInOI",0))
    chg=float(stk.get("change_pct") or 0); curr=float(stk.get("curr_close") or 0)
    sup=float(stk.get("support") or 0); res=float(stk.get("resistance") or 0)
    perf=stk.get("perfect_setup",{}).get("is_perfect",False)
    sweep=stk.get("liquidity_sweep",{}).get("sweep_side")
    entry=float(stk.get("ai_entry") or curr); sl=float(stk.get("ai_sl") or 0)
    tgt=float(stk.get("ai_target") or 0)
    action="SKIP"
    
    # Determine action based on signals
    if "BUY" in sig or ai_s=="BUY": action="BUY"
    elif "SELL" in sig or ai_s=="SELL": action="SELL"
    if action=="SKIP": return {"action":"SKIP","score":0,"reason":"No directional signal"}
    
    # OI Confirmation (if enabled)
    if _ag_cfg.get("use_oi_confirmation", False) and abs(oi) >= _ag_cfg.get("min_oi_change", 5.0):
        if action=="BUY" and oi < 0:
            return {"action":"SKIP","score":0,"reason":f"BUY BLOCKED: OI declining {oi:.0f}% (bearish)"}
        elif action=="SELL" and oi > 0:
            return {"action":"SKIP","score":0,"reason":f"SELL BLOCKED: OI rising {oi:.0f}% (bullish)"}
    
    # BUY Trade Criteria
    if action=="BUY":
        if rsi>_ag_cfg["buy_max_rsi"]: return {"action":"SKIP","score":0,"reason":f"BUY BLOCKED: RSI {rsi:.0f}>{_ag_cfg['buy_max_rsi']}"}
        if chg>_ag_cfg["buy_max_chg_pct"]: return {"action":"SKIP","score":0,"reason":f"BUY BLOCKED: already up {chg:.1f}%"}
        if rsi<25: score+=3; reasons.append(f"RSI deeply oversold {rsi:.0f}")
        elif rsi<35: score+=2; reasons.append(f"RSI oversold {rsi:.0f}")
        elif rsi<45: score+=1.5; reasons.append(f"RSI low {rsi:.0f}")
        else: score+=1; reasons.append(f"RSI neutral-low {rsi:.0f}")
        if sup>0 and curr>0:
            d=(curr-sup)/curr*100
            if d<=0.5: score+=2; reasons.append(f"At support ₹{sup:.0f}")
            elif d<=1.0: score+=1; reasons.append(f"Near support ₹{sup:.0f}")
        if oi > _ag_cfg.get("min_oi_change", 5.0):
            score+=1.5; reasons.append(f"OI rising {oi:.0f}% (bullish)")
    
    # SELL Trade Criteria (More Balanced)
    elif action=="SELL":
        if rsi<_ag_cfg["sell_min_rsi"]: return {"action":"SKIP","score":0,"reason":f"SELL BLOCKED: RSI {rsi:.0f}<{_ag_cfg['sell_min_rsi']}"}
        if chg<_ag_cfg["sell_min_chg_pct"]: return {"action":"SKIP","score":0,"reason":f"SELL BLOCKED: already down {chg:.1f}%"}
        if rsi>75: score+=3; reasons.append(f"RSI deeply OB {rsi:.0f}")
        elif rsi>65: score+=2; reasons.append(f"RSI overbought {rsi:.0f}")
        elif rsi>55: score+=1.5; reasons.append(f"RSI elevated {rsi:.0f}")
        else: score+=1; reasons.append(f"RSI neutral-high {rsi:.0f}")
        if res>0 and curr>0:
            d=(res-curr)/curr*100
            if d<=0.5: score+=2; reasons.append(f"At resistance ₹{res:.0f}")
            elif d<=1.0: score+=1; reasons.append(f"Near resistance ₹{res:.0f}")
        if oi < -_ag_cfg.get("min_oi_change", 5.0):
            score+=1.5; reasons.append(f"OI declining {oi:.0f}% (bearish)")
    
    # Validate trade geometry
    if action=="BUY" and sl and tgt and (sl>=entry or tgt<=entry): return {"action":"SKIP","score":0,"reason":"BUY geometry invalid"}
    if action=="SELL" and sl and tgt and (sl<=entry or tgt>=entry): return {"action":"SKIP","score":0,"reason":"SELL geometry invalid"}
    if entry>0 and sl>0 and tgt>0:
        risk=abs(entry-sl); rwd=abs(tgt-entry)
        if rwd<risk*1.8: return {"action":"SKIP","score":0,"reason":f"RR {rwd/risk:.1f}:1 below 1.8:1 min"}
    
    # Additional scoring factors
    if perf:          score+=3; reasons.append("Perfect Setup")
    if sweep==action: score+=2; reasons.append("Liquidity Sweep")
    if sig==ai_s:     score+=1; reasons.append("TV+AI agree")
    if rvol>=4.0:     score+=1; reasons.append(f"Vol {rvol:.1f}x")
    elif rvol>=2.5:   score+=0.5
    if abs(mom)>=1.5: score+=0.5; reasons.append(f"Mom {mom:+.1f}%")
    
    # Calculate quantity
    qty=0
    if entry>0 and sl>0:
        rps=abs(entry-sl)
        if rps>0: qty=max(1,int(_ag_cfg["capital"]*(_ag_cfg["max_risk_pct"]/100)/rps))
    if qty==0: return {"action":"SKIP","score":0,"reason":"Qty=0 — SL too wide"}
    conf="HIGH" if score>=8 else "MEDIUM" if score>=6 else "LOW"
    return {"action":action,"score":round(score,1),"confidence":conf,"reason":" | ".join(reasons),
            "entry":round(entry,2),"sl":round(sl,2),"target":round(tgt,2),"qty":qty,
            "rsi":round(rsi,1),"chg":round(chg,2)}
def _ag_decide(stk):
    r=_ag_score(stk)
    if r["score"]<_ag_cfg["min_score"]: r["action"]="SKIP"; return r
    key=_ag_cfg.get("anthropic_api_key","")
    if not key: return r
    try:
        import anthropic
        c=anthropic.Anthropic(api_key=key)
        p=f"""NSE F&O trader AI. BUY LOW/SELL TOP. ONE trade at a time.
{stk.get('name')} ({stk.get('symbol')}) Signal:{stk.get('signal')} RSI:{stk.get('ai_rsi')} LTP:₹{stk.get('curr_close')} Chg:{stk.get('change_pct')}%
Vol:{stk.get('rel_volume')}x Sup:₹{stk.get('support')} Res:₹{stk.get('resistance')} OI:{(stk.get('oi') or {}).get('avgInOI',0)}%
Entry:₹{r['entry']} SL:₹{r['sl']} Tgt:₹{r['target']} RuleScore:{r['score']}/10
BUY only RSI<40+near support. SELL only RSI>65+near resistance. Min 1.8:1 RR.
Output ONLY JSON: {{"action":"BUY"|"SELL"|"SKIP","score":1-10,"confidence":"HIGH"|"MEDIUM"|"LOW","reason":"<20 words>","entry":<f>,"sl":<f>,"target":<f>,"qty":{r['qty']}}}"""
        resp=c.messages.create(model="claude-sonnet-4-20250514",max_tokens=200,messages=[{"role":"user","content":p}])
        raw=resp.content[0].text.strip().strip("```json").strip("```").strip()
        res=json.loads(raw)
        a=res.get("action"); e=float(res.get("entry",0)); s=float(res.get("sl",0)); t=float(res.get("target",0))
        if a=="BUY" and (s>=e or t<=e): res["action"]="SKIP"
        if a=="SELL" and (s<=e or t>=e): res["action"]="SKIP"
        if res.get("score",0)<_ag_cfg["min_score"]: res["action"]="SKIP"
        return res
    except Exception as ex: print(f"[AGENT] Claude err:{ex}"); return r
def _ag_enter(dec,stk):
    global _ag_open,_ag_last_trade_time,_ag_traded_today
    with _ag_lock:
        if len(_ag_open)>=_ag_cfg["max_open_trades"]: return None
        sym=stk["symbol"]
        if any(t["symbol"]==sym for t in _ag_open) or sym in _ag_traded_today: return None
        oid=_ag_order(sym,dec["action"],dec["qty"],dec["entry"])
        t={"trade_id":f"{sym}-{int(time.time())}","symbol":sym,"name":stk.get("name",sym),
           "side":dec["action"],"qty":dec["qty"],"entry":dec["entry"],
           "sl":dec["sl"],"trail_sl":dec["sl"],"target":dec["target"],
           "curr_price":dec["entry"],"peak_price":dec["entry"],"status":"OPEN","order_id":oid,
           "score":dec["score"],"confidence":dec["confidence"],"ai_reason":dec["reason"],
           "open_time":datetime.now().isoformat(),"p_l":0.0,"p_l_pct":0.0,
           "broker_mode":_ag_cfg["broker_mode"],"rsi_at_entry":dec.get("rsi"),"chg_at_entry":dec.get("chg")}
        _ag_open.append(t); _ag_save(t)
        _ag_last_trade_time=datetime.now(); _ag_traded_today.add(sym)
        print(f"[AGENT] ✅ {dec['action']} {dec['qty']}×{sym} @ ₹{dec['entry']:.2f} SL ₹{dec['sl']:.2f} TGT ₹{dec['target']:.2f} RSI:{dec.get('rsi')} Score:{dec['score']}/10")
        _ag_push("TRADE_ENTERED",{"trade_id":t["trade_id"],"symbol":sym,"name":t["name"],
            "side":dec["action"],"entry":dec["entry"],"sl":dec["sl"],"target":dec["target"],
            "qty":dec["qty"],"score":dec["score"],"confidence":dec["confidence"],
            "reason":dec["reason"],"rsi":dec.get("rsi"),"chg":dec.get("chg")})
        return t
def _ag_trail(t,ltp):
    side=t["side"]; e=t["entry"]
    trig=_ag_cfg["trail_trigger_pct"]/100; step=_ag_cfg["trail_step_pct"]/100
    if side=="BUY":
        if (ltp-e)/e>=trig:
            t["peak_price"]=max(t.get("peak_price",ltp),ltp)
            nt=round(t["peak_price"]*(1-step),2)
            if nt>t["trail_sl"]: t["trail_sl"]=nt; print(f"[AGENT] 📈 TRAIL {t['symbol']} SL→₹{nt}")
    else:
        if (e-ltp)/e>=trig:
            t["peak_price"]=min(t.get("peak_price",ltp),ltp)
            nt=round(t["peak_price"]*(1+step),2)
            if nt<t["trail_sl"]: t["trail_sl"]=nt; print(f"[AGENT] 📉 TRAIL {t['symbol']} SL→₹{nt}")
def _ag_close(t,xp,reason):
    global _ag_open
    sym=t["symbol"]; e=t["entry"]; q=t["qty"]; side=t["side"]
    try: _ag_order(sym,"SELL" if side=="BUY" else "BUY",q,xp)
    except: pass
    pl=(xp-e)*q if side=="BUY" else (e-xp)*q; pp=round(pl/(e*q)*100,2) if e*q else 0
    t.update({"status":"CLOSED","exit_price":round(xp,2),"exit_reason":reason,
              "exit_time":datetime.now().isoformat(),"p_l":round(pl,2),"p_l_pct":pp})
    print(f"[AGENT] {'✅' if pl>=0 else '❌'} {sym} {reason}: ₹{e}→₹{xp:.2f} P/L ₹{pl:+.2f}")
    _ag_archive(t); _ag_open=[x for x in _ag_open if x["trade_id"]!=t["trade_id"]]
    _ag_push("TRADE_CLOSED",{"symbol":sym,"side":side,"entry":e,"exit_price":round(xp,2),"p_l":round(pl,2),"p_l_pct":pp,"reason":reason})
def _ag_monitor():
    now=datetime.now(); h,m=map(int,_ag_cfg["force_exit_at"].split(":"))
    eod=now>=now.replace(hour=h,minute=m,second=0)
    with _ag_lock:
        for t in list(_ag_open):
            ltp=_ag_ltp(t["symbol"])
            if not ltp: continue
            if _ag_cfg["trailing_enabled"]: _ag_trail(t,ltp)
            sl=t["trail_sl"]; tgt=t["target"]; side=t["side"]; e=t["entry"]; q=t["qty"]
            pl=(ltp-e)*q if side=="BUY" else (e-ltp)*q
            t["curr_price"]=ltp; t["p_l"]=round(pl,2)
            t["p_l_pct"]=round(pl/(e*q)*100,2) if e*q else 0; _ag_save(t)
            if (side=="BUY" and ltp<=sl) or (side=="SELL" and ltp>=sl): _ag_close(t,ltp,"STOP LOSS")
            elif (side=="BUY" and ltp>=tgt) or (side=="SELL" and ltp<=tgt): _ag_close(t,ltp,"TARGET HIT")
            elif eod: _ag_close(t,ltp,"EOD EXIT")
def _ag_candidates():
    with _scan_lock: all_s=list(_last_scan.get("data",[]))
    done={t["symbol"] for t in _ag_open}|_ag_traded_today
    def ok(s):
        sig=s.get("signal",""); ai=s.get("ai_signal","")
        return (("BUY" in sig or "SELL" in sig or ai in ("BUY","SELL")) and s.get("symbol") not in done)
    def rank(s):
        rsi=float(s.get("ai_rsi") or 50); sig=s.get("signal","")
        rq=(50-rsi) if "BUY" in sig else (rsi-50) if "SELL" in sig else 0
        return (10 if s.get("perfect_setup",{}).get("is_perfect") else 0)+(5 if s.get("liquidity_sweep",{}).get("sweep_side") else 0)+rq*0.3+float(s.get("rel_volume") or 1)*0.5
    f=[s for s in all_s if ok(s)]; f.sort(key=rank,reverse=True); return f[:8]
def _ag_cycle():
    global _agent_paused
    dl=_ag_day_pl(); ml=-_ag_cfg["capital"]*(_ag_cfg["max_daily_loss_pct"]/100)
    if dl<ml: print(f"[AGENT] ⛔ Day loss limit"); _agent_paused=True; return
    if _ag_consec()>=_ag_cfg["max_consec_losses"]: print("[AGENT] ⛔ Consec losses"); _agent_paused=True; return
    _ag_monitor()
    if not is_market_open(): return
    now=datetime.now(); h,m=map(int,_ag_cfg["no_entry_after"].split(":"))
    if now>=now.replace(hour=h,minute=m,second=0): return
    if len(_ag_open)>=_ag_cfg["max_open_trades"]: return
    if (now-_ag_last_trade_time).total_seconds()/60<_ag_cfg["cooldown_min"]: return
    for stk in _ag_candidates():
        dec=_ag_decide(stk); _ag_log(stk["symbol"],dec,stk)
        if dec["action"] in ("BUY","SELL") and dec["score"]>=_ag_cfg["min_score"]:
            print(f"[AGENT] 🎯 {stk['symbol']} {dec['score']}/10 {dec['reason'][:55]}")
            _ag_enter(dec,stk); break
def _ag_loop():
    global _ag_traded_today
    _ag_load(); _ag_traded_today=set()
    print("[AGENT] 🤖 Professional AI Agent v3 — BUY LOW · SELL TOP · ONE TRADE")
    last_day=datetime.now().date()
    while _agent_running:
        try:
            if datetime.now().date()!=last_day: _ag_traded_today=set(); last_day=datetime.now().date()
            if not _agent_paused: _ag_cycle()
        except Exception as ex: print(f"[AGENT ERR] {ex}")
        time.sleep(30)

@app.route("/api/agent/status")
def agent_status():
    mins=(datetime.now()-_ag_last_trade_time).total_seconds()/60
    return safe_jsonify({"running":_agent_running,"paused":_agent_paused,
        "broker_mode":_ag_cfg["broker_mode"],"open_trades":len(_ag_open),
        "daily_pl":round(_ag_day_pl(),2),"capital":_ag_cfg["capital"],
        "max_trades":_ag_cfg["max_open_trades"],"min_score":_ag_cfg["min_score"],
        "cooldown_remaining_min":round(max(0,_ag_cfg["cooldown_min"]-mins),1),
        "buy_max_rsi":_ag_cfg["buy_max_rsi"],"sell_min_rsi":_ag_cfg["sell_min_rsi"],
        "traded_today":list(_ag_traded_today),"timestamp":datetime.now().isoformat()})
@app.route("/api/agent/start",methods=["POST"])
def agent_start():
    global _agent_running,_agent_paused
    body=request.get_json(silent=True) or {}
    for k in ("broker_mode","capital","max_open_trades","max_risk_pct","min_score","cooldown_min",
              "buy_max_rsi","sell_min_rsi","max_daily_loss_pct","kite_api_key","kite_access_token","anthropic_api_key"):
        if k in body: _ag_cfg[k]=body[k]
    if _agent_running: return jsonify({"status":"already_running"})
    _agent_running=True; _agent_paused=False
    threading.Thread(target=_ag_loop,daemon=True).start()
    return jsonify({"status":"started","mode":_ag_cfg["broker_mode"]})
@app.route("/api/agent/stop",methods=["POST"])
def agent_stop():
    global _agent_running; _agent_running=False; return jsonify({"status":"stopped"})
@app.route("/api/agent/pause",methods=["POST"])
def agent_pause_r():
    global _agent_paused; _agent_paused=True; return jsonify({"status":"paused"})
@app.route("/api/agent/resume",methods=["POST"])
def agent_resume_r():
    global _agent_paused; _agent_paused=False; return jsonify({"status":"resumed"})
@app.route("/api/agent/trades")
def agent_trades_api():
    today=datetime.now().strftime("%Y-%m-%d")
    if MONGO_OK:
        op=list(agent_trades_col.find({"status":"OPEN"},{"_id":0}))
        cl=list(agent_journal_col.find({},{"_id":0},sort=[("exit_time",-1)],limit=50))
    else:
        op=_ag_open; cl=list(reversed(_ag_mem_journal[-50:]))
    tpl=sum(t.get("p_l",0) for t in cl if t.get("exit_time","").startswith(today))
    return safe_jsonify({"open_trades":op,"closed_trades":cl,"daily_pl":round(tpl,2),"open_count":len(op)})
@app.route("/api/agent/log")
def agent_log_api():
    lim=int(request.args.get("limit",80))
    if MONGO_OK: logs=list(agent_log_col.find({},{"_id":0},sort=[("ts",-1)],limit=lim))
    else: logs=list(reversed(_ag_mem_log[-lim:]))
    return safe_jsonify({"log":logs,"count":len(logs)})
@app.route("/api/agent/config",methods=["GET"])
def agent_cfg_get():
    return jsonify({k:v for k,v in _ag_cfg.items() if "token" not in k and "key" not in k})
@app.route("/api/agent/config",methods=["POST"])
def agent_cfg_set():
    body=request.get_json(silent=True) or {}
    changed=[k for k,v in body.items() if k in _ag_cfg and not _ag_cfg.update({k:v})]  # type: ignore
    return jsonify({"updated":changed})
@app.route("/api/agent/close/<tid>",methods=["POST"])
def agent_close_r(tid):
    with _ag_lock:
        t=next((x for x in _ag_open if x["trade_id"]==tid),None)
        if not t: return jsonify({"error":"Not found"}),404
        ltp=_ag_ltp(t["symbol"]) or t["curr_price"]; _ag_close(t,ltp,"MANUAL")
    return jsonify({"status":"closed","trade_id":tid})
@app.route("/api/agent/events")
def agent_events():
    import queue
    q=queue.Queue(maxsize=20); _ag_sse_queues.append(q)
    def gen():
        try:
            yield 'data: {"type":"connected"}\n\n'
            while True:
                try: yield q.get(timeout=20)
                except: yield ": ping\n\n"
        finally:
            try: _ag_sse_queues.remove(q)
            except: pass
    return Response(gen(),mimetype="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

print("[OK] AI Agent v3 + Auth routes ready")

# ══════════════════════════════════════════════════════════════════
#  TRADING JOURNAL & DAILY REPORT ROUTES
# ══════════════════════════════════════════════════════════════════
try:
    from journal_api import register_journal_routes
    register_journal_routes(app)
except Exception as e:
    print(f"[WARN] Journal routes not loaded: {e}")

# Start backtest thread
threading.Thread(target=refresh_global_backtest, daemon=True).start()

if __name__ == "__main__":
    _watchlist_state_cache_v2.clear()
    scanner_thread = threading.Thread(target=background_scanner, daemon=True)
    scanner_thread.start()
    print("=" * 62)
    print("  NSE F&O Scanner + AI Agent v3 + Supabase Auth")
    print("  Login:     http://localhost:5000/login")
    print("  Dashboard: http://localhost:5000  (auth required)")
    print("  Admin:     set ADMIN_EMAIL env var")
    print("=" * 62)
    app.run(debug=False, port=5000, host="0.0.0.0")
