#!/bin/bash

# RaspiWiFi Service Diagnostic and Fix Script
# Run this script to diagnose and fix service management issues

echo "=== RaspiWiFi Service Diagnostic Script ==="
echo "Checking and fixing service states..."
echo

# Function to check and fix a service
check_and_fix_service() {
    local service=$1
    local should_be_enabled=$2
    local should_be_running=$3
    
    echo "--- Checking $service ---"
    
    # Check if service is masked
    if systemctl is-enabled $service 2>&1 | grep -q "masked"; then
        echo "❌ $service is MASKED - fixing..."
        systemctl unmask $service
        sleep 1
        if systemctl is-enabled $service 2>&1 | grep -q "masked"; then
            echo "❌ Failed to unmask $service"
            return 1
        else
            echo "✅ Successfully unmasked $service"
        fi
    else
        echo "✅ $service is not masked"
    fi
    
    # Check if service should be enabled
    if [ "$should_be_enabled" = "true" ]; then
        if systemctl is-enabled $service 2>/dev/null | grep -q "enabled"; then
            echo "✅ $service is enabled"
        else
            echo "❌ $service is not enabled - fixing..."
            systemctl enable $service
            sleep 1
            if systemctl is-enabled $service 2>/dev/null | grep -q "enabled"; then
                echo "✅ Successfully enabled $service"
            else
                echo "❌ Failed to enable $service"
                return 1
            fi
        fi
    fi
    
    # Check if service should be running
    if [ "$should_be_running" = "true" ]; then
        if systemctl is-active $service 2>/dev/null | grep -q "active"; then
            echo "✅ $service is running"
        else
            echo "❌ $service is not running - starting..."
            systemctl start $service
            sleep 3
            if systemctl is-active $service 2>/dev/null | grep -q "active"; then
                echo "✅ Successfully started $service"
            else
                echo "❌ Failed to start $service"
                echo "Service status:"
                systemctl status $service --no-pager -l
                return 1
            fi
        fi
    fi
    
    echo "✅ $service is properly configured"
    echo
    return 0
}

# Check if we're running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Determine what mode we should be in
if [ -f "/etc/raspiwifi/host_mode" ]; then
    echo "📡 RaspiWiFi is in AP/HOST mode"
    AP_MODE=true
else
    echo "📶 RaspiWiFi is in CLIENT mode"
    AP_MODE=false
fi

echo

# Check and fix services based on mode
if [ "$AP_MODE" = "true" ]; then
    echo "=== AP Mode Service Check ==="
    check_and_fix_service "hostapd" "true" "true"
    check_and_fix_service "dnsmasq" "true" "true"
    check_and_fix_service "dhcpcd" "true" "true"
    check_and_fix_service "NetworkManager" "false" "false"
    check_and_fix_service "wpa_supplicant" "false" "false"
else
    echo "=== Client Mode Service Check ==="
    check_and_fix_service "hostapd" "false" "false"
    check_and_fix_service "dnsmasq" "false" "false"
    check_and_fix_service "dhcpcd" "true" "true"
    check_and_fix_service "NetworkManager" "true" "true"
    check_and_fix_service "wpa_supplicant" "true" "true"
fi

echo "=== Network Interface Check ==="
echo "wlan0 status:"
ip addr show wlan0 2>/dev/null || echo "❌ wlan0 interface not found"

if [ "$AP_MODE" = "true" ]; then
    echo
    echo "Checking AP mode IP configuration..."
    if ip addr show wlan0 | grep -q "10.0.0.1"; then
        echo "✅ wlan0 has correct AP IP (10.0.0.1)"
    else
        echo "❌ wlan0 does not have AP IP - fixing..."
        ip addr flush dev wlan0 2>/dev/null
        ip addr add 10.0.0.1/24 dev wlan0 2>/dev/null
        ip link set wlan0 up 2>/dev/null
        if ip addr show wlan0 | grep -q "10.0.0.1"; then
            echo "✅ Successfully set AP IP"
        else
            echo "❌ Failed to set AP IP"
        fi
    fi
fi

echo
echo "=== Process Check ==="
echo "Active network-related processes:"
pgrep -f hostapd && echo "✅ hostapd process running" || echo "❌ hostapd process not running"
pgrep -f dnsmasq && echo "✅ dnsmasq process running" || echo "❌ dnsmasq process not running"
pgrep -f wpa_supplicant && echo "✅ wpa_supplicant process running" || echo "❌ wpa_supplicant process not running"
pgrep -f NetworkManager && echo "✅ NetworkManager process running" || echo "❌ NetworkManager process not running"

echo
echo "=== Configuration Files Check ==="
[ -f "/etc/hostapd/hostapd.conf" ] && echo "✅ hostapd.conf exists" || echo "❌ hostapd.conf missing"
[ -f "/etc/dnsmasq.conf" ] && echo "✅ dnsmasq.conf exists" || echo "❌ dnsmasq.conf missing"
[ -f "/etc/wpa_supplicant/wpa_supplicant.conf" ] && echo "✅ wpa_supplicant.conf exists" || echo "❌ wpa_supplicant.conf missing"
[ -f "/etc/dhcpcd.conf" ] && echo "✅ dhcpcd.conf exists" || echo "❌ dhcpcd.conf missing"

echo
echo "=== Service Status Summary ==="
systemctl status hostapd --no-pager -l | head -3
systemctl status dnsmasq --no-pager -l | head -3  
systemctl status NetworkManager --no-pager -l | head -3
systemctl status wpa_supplicant --no-pager -l | head -3

echo
echo "=== Diagnostic Complete ==="
echo "If services are still not working, check:"
echo "1. Configuration files for syntax errors"
echo "2. Hardware WiFi adapter compatibility" 
echo "3. Kernel modules (lsmod | grep brcm)"
echo "4. Journal logs: journalctl -u [service-name] -n 20"
