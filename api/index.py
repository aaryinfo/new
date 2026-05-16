# Vercel serverless function entry point
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Disable threading and background tasks for serverless
os.environ['SERVERLESS'] = '1'

try:
    # Import the Flask app
    from app import app
    
    # Vercel handler
    def handler(request, context):
        return app(request.environ, context)
        
except Exception as e:
    # Fallback minimal app if main app fails
    from flask import Flask, jsonify
    
    app = Flask(__name__)
    
    @app.route('/')
    def home():
        return jsonify({
            "error": "App initialization failed",
            "message": str(e),
            "note": "This app requires a traditional server environment (not serverless)"
        })
    
    @app.route('/<path:path>')
    def catch_all(path):
        return jsonify({
            "error": "App initialization failed", 
            "message": str(e),
            "path": path
        })

