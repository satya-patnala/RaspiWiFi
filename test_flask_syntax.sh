#!/bin/bash

# Test Flask app startup
cd /Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/configuration_app

echo "Testing Flask app syntax and startup..."
python3 -m py_compile app.py

if [ $? -eq 0 ]; then
    echo "✓ Flask app syntax is valid"
else
    echo "✗ Flask app has syntax errors"
    exit 1
fi

# Try to import the app module
python3 -c "
import sys
sys.path.append('.')
try:
    import app
    print('✓ Flask app can be imported successfully')
except Exception as e:
    print(f'✗ Flask app import failed: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "Flask app is ready to run"
else
    echo "Flask app has import issues"
    exit 1
fi
