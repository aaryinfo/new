# Vercel serverless function entry point
import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# CRITICAL: Set serverless mode BEFORE importing app
os.environ['SERVERLESS'] = '1'
os.environ['VERCEL'] = '1'
os.environ['DISABLE_THREADS'] = '1'
os.environ['DISABLE_SCANNER'] = '1'

# Import Flask first
from flask import Flask, jsonify, send_from_directory

# Try to import the main app, but with fallback
try:
    # This will import app.py but skip thread initialization
    import app as main_app
    application = main_app.app
    
    # Add a quick-scan endpoint for Vercel
    @application.route('/api/quick-scan')
    def vercel_quick_scan():
        """Quick scan of top 20 stocks for Vercel"""
        try:
            from vercel_quick_scan import quick_scan_for_vercel
            stocks = quick_scan_for_vercel()
            
            # Update the main app's data store
            main_app._last_scan["data"] = stocks
            main_app._last_scan["time"] = "Just now"
            
            return jsonify({
                "status": "success",
                "stocks": stocks,
                "count": len(stocks),
                "message": "Quick scan complete (top 20 stocks)"
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
except Exception as e:
    # If main app fails, create a working fallback
    print(f"[VERCEL] Main app import failed: {e}")
    print("[VERCEL] Using fallback app")
    
    application = Flask(__name__, static_folder='..', static_url_path='')
    
    @application.route('/')
    def home():
        try:
            return send_from_directory('..', 'index.html')
        except:
            return jsonify({
                "status": "ok",
                "message": "NSE F&O Scanner - Vercel Deployment",
                "note": "Dashboard loading..."
            })
    
    @application.route('/api/quick-scan')
    def quick_scan():
        """Quick scan endpoint"""
        try:
            from vercel_quick_scan import quick_scan_for_vercel
            stocks = quick_scan_for_vercel()
            return jsonify({
                "status": "success",
                "stocks": stocks,
                "count": len(stocks)
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @application.route('/api/stocks')
    def stocks():
        """Return empty stocks - user should call /api/quick-scan first"""
        return jsonify({
            "stocks": [],
            "total": 0,
            "message": "Call /api/quick-scan to load data"
        })
    
    @application.route('/api/admin/stats')
    def stats():
        return jsonify({
            "date": "2026-05-16",
            "total_fo_stocks": 206,
            "mongo_connected": False,
            "scanner_running": False,
            "agent_open_trades": 0
        })
    
    @application.route('/<path:path>')
    def catch_all(path):
        return jsonify({"error": "Endpoint not available", "path": path})

# Expose for Vercel
app = application
