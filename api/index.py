# Vercel serverless function entry point
import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# CRITICAL: Set serverless mode BEFORE importing app
os.environ['SERVERLESS'] = '1'
os.environ['VERCEL'] = '1'

# Disable all background operations
os.environ['DISABLE_THREADS'] = '1'
os.environ['DISABLE_SCANNER'] = '1'

# Import Flask first
from flask import Flask, jsonify, send_from_directory

# Try to import the main app, but with fallback
try:
    # This will import app.py but skip thread initialization
    import app as main_app
    application = main_app.app
    
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
    
    @application.route('/api/admin/stats')
    def stats():
        return jsonify({
            "date": "2026-05-16",
            "total_fo_stocks": 206,
            "mongo_connected": False,
            "scanner_running": False,
            "agent_open_trades": 0
        })
    
    @application.route('/api/stocks')
    def stocks():
        return jsonify([])
    
    @application.route('/<path:path>')
    def catch_all(path):
        return jsonify({"error": "Endpoint not available", "path": path})

# Expose for Vercel
app = application



