"""
Sector mapping for NSE F&O stocks
Maps stock symbols to their respective sectors
"""

SECTOR_MAP = {
    # Banking & Financial Services
    "AXISBANK": "Banking", "HDFCBANK": "Banking", "ICICIBANK": "Banking",
    "SBIN": "Banking", "KOTAKBANK": "Banking", "INDUSINDBK": "Banking",
    "BANDHANBNK": "Banking", "FEDERALBNK": "Banking", "IDFCFIRSTB": "Banking",
    "PNB": "Banking", "BANKBARODA": "Banking", "BANKINDIA": "Banking",
    "CANBK": "Banking", "UNIONBANK": "Banking", "YESBANK": "Banking",
    "RBLBANK": "Banking",
    
    "BAJFINANCE": "Financial Services", "BAJAJFINSV": "Financial Services",
    "CHOLAFIN": "Financial Services", "SHRIRAMFIN": "Financial Services",
    "MUTHOOTFIN": "Financial Services", "MANAPPURAM": "Financial Services",
    "LTF": "Financial Services", "LICHSGFIN": "Financial Services",
    "PNBHOUSING": "Financial Services", "ABCAPITAL": "Financial Services",
    
    "HDFCLIFE": "Insurance", "ICICIGI": "Insurance", "ICICIPRULI": "Insurance",
    "SBILIFE": "Insurance", "SBICARD": "Insurance", "LICI": "Insurance",
    
    # IT Services
    "TCS": "IT Services", "INFY": "IT Services", "WIPRO": "IT Services",
    "HCLTECH": "IT Services", "TECHM": "IT Services", "LTIM": "IT Services",
    "COFORGE": "IT Services", "PERSISTENT": "IT Services", "MPHASIS": "IT Services",
    "KPITTECH": "IT Services", "TATAELXSI": "IT Services",
    
    # Automobiles
    "MARUTI": "Automobiles", "M&M": "Automobiles", "TATAMOTORS": "Automobiles",
    "BAJAJ-AUTO": "Automobiles", "EICHERMOT": "Automobiles", "HEROMOTOCO": "Automobiles",
    "TVSMOTOR": "Automobiles", "ASHOKLEY": "Automobiles", "MOTHERSON": "Automobiles",
    "SONACOMS": "Automobiles", "TIINDIA": "Automobiles", "UNOMINDA": "Automobiles",
    "EXIDEIND": "Automobiles", "AMBUJACEM": "Automobiles",
    
    # Pharmaceuticals
    "SUNPHARMA": "Pharmaceuticals", "DRREDDY": "Pharmaceuticals", "CIPLA": "Pharmaceuticals",
    "DIVISLAB": "Pharmaceuticals", "AUROPHARMA": "Pharmaceuticals", "LUPIN": "Pharmaceuticals",
    "BIOCON": "Pharmaceuticals", "TORNTPHARM": "Pharmaceuticals", "ALKEM": "Pharmaceuticals",
    "LAURUSLABS": "Pharmaceuticals", "GLENMARK": "Pharmaceuticals", "MANKIND": "Pharmaceuticals",
    "ZYDUSLIFE": "Pharmaceuticals", "SYNGENE": "Pharmaceuticals", "PPLPHARMA": "Pharmaceuticals",
    
    # Oil & Gas
    "RELIANCE": "Oil & Gas", "ONGC": "Oil & Gas", "BPCL": "Oil & Gas",
    "IOC": "Oil & Gas", "HINDPETRO": "Oil & Gas", "GAIL": "Oil & Gas",
    "OIL": "Oil & Gas", "PETRONET": "Oil & Gas",
    
    # Metals & Mining
    "TATASTEEL": "Metals & Mining", "HINDALCO": "Metals & Mining", "JSWSTEEL": "Metals & Mining",
    "VEDL": "Metals & Mining", "COALINDIA": "Metals & Mining", "NMDC": "Metals & Mining",
    "SAIL": "Metals & Mining", "JINDALSTEL": "Metals & Mining", "HINDZINC": "Metals & Mining",
    "NATIONALUM": "Metals & Mining",
    
    # Power & Energy
    "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power",
    "ADANIGREEN": "Power", "ADANIENSOL": "Power", "JSWENERGY": "Power",
    "TORNTPOWER": "Power", "NHPC": "Power", "SUZLON": "Power",
    "INOXWIND": "Power", "WAAREEENER": "Power", "PREMIERENE": "Power",
    
    # Cement
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "DALBHARAT": "Cement",
    
    # Consumer Goods
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "BRITANNIA": "FMCG",
    "NESTLEIND": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
    "GODREJCP": "FMCG", "COLPAL": "FMCG", "TATACONSUM": "FMCG",
    "VBL": "FMCG", "PATANJALI": "FMCG", "UNITDSPR": "FMCG",
    
    # Retail
    "DMART": "Retail", "TRENT": "Retail", "TITAN": "Retail",
    "NYKAA": "Retail", "KALYANKJIL": "Retail", "JUBLFOOD": "Retail",
    
    # Real Estate
    "DLF": "Real Estate", "GODREJPROP": "Real Estate", "OBEROIRLTY": "Real Estate",
    "PRESTIGE": "Real Estate", "PHOENIXLTD": "Real Estate", "LODHA": "Real Estate",
    
    # Telecom
    "BHARTIARTL": "Telecom", "IDEA": "Telecom", "INDUSTOWER": "Telecom",
    "INDIGO": "Aviation",
    
    # Infrastructure & Construction
    "LT": "Infrastructure", "ADANIENT": "Infrastructure", "ADANIPORTS": "Infrastructure",
    "CONCOR": "Infrastructure", "GMRAIRPORT": "Infrastructure", "RVNL": "Infrastructure",
    "NBCC": "Infrastructure", "HUDCO": "Infrastructure", "IRFC": "Infrastructure",
    "IREDA": "Infrastructure",
    
    # Capital Goods
    "SIEMENS": "Capital Goods", "ABB": "Capital Goods", "BHEL": "Capital Goods",
    "BEL": "Capital Goods", "HAL": "Capital Goods", "BDL": "Capital Goods",
    "CUMMINSIND": "Capital Goods", "BOSCHLTD": "Capital Goods", "POWERINDIA": "Capital Goods",
    "BHARATFORG": "Capital Goods", "MAZDOCK": "Capital Goods",
    
    # Chemicals
    "UPL": "Chemicals", "SRF": "Chemicals", "PIIND": "Chemicals",
    "AARTI": "Chemicals", "DEEPAKNTR": "Chemicals", "GNFC": "Chemicals",
    
    # Textiles & Apparel
    "PAGEIND": "Textiles",
    
    # Hotels & Hospitality
    "INDHOTEL": "Hotels", "APOLLOHOSP": "Healthcare",
    "FORTIS": "Healthcare", "MAXHEALTH": "Healthcare",
    
    # Diversified
    "ADANIPOWER": "Power", "CGPOWER": "Capital Goods",
    "POLYCAB": "Cables", "KEI": "Cables", "HAVELLS": "Electricals",
    "CROMPTON": "Electricals", "VOLTAS": "Consumer Durables",
    "BLUESTARCO": "Consumer Durables", "DIXON": "Electronics",
    "AMBER": "Consumer Durables", "KAYNES": "Electronics",
    
    # Paints & Building Materials
    "ASIANPAINT": "Paints", "PIDILITIND": "Chemicals",
    "ASTRAL": "Building Materials", "APLAPOLLO": "Building Materials",
    "SUPREMEIND": "Building Materials",
    
    # Financial Market Infrastructure
    "BSE": "Financial Services", "MCX": "Financial Services",
    "CDSL": "Financial Services", "CAMS": "Financial Services",
    "KFINTECH": "Financial Services", "NUVAMA": "Financial Services",
    
    # Fintech & New Age
    "PAYTM": "Fintech", "POLICYBZR": "Fintech", "ANGELONE": "Fintech",
    "NAUKRI": "Internet", "DELHIVERY": "Logistics", "SWIGGY": "Internet",
    
    # Specialty Finance
    "HDFCAMC": "Asset Management", "MFSL": "Financial Services",
    "360ONE": "Asset Management", "JIOFIN": "Financial Services",
    
    # Misc
    "OFSS": "IT Services", "SOLARINDS": "Capital Goods",
    "ETERNAL": "Chemicals", "PGEL": "Electronics",
    "SAMMAANCAP": "Financial Services", "TATATECH": "IT Services",
}

def get_sector(symbol: str) -> str:
    """
    Get sector for a given stock symbol.
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
        
    Returns:
        Sector name or 'Others' if not found
    """
    # Remove .NS suffix if present
    clean_symbol = symbol.replace(".NS", "").upper()
    return SECTOR_MAP.get(clean_symbol, "Others")


def get_all_sectors() -> list:
    """Get list of all unique sectors."""
    return sorted(set(SECTOR_MAP.values()))


def get_stocks_by_sector(sector: str) -> list:
    """Get all stocks in a given sector."""
    return [symbol for symbol, sec in SECTOR_MAP.items() if sec == sector]
