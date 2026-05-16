"""
Minimal Flask app for Vercel testing
This bypasses the complex main app to verify deployment works
"""
from flask import Flask, jsonify, send_from_directory
import os

app = Flask(__name__, static_folder='..', static_url_path='')

@app.route('/')
def home():
    """Serve the main HTML file"""
    try:
        return send_from_directory('..', 'index.html')
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Dashboard file not found",
            "error": str(e)
        })

@app.route('/api/test')
def test():
    """Test endpoint"""
    return jsonify({
        "status": "ok",
        "message": "Vercel deployment successful!",
        "note": "This is a minimal version. Full app requires Railway.app"
    })

@app.route('/api/admin/stats')
def stats():
    """Basic stats endpoint"""
    return jsonify({
        "status": "limited",
        "message": "Running in minimal mode on Vercel",
        "total_fo_stocks": 206,
        "mongo_connected": False,
        "scanner_running": False,
        "note": "Deploy to Railway.app for full features"
    })

@app.route('/<path:path>')
def catch_all(path):
    """Catch all other routes"""
    return jsonify({
        "error": "Endpoint not available in minimal mode",
        "path": path,
        "message": "Deploy to Railway.app for full functionality"
    })

# WSGI entry point
application = app
