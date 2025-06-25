#!/bin/bash

# Quick test script to check if RaspiWiFi Flask app can start
# Run this on the Raspberry Pi to diagnose startup issues

echo "=== RaspiWiFi Flask App Test ==="

# Check if we're in the right directory
if [ ! -f "libs/configuration_app/app.py" ]; then
    echo "❌ Error: app.py not found. Make sure you're in the RaspiWiFi directory."
    exit 1
fi

echo "✅ Found app.py"

# Test Python syntax
echo "Testing Python syntax..."
python3 -m py_compile libs/configuration_app/app.py
if [ $? -eq 0 ]; then
    echo "✅ Python syntax is valid"
else
    echo "❌ Python syntax error found"
    exit 1
fi

# Test imports
echo "Testing imports..."
python3 -c "
import sys
sys.path.insert(0, 'libs/configuration_app')
try:
    from flask import Flask
    print('✅ Flask import OK')
except ImportError as e:
    print(f'❌ Flask import failed: {e}')
    sys.exit(1)

try:
    import subprocess
    print('✅ subprocess import OK')
except ImportError as e:
    print(f'❌ subprocess import failed: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Import test failed"
    exit 1
fi

# Test Flask app initialization
echo "Testing Flask app initialization..."
python3 -c "
import sys
import os
sys.path.insert(0, 'libs/configuration_app')
os.chdir('libs/configuration_app')
try:
    import app
    print('✅ App module loads successfully')
except Exception as e:
    print(f'❌ App module failed to load: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "✅ Flask app initialization successful"
else
    echo "❌ Flask app initialization failed"
    exit 1
fi

# Check if required directories exist
echo "Checking required directories..."
[ -d "/tmp/raspiwifi_status" ] && echo "✅ Status directory exists" || echo "❌ Status directory missing"
[ -d "/etc/raspiwifi" ] && echo "✅ Config directory exists" || echo "❌ Config directory missing"
[ -f "/etc/raspiwifi/raspiwifi.conf" ] && echo "✅ Config file exists" || echo "❌ Config file missing"

# Test network interface
echo "Checking network interface..."
if ip link show wlan0 >/dev/null 2>&1; then
    echo "✅ wlan0 interface exists"
    ip addr show wlan0 | grep "inet " || echo "ℹ️  wlan0 has no IP address (normal in client mode)"
else
    echo "❌ wlan0 interface not found"
fi

# Check if port 80 is available
echo "Checking if port 80 is available..."
if netstat -ln | grep -q ":80 "; then
    echo "❌ Port 80 is already in use:"
    netstat -ln | grep ":80 "
else
    echo "✅ Port 80 is available"
fi

echo
echo "=== Manual Test Instructions ==="
echo "To manually test the Flask app, run:"
echo "1. cd /path/to/RaspiWiFi/libs/configuration_app"
echo "2. sudo python3 app.py"
echo "3. Check if you see 'Running on http://0.0.0.0:80'"
echo "4. Test access: curl http://10.0.0.1 or open browser to http://10.0.0.1"
echo
echo "If the app still doesn't start, check:"
echo "- sudo journalctl -f (while running the app)"
echo "- python3 app.py (to see direct error messages)"
echo "- Check permissions on /etc/raspiwifi/ directory"
