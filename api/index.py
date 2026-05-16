# Vercel serverless function entry point
import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Disable threading and background tasks for serverless
os.environ['SERVERLESS'] = '1'

# Import the Flask app
from app import app

# Vercel looks for 'app' or 'application' variable
application = app


