from flask import Flask, render_template
import os

app = Flask(__name__)
app.debug = True

@app.route('/')
def index():
    return "<h1>RaspiWiFi Test - Flask is working!</h1><p>If you see this, the Flask app can start successfully.</p>"

@app.route('/test')
def test():
    return f"<h2>System Test</h2><p>Current user: {os.getenv('USER', 'unknown')}</p><p>Current directory: {os.getcwd()}</p>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
