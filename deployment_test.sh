#!/bin/bash

echo "=== RaspiWiFi Flask App Deployment Test ==="

# Test 1: Syntax check
echo "1. Testing Flask app syntax..."
cd /Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/configuration_app
python3 -m py_compile app.py
if [ $? -eq 0 ]; then
    echo "✓ Flask app syntax is valid"
else
    echo "✗ Flask app has syntax errors"
    exit 1
fi

# Test 2: Check all required templates exist
echo "2. Checking required templates..."
TEMPLATES_DIR="/Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/configuration_app/templates"
REQUIRED_TEMPLATES=("app.html" "layout.html" "manual_ssid_entry.html" "save_credentials.html" "save_wpa_credentials.html" "status.html" "wpa_settings.html")

for template in "${REQUIRED_TEMPLATES[@]}"; do
    if [ -f "$TEMPLATES_DIR/$template" ]; then
        echo "✓ Template $template exists"
    else
        echo "✗ Template $template missing"
        exit 1
    fi
done

# Test 3: Check static files
echo "3. Checking static files..."
STATIC_DIR="/Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/configuration_app/static"
if [ -d "$STATIC_DIR" ]; then
    echo "✓ Static directory exists"
else
    echo "⚠ Static directory missing (may be optional)"
fi

# Test 4: Check bootstrap files
echo "4. Checking bootstrap files..."
BOOTSTRAP_FILE="/Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/reset_device/static_files/aphost_bootstrapper"
if [ -f "$BOOTSTRAP_FILE" ]; then
    echo "✓ AP host bootstrapper exists"
else
    echo "✗ AP host bootstrapper missing"
    exit 1
fi

# Test 5: Check permissions on key directories
echo "5. Summary of key files:"
echo "Flask app: $(ls -la /Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/configuration_app/app.py | awk '{print $1, $3, $4}')"
echo "Bootstrap: $(ls -la /Users/satya.patnala@grofers.com/blinkit/RaspiWiFi/libs/reset_device/static_files/aphost_bootstrapper | awk '{print $1, $3, $4}')"

echo ""
echo "=== Deployment Test Complete ==="
echo "✓ Flask app should be ready for deployment"
echo ""
echo "To deploy on Raspberry Pi:"
echo "1. Run initial_setup.py as root"
echo "2. Reboot to enable AP mode"
echo "3. Access web interface at http://10.0.0.1"
