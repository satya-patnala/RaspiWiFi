#!/bin/bash

# RaspiWiFi Deployment and Testing Script
# Run this on the Raspberry Pi after copying the updated code

echo "=== RaspiWiFi Deployment and Testing Script ==="
echo "Run this script on your Raspberry Pi after copying the updated code"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

# Create status directory
echo "Creating status directory..."
mkdir -p /tmp/raspiwifi_status
chmod 755 /tmp/raspiwifi_status

# Stop any existing services
echo "Stopping existing services..."
systemctl stop raspiwifi-configuration
systemctl stop hostapd
systemctl stop dnsmasq

# Kill any existing wpa_supplicant processes
echo "Cleaning up wpa_supplicant processes..."
pkill -f wpa_supplicant

# Check for the "registration to specific type not supported" error
echo "Checking for wpa_supplicant driver issues..."
if lsmod | grep -q brcmfmac; then
    echo "Broadcom WiFi detected - using nl80211 driver"
    WPA_DRIVER="nl80211"
elif lsmod | grep -q rtl; then
    echo "Realtek WiFi detected - using nl80211 driver"
    WPA_DRIVER="nl80211"
else
    echo "Unknown WiFi chipset - using default driver"
    WPA_DRIVER="nl80211"
fi

# Test WiFi interface
echo "Testing WiFi interface..."
if ! ip link show wlan0 > /dev/null 2>&1; then
    echo "ERROR: wlan0 interface not found!"
    echo "Available interfaces:"
    ip link show
    exit 1
fi

# Bring up WiFi interface
echo "Bringing up wlan0 interface..."
ip link set wlan0 up

# Test wpa_supplicant manually to check for driver issues
echo "Testing wpa_supplicant with current driver..."
timeout 10s wpa_supplicant -i wlan0 -D $WPA_DRIVER -c /dev/null -d 2>&1 | grep -E "(registration|not supported|driver|error)" || echo "No obvious driver errors"

# Check system services that might conflict
echo "Checking for conflicting services..."
if systemctl is-active --quiet NetworkManager; then
    echo "INFO: NetworkManager is running - RaspiWiFi now creates NetworkManager connections for compatibility"
else
    echo "INFO: NetworkManager is not running - RaspiWiFi will use wpa_supplicant primarily"
fi

if systemctl is-active --quiet systemd-networkd; then
    echo "WARNING: systemd-networkd is running - this may conflict with RaspiWiFi"
fi

# Check NetworkManager connections directory
echo "Checking NetworkManager connections directory..."
if [ -d "/etc/NetworkManager/system-connections" ]; then
    echo "✓ NetworkManager system-connections directory exists"
    echo "Current connections:"
    ls -la /etc/NetworkManager/system-connections/ 2>/dev/null || echo "No existing connections"
else
    echo "Creating NetworkManager system-connections directory..."
    mkdir -p /etc/NetworkManager/system-connections
    chmod 755 /etc/NetworkManager/system-connections
fi

# Install/update RaspiWiFi
echo "Installing/updating RaspiWiFi..."
if [ -f "initial_setup.py" ]; then
    python3 initial_setup.py
else
    echo "ERROR: initial_setup.py not found. Make sure you're in the RaspiWiFi directory."
    exit 1
fi

# Ensure services are unmasked and can be started
echo "Ensuring hostapd and dnsmasq are unmasked..."
systemctl unmask hostapd
systemctl unmask dnsmasq

# Start in AP mode for testing
echo "Starting RaspiWiFi in AP mode..."
systemctl start raspiwifi-configuration

# Wait a moment for services to start
sleep 5

# Check service status
echo "Checking service status..."
systemctl status raspiwifi-configuration --no-pager -l

# Check if AP is working
echo "Checking Access Point..."
if iwconfig wlan0 | grep -q "Mode:Master"; then
    echo "✓ AP mode is active"
else
    echo "✗ AP mode failed to start"
fi

# Check if web interface is accessible
echo "Checking web interface..."
if curl -s http://10.0.0.1:80 > /dev/null; then
    echo "✓ Web interface is accessible at http://10.0.0.1"
else
    echo "✗ Web interface is not accessible"
fi

# Check for recent errors
echo "Recent system errors related to WiFi:"
journalctl -u wpa_supplicant -u hostapd -u dnsmasq -u raspiwifi-configuration --since "5 minutes ago" --no-pager | grep -E "(error|failed|not supported)" || echo "No recent errors found"

echo
echo "=== Troubleshooting Information ==="
echo "1. Connect to WiFi network 'RaspiWiFi Setup'"
echo "2. Open browser to http://10.0.0.1"
echo "3. Check status at http://10.0.0.1/status"
echo "4. Check connection info at http://10.0.0.1/connection_status"
echo "5. View debug info at http://10.0.0.1/debug_wifi"
echo
echo "=== Service Management ==="
echo "If services are not starting/enabling properly:"
echo "1. Run the diagnostic script: sudo ./raspiwifi_service_fix.sh"
echo "2. This will check and fix service states automatically"
echo "3. Check individual service status: systemctl status [service]"
echo "4. View service logs: journalctl -u [service] -n 20"
echo
echo "=== Network Configuration Details ==="
echo "RaspiWiFi now creates BOTH wpa_supplicant and NetworkManager connections:"
echo "- wpa_supplicant.conf: /etc/wpa_supplicant/wpa_supplicant.conf"
echo "- NetworkManager: /etc/NetworkManager/system-connections/*.nmconnection"
echo "This dual approach improves compatibility and provides fallback options."
echo
echo "If you see 'registration to specific type not supported':"
echo "- This usually indicates wpa_supplicant driver issues"
echo "- RaspiWiFi will automatically try NetworkManager as fallback"
echo "- Check that the correct WiFi driver is loaded (nl80211 vs wext)"
echo "- Ensure no conflicting network managers are running simultaneously"
echo
echo "Connection methods (in order of preference):"
echo "1. wpa_supplicant with nl80211 driver"
echo "2. wpa_supplicant with wext driver (fallback)"
echo "3. NetworkManager connection (fallback)"
echo "4. Legacy wpa_supplicant service (last resort)"
echo
echo "Status files are created in /tmp/raspiwifi_status/"
echo "Check these files for detailed operation logs"
