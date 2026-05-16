# Vercel serverless function entry point
import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app
from app import app

# Vercel expects a variable named 'app' or a function named 'handler'
# The app variable is already defined in app.py, so we just need to expose it
