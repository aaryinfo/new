from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "ok",
        "message": "Vercel deployment test successful",
        "version": "1.0"
    })

@app.route('/api/test')
def test():
    return jsonify({"test": "working"})

# For Vercel
if __name__ != '__main__':
    # Production mode (Vercel)
    pass
