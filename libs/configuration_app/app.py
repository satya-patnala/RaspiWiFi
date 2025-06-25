from flask import Flask, render_template, request, jsonify
import os
import time
import subprocess
from threading import Thread
import fileinput
import json

app = Flask(__name__)
app.debug = True

@app.route('/')
def index():
    wifi_ap_array = scan_wifi_networks()
    config_hash = config_file_hash()
    
    return render_template('app.html', 
                         wifi_ap_array=wifi_ap_array, 
                         config_hash=config_hash)

@app.route('/manual_ssid_entry')
def manual_ssid_entry():
    return render_template('manual_ssid_entry.html')

@app.route('/wpa_settings')
def wpa_settings():
    config_hash = config_file_hash()
    return render_template('wpa_settings.html', wpa_enabled = config_hash['wpa_enabled'], wpa_key = config_hash['wpa_key'])


@app.route('/save_credentials', methods = ['GET', 'POST'])
def save_credentials():
    ssid = request.form['ssid']
    wifi_key = request.form['wifi_key']
    
    # Store credentials globally for transition function
    current_wifi_credentials['ssid'] = ssid
    current_wifi_credentials['key'] = wifi_key
    
    # Log SSID for debugging (helpful for special character issues)
    print(f"Connecting to SSID: '{ssid}' (length: {len(ssid)})")
    print(f"SSID bytes: {ssid.encode('utf-8')}")

    # Create wpa_supplicant.conf
    create_wpa_supplicant(ssid, wifi_key)
    
    # Create NetworkManager connection
    create_networkmanager_connection(ssid, wifi_key)
    
    # Call transition to client mode in a thread
    def sleep_and_transition():
        time.sleep(3)
        transition_to_client_mode_with_status(ssid)
    t = Thread(target=sleep_and_transition)
    t.start()

    return render_template('save_credentials.html', ssid = ssid)


@app.route('/save_wpa_credentials', methods = ['GET', 'POST'])
def save_wpa_credentials():
    config_hash = config_file_hash()
    wpa_enabled = request.form.get('wpa_enabled')
    wpa_key = request.form['wpa_key']

    if str(wpa_enabled) == '1':
        update_wpa(1, wpa_key)
    else:
        update_wpa(0, wpa_key)

    def sleep_and_restart_services():
        time.sleep(2)
        # Restart hostapd service to apply WPA changes
        os.system('systemctl unmask hostapd')
        os.system('systemctl unmask dnsmasq')
        os.system('systemctl restart hostapd')
        os.system('systemctl restart dnsmasq')

    t = Thread(target=sleep_and_restart_services)
    t.start()

    config_hash = config_file_hash()
    return render_template('save_wpa_credentials.html', wpa_enabled = config_hash['wpa_enabled'], wpa_key = config_hash['wpa_key'])




######## FUNCTIONS ##########

def scan_wifi_networks():
    iwlist_raw = subprocess.Popen(['iwlist', 'scan'], stdout=subprocess.PIPE)
    ap_list, err = iwlist_raw.communicate()
    ap_array = []

    for line in ap_list.decode('utf-8').rsplit('\n'):
        if 'ESSID' in line:
            ap_ssid = line[27:-1]
            if ap_ssid != '':
                ap_array.append(ap_ssid)

    return ap_array

def create_wpa_supplicant(ssid, wifi_key):
    # Use /tmp directory for temporary file to ensure write permissions
    temp_file_path = '/tmp/wpa_supplicant.conf.tmp'
    
    try:
        # Stop NetworkManager temporarily to prevent interference during configuration
        os.system('systemctl stop NetworkManager 2>/dev/null')
        
        # Create the temporary file
        temp_conf_file = open(temp_file_path, 'w')

        # Write wpa_supplicant configuration with proper driver settings
        temp_conf_file.write('ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n')
        temp_conf_file.write('update_config=1\n')
        temp_conf_file.write('country=US\n')
        temp_conf_file.write('ap_scan=1\n')  # Enable AP scanning
        temp_conf_file.write('\n')
        temp_conf_file.write('network={\n')
        temp_conf_file.write('    ssid="' + ssid + '"\n')

        if wifi_key == '':
            temp_conf_file.write('    key_mgmt=NONE\n')
        else:
            # Use plain text password for better compatibility and simplicity
            temp_conf_file.write('    psk="' + wifi_key + '"\n')
            temp_conf_file.write('    key_mgmt=WPA-PSK\n')
            temp_conf_file.write('    proto=RSN WPA\n')  # Support both WPA and WPA2
            temp_conf_file.write('    pairwise=CCMP TKIP\n')  # Support both encryption types
            temp_conf_file.write('    group=CCMP TKIP\n')
            temp_conf_file.write('    scan_ssid=1\n')  # Allow hidden networks

        temp_conf_file.write('    priority=1\n')  # Give this network highest priority
        temp_conf_file.write('    }\n')

        # Ensure data is written to disk
        temp_conf_file.flush()
        os.fsync(temp_conf_file.fileno())
        temp_conf_file.close()

        # Verify temp file was created successfully
        if not os.path.exists(temp_file_path):
            raise Exception("Temporary file was not created")

        # Stop wpa_supplicant completely before replacing config
        os.system('systemctl stop wpa_supplicant')
        os.system('killall wpa_supplicant 2>/dev/null')

        # Move the file and set proper permissions
        move_result = os.system('mv ' + temp_file_path + ' /etc/wpa_supplicant/wpa_supplicant.conf')
        if move_result != 0:
            raise Exception("Failed to move wpa_supplicant.conf to /etc/wpa_supplicant/")
            
        # Verify the final file was created
        if not os.path.exists('/etc/wpa_supplicant/wpa_supplicant.conf'):
            raise Exception("wpa_supplicant.conf was not created in /etc/wpa_supplicant/")

        # Set proper permissions (readable/writable by root only)
        os.system('chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf')
        
        # Unmask and enable wpa_supplicant service
        os.system('systemctl unmask wpa_supplicant')
        os.system('systemctl enable wpa_supplicant')
        
        # Force filesystem sync to ensure all writes are completed
        os.system('sync')
        
        # Validate the file contents to ensure it's properly formatted
        try:
            with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'r') as f:
                content = f.read()
                if 'network={' not in content or ssid not in content:
                    raise Exception("wpa_supplicant.conf content validation failed")
                print(f"wpa_supplicant.conf created successfully for SSID: {ssid}")
        except Exception as e:
            raise Exception("Cannot read or validate wpa_supplicant.conf: " + str(e))
        
        return True
            
    except Exception as e:
        # Clean up temporary file if it exists
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        # Re-raise the exception so caller knows it failed
        raise e

def set_ap_client_mode():
    os.system('rm -f /etc/raspiwifi/host_mode')
    os.system('rm /etc/cron.raspiwifi/aphost_bootstrapper')
    os.system('cp /usr/lib/raspiwifi/reset_device/static_files/apclient_bootstrapper /etc/cron.raspiwifi/')
    os.system('chmod +x /etc/cron.raspiwifi/apclient_bootstrapper')
    os.system('mv /etc/dnsmasq.conf.original /etc/dnsmasq.conf')
    os.system('mv /etc/dhcpcd.conf.original /etc/dhcpcd.conf')
    
    # Stop AP mode services
    os.system('systemctl stop hostapd')
    os.system('systemctl stop dnsmasq')
    os.system('systemctl disable hostapd')
    os.system('systemctl disable dnsmasq')
    
    # Restart network services for client mode
    os.system('systemctl restart dhcpcd')
    
    # Restart network interface to apply new configuration
    restart_network_interface()
    
    # Start and enable wpa_supplicant for WiFi client mode
    os.system('systemctl start wpa_supplicant')
    os.system('systemctl enable wpa_supplicant')
    
    # Wait for connection to establish
    time.sleep(5)
    
    # Try to connect to the WiFi network
    os.system('wpa_cli -i wlan0 reconfigure')
    os.system('dhclient wlan0')
    
    # Optionally enable NetworkManager for GUI compatibility
    # This allows the WiFi icon in the desktop to work properly
    os.system('systemctl enable NetworkManager')
    os.system('systemctl start NetworkManager')

def update_wpa(wpa_enabled, wpa_key):
    with fileinput.FileInput('/etc/raspiwifi/raspiwifi.conf', inplace=True) as raspiwifi_conf:
        for line in raspiwifi_conf:
            if 'wpa_enabled=' in line:
                line_array = line.split('=')
                line_array[1] = wpa_enabled
                print(line_array[0] + '=' + str(line_array[1]))

            if 'wpa_key=' in line:
                line_array = line.split('=')
                line_array[1] = wpa_key
                print(line_array[0] + '=' + line_array[1])

            if 'wpa_enabled=' not in line and 'wpa_key=' not in line:
                print(line, end='')


def config_file_hash():
    config_file = open('/etc/raspiwifi/raspiwifi.conf')
    config_hash = {}

    for line in config_file:
        line_key = line.split("=")[0]
        line_value = line.split("=")[1].rstrip()
        config_hash[line_key] = line_value

    return config_hash

def restart_network_interface():
    """Restart wlan0 interface to apply new network configuration"""
    os.system('ip link set wlan0 down')
    time.sleep(1)
    os.system('ip link set wlan0 up')
    time.sleep(2)
    
    # Restart networking to ensure configuration is applied
    os.system('systemctl restart networking')

def ensure_ap_mode_ip():
    """Ensure wlan0 has static IP 10.0.0.1 when in AP mode"""
    # Check if we're in host mode (AP mode)
    if os.path.exists('/etc/raspiwifi/host_mode'):
        # Stop NetworkManager if it's running to avoid conflicts
        os.system('systemctl stop NetworkManager 2>/dev/null')
        
        # Bring interface down and up to reset it
        os.system('ip link set wlan0 down 2>/dev/null')
        os.system('sleep 1')
        os.system('ip link set wlan0 up')
        os.system('sleep 1')
        
        # Set static IP immediately for AP mode
        os.system('ifconfig wlan0 10.0.0.1 netmask 255.255.255.0 up')
        
        # Verify it worked
        result = os.system('ifconfig wlan0 | grep "inet 10.0.0.1" > /dev/null 2>&1')
        if result != 0:
            # Try alternative method if first attempt failed
            os.system('ip addr add 10.0.0.1/24 dev wlan0 2>/dev/null')
            os.system('ip link set wlan0 up')
        
        # Ensure dhcpcd is managing the interface properly
        os.system('systemctl restart dhcpcd 2>/dev/null')

def transition_to_client_mode_with_status(ssid):
    """Transition to client mode"""
    
    # Stop AP mode services
    os.system('systemctl stop hostapd')
    os.system('systemctl stop dnsmasq') 
    os.system('systemctl disable hostapd')
    os.system('systemctl disable dnsmasq')
    
    # Reset network interface
    os.system('ip addr flush dev wlan0')
    os.system('ip link set wlan0 down')
    os.system('ip link set wlan0 up')
    
    # Stop any existing wpa_supplicant processes
    os.system('killall wpa_supplicant 2>/dev/null')
    os.system('systemctl stop wpa_supplicant 2>/dev/null')
    
    # Configure dhcpcd for client mode
    log_status("Configuring dhcpcd for client mode...")
    os.system('cp /etc/dhcpcd.conf.original /etc/dhcpcd.conf 2>/dev/null || echo "# dhcpcd config for client mode" > /etc/dhcpcd.conf')
    os.system('systemctl restart dhcpcd')
    
    # Start NetworkManager first and let it handle the connection
    log_status("Starting NetworkManager to handle WiFi connection...")
    os.system('systemctl unmask NetworkManager')
    os.system('systemctl enable NetworkManager') 
    os.system('systemctl restart NetworkManager')
    
    # Wait for NetworkManager to start
    time.sleep(5)
    
    nm_running = os.system('systemctl is-active NetworkManager > /dev/null') == 0
    log_status(f"NetworkManager status: {'running' if nm_running else 'failed'}")
    
    if nm_running:
        # Try NetworkManager connection first
        update_connection_status({
            'state': 'connecting',
            'ssid': ssid,
            'message': 'Attempting WiFi connection via NetworkManager...'
        })
        
        log_status(f"Attempting NetworkManager connection to '{ssid}'...")
        log_status(f"SSID contains: spaces={' ' in ssid}, apostrophe={chr(39) in ssid}")
        
        # Get WiFi key from stored credentials
        wifi_key = current_wifi_credentials.get('key', '')
        
        # Use subprocess for better shell escaping instead of os.system
        try:
            # Try with password if available
            if wifi_key and wifi_key.strip():
                cmd = ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', wifi_key]
                log_status("Connecting with password...")
            else:
                cmd = ['nmcli', 'device', 'wifi', 'connect', ssid]
                log_status("Connecting without password (open network)...")
                
            log_status(f"Running command: {' '.join(['nmcli', 'device', 'wifi', 'connect', repr(ssid), '...'])}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            nm_result = result.returncode
            
            if nm_result != 0:
                log_status(f"NetworkManager error: {result.stderr.strip()}")
                log_status(f"NetworkManager stdout: {result.stdout.strip()}")
            else:
                log_status("NetworkManager command completed successfully")
                
        except subprocess.TimeoutExpired:
            log_status("NetworkManager connection timed out")
            nm_result = 1
        except Exception as e:
            log_status(f"NetworkManager connection error: {str(e)}")
            nm_result = 1
            
        if nm_result == 0:
            log_status("NetworkManager connection successful!")
            time.sleep(3)
            # Check if we got IP
            ip_result = os.system('ip addr show wlan0 | grep "inet " | grep -v "127.0.0.1" > /dev/null')
            if ip_result == 0:
                log_status("IP address obtained via NetworkManager!")
                update_connection_status({
                    'state': 'connected',
                    'ssid': ssid,
                    'message': 'Connected via NetworkManager'
                })
                final_check()
                return
        else:
            # Try fallback method with connection profile
            log_status("Direct connection failed, trying connection profile method...")
            try:
                result = subprocess.run(['nmcli', 'connection', 'up', ssid], 
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    log_status("Connection profile method successful!")
                    time.sleep(3)
                    ip_result = os.system('ip addr show wlan0 | grep "inet " | grep -v "127.0.0.1" > /dev/null')
                    if ip_result == 0:
                        log_status("IP address obtained via connection profile!")
                        update_connection_status({
                            'state': 'connected',
                            'ssid': ssid,
                            'message': 'Connected via NetworkManager profile'
                        })
                        final_check()
                        return
                else:
                    log_status(f"Connection profile error: {result.stderr.strip()}")
            except Exception as e:
                log_status(f"Connection profile method error: {str(e)}")
    
    # If NetworkManager failed completely, try wpa_supplicant as fallback
    log_status("NetworkManager connection failed, trying wpa_supplicant fallback...")
    
    # Stop NetworkManager to avoid conflicts
    os.system('systemctl stop NetworkManager')
    
    # Start wpa_supplicant manually with specific config
    log_status("Starting wpa_supplicant manually...")
    wpa_cmd = 'wpa_supplicant -B -i wlan0 -D nl80211,wext -c /etc/wpa_supplicant/wpa_supplicant.conf'
    wpa_result = os.system(wpa_cmd)
    
    if wpa_result == 0:
        time.sleep(3)
        wpa_running = os.system('pgrep wpa_supplicant > /dev/null') == 0
        
        if wpa_running:
            log_status("wpa_supplicant started successfully, triggering connection...")
            os.system('wpa_cli -i wlan0 reconfigure')
            os.system('wpa_cli -i wlan0 reassociate')
            
            update_connection_status({
                'state': 'connecting',
                'ssid': ssid,
                'message': 'Attempting WiFi connection via wpa_supplicant...'
            })
            
            # Wait for connection and check for IP
            max_attempts = 8
            connected = False
            
            for attempt in range(max_attempts):
                time.sleep(3)
                
                # Check if we have an IP address
                ip_result = os.system('ip addr show wlan0 | grep "inet " | grep -v "127.0.0.1" > /dev/null')
                if ip_result == 0:
                    log_status("Connection successful - IP address obtained!")
                    connected = True
                    break
                
                # Check wpa_supplicant status
                wpa_status = os.system('wpa_cli -i wlan0 status | grep "wpa_state=COMPLETED" > /dev/null')
                if wpa_status == 0:
                    log_status("wpa_supplicant connected, requesting IP...")
                    os.system('dhclient wlan0 2>/dev/null')
                    time.sleep(2)
                    continue
                
                log_status(f"Connection attempt {attempt + 1}/{max_attempts}...")
                os.system('wpa_cli -i wlan0 reassociate')
            
            if connected:
                update_connection_status({
                    'state': 'connected',
                    'ssid': ssid,
                    'message': 'Connected via wpa_supplicant'
                })
            else:
                log_status("wpa_supplicant connection failed", is_error=True)
                update_connection_status({
                    'state': 'connection_failed',
                    'ssid': ssid,
                    'message': f'Failed to connect to WiFi network {ssid}'
                })
        else:
            log_status("Failed to start wpa_supplicant", is_error=True)
    else:
        log_status("wpa_supplicant command failed", is_error=True)
    
    # Final status check
    final_check()

def final_check():
    """Perform final connectivity check and update status"""
    log_status("Performing final connectivity check...")
    
    # Check if we have an IP address
    ip_result = os.system('ip addr show wlan0 | grep "inet " | grep -v "127.0.0.1" > /dev/null')
    if ip_result == 0:
        # Check internet connectivity
        ping_result = os.system('ping -c 1 -W 5 8.8.8.8 > /dev/null 2>&1')
        if ping_result == 0:
            log_status("Final check: Full internet connectivity confirmed")
        else:
            log_status("Final check: Local network connected but no internet")
    else:
        log_status("Final check: No IP address assigned", is_error=True)

def debug_wifi_configs():
    """Debug function to check all WiFi configuration sources"""
    debug_info = []
    
    # Check wpa_supplicant.conf
    try:
        with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'r') as f:
            content = f.read()
            debug_info.append(f"wpa_supplicant.conf content:\n{content}")
    except:
        debug_info.append("wpa_supplicant.conf not found or not readable")
    
    # Check NetworkManager connections
    import glob
    nm_connections = glob.glob('/etc/NetworkManager/system-connections/*')
    if nm_connections:
        debug_info.append(f"NetworkManager connections found: {nm_connections}")
        for conn in nm_connections:
            try:
                with open(conn, 'r') as f:
                    debug_info.append(f"Connection {conn}:\n{f.read()}")
            except:
                debug_info.append(f"Could not read {conn}")
    else:
        debug_info.append("No NetworkManager connections found")
    
    # Check current WiFi connection
    try:
        result = subprocess.run(['iwconfig', 'wlan0'], capture_output=True, text=True)
        debug_info.append(f"Current wlan0 status:\n{result.stdout}")
    except:
        debug_info.append("Could not get iwconfig status")
    
    # Check dhcpcd.conf
    try:
        with open('/etc/dhcpcd.conf', 'r') as f:
            content = f.read()
            debug_info.append(f"dhcpcd.conf content:\n{content}")
    except:
        debug_info.append("dhcpcd.conf not found or not readable")
    
    return debug_info

@app.route('/debug_wifi')
def debug_wifi():
    """Debug route to show all WiFi configurations"""
    if app.debug:  # Only available in debug mode
        debug_info = debug_wifi_configs()
        debug_html = "<h1>WiFi Debug Information</h1>"
        for info in debug_info:
            debug_html += f"<pre>{info}</pre><hr>"
        return debug_html
    else:
        return "Debug mode not enabled", 403

@app.route('/connection_status')
def connection_status():
    """Check the current WiFi connection status"""
    if app.debug:
        status_info = []
        
        # Check wpa_supplicant status
        try:
            result = subprocess.run(['wpa_cli', '-i', 'wlan0', 'status'], capture_output=True, text=True)
            status_info.append(f"WPA Supplicant Status:\n{result.stdout}")
        except:
            status_info.append("Could not get wpa_supplicant status")
        
        # Check network interface status
        try:
            result = subprocess.run(['ifconfig', 'wlan0'], capture_output=True, text=True)
            status_info.append(f"wlan0 Interface Status:\n{result.stdout}")
        except:
            status_info.append("Could not get wlan0 interface status")
        
        # Check routing table
        try:
            result = subprocess.run(['route', '-n'], capture_output=True, text=True)
            status_info.append(f"Routing Table:\n{result.stdout}")
        except:
            status_info.append("Could not get routing table")
        
        # Check if we can ping gateway
        try:
            result = subprocess.run(['ping', '-c', '1', '8.8.8.8'], capture_output=True, text=True)
            if result.returncode == 0:
                status_info.append("Internet connectivity: SUCCESS")
            else:
                status_info.append("Internet connectivity: FAILED")
        except:
            status_info.append("Could not test internet connectivity")
        
        status_html = "<h1>WiFi Connection Status</h1>"
        for info in status_info:
            status_html += f"<pre>{info}</pre><hr>"
        return status_html
    else:
        return "Debug mode not enabled", 403

def create_networkmanager_connection(ssid, wifi_key):
    """
    Create a NetworkManager connection profile for the WiFi network.
    This provides redundancy and compatibility with NetworkManager-based systems.
    """
    import uuid
    import secrets
    
    try:
        # Create system-connections directory if it doesn't exist
        os.system('mkdir -p /etc/NetworkManager/system-connections')
        
        # Generate a unique UUID for this connection
        connection_uuid = str(uuid.uuid4())
        
        # Use UUID for filename to avoid filesystem issues with special characters
        connection_file = f'/etc/NetworkManager/system-connections/{connection_uuid}.nmconnection'
        
        # Create temporary file first
        temp_file = f'/tmp/{connection_uuid}.nmconnection.tmp'
        
        with open(temp_file, 'w') as f:
            f.write('[connection]\n')
            f.write(f'id={ssid}\n')
            f.write(f'uuid={connection_uuid}\n')
            f.write('type=wifi\n')
            f.write('autoconnect=true\n')
            f.write('autoconnect-priority=1\n')
            f.write('\n')
            
            f.write('[wifi]\n')
            f.write(f'ssid={ssid}\n')
            f.write('mode=infrastructure\n')
            f.write('\n')
            
            if wifi_key == '':
                # Open network (no security)
                f.write('[wifi-security]\n')
                f.write('key-mgmt=none\n')
            else:
                # WPA/WPA2 network
                f.write('[wifi-security]\n')
                f.write('key-mgmt=wpa-psk\n')
                f.write(f'psk={wifi_key}\n')
            
            f.write('\n')
            f.write('[ipv4]\n')
            f.write('method=auto\n')
            f.write('\n')
            
            f.write('[ipv6]\n')
            f.write('method=auto\n')
            
        # Move temp file to final location and set permissions
        move_result = os.system(f'mv {temp_file} {connection_file}')
        if move_result != 0:
            raise Exception(f"Failed to create NetworkManager connection file: {connection_file}")
            
        # Set strict permissions (only root can read/write)
        os.system(f'chmod 600 {connection_file}')
        os.system(f'chown root:root {connection_file}')
        
        # Verify file was created
        if not os.path.exists(connection_file):
            raise Exception(f"NetworkManager connection file was not created: {connection_file}")
        
        print(f"NetworkManager connection created: {connection_file}")
        return True
        
    except Exception as e:
        # Clean up temp file if it exists
        temp_file = f'/tmp/{connection_uuid}.nmconnection.tmp'
        if os.path.exists(temp_file):
            os.remove(temp_file)
        print(f"Failed to create NetworkManager connection: {str(e)}")
        return False

def cleanup_old_network_connections():
    """
    Clean up old or conflicting network connections while preserving the current one
    """
    try:
        # Get list of NetworkManager connections
        result = os.popen('nmcli -t -f NAME connection show 2>/dev/null').read()
        connections = [line.strip() for line in result.split('\n') if line.strip()]
        
        # Remove old WiFi connections but keep the one we just created
        current_time = time.time()
        nm_dir = '/etc/NetworkManager/system-connections'
        
        if os.path.exists(nm_dir):
            for filename in os.listdir(nm_dir):
                filepath = os.path.join(nm_dir, filename)
                # If file is older than 1 hour and is a WiFi connection, consider removing it
                if os.path.isfile(filepath) and filename.endswith('.nmconnection'):
                    file_age = current_time - os.path.getmtime(filepath)
                    if file_age > 3600:  # 1 hour
                        # Check if it's a WiFi connection by reading the file
                        try:
                            with open(filepath, 'r') as f:
                                content = f.read()
                                if 'type=wifi' in content:
                                    log_status(f"Removing old WiFi connection: {filename}")
                                    os.remove(filepath)
                        except:
                            pass  # Ignore errors reading old files
        
        return True
    except Exception as e:
        log_status(f"Error cleaning up old connections: {str(e)}")
        return False

def log_status(message, is_error=False):
    """Log status messages to a file for debugging"""
    log_file = '/tmp/raspiwifi_status.log'
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f'[{timestamp}] {"ERROR: " if is_error else ""} {message}\n'
    
    with open(log_file, 'a') as f:
        f.write(log_entry)
    print(log_entry)

def update_connection_status(status):
    """Update the connection status in a JSON file"""
    status_file = '/tmp/connection_status.json'
    with open(status_file, 'w') as f:
        json.dump(status, f)

def get_wifi_key_from_config(ssid):
    """Get the WiFi key from wpa_supplicant config for the given SSID"""
    try:
        with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'r') as f:
            content = f.read()
            # Simple parsing to extract password for the current SSID
            lines = content.split('\n')
            in_network = False
            current_ssid = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('network={'):
                    in_network = True
                elif line == '}' and in_network:
                    in_network = False
                    current_ssid = None
                elif in_network and line.startswith('ssid='):
                    # Extract SSID (remove quotes)
                    current_ssid = line.split('=', 1)[1].strip().strip('"')
                elif in_network and line.startswith('psk=') and current_ssid == ssid:
                    # Extract password (remove quotes)
                    return line.split('=', 1)[1].strip().strip('"')
        return None
    except Exception as e:
        print(f"Error reading wpa_supplicant config: {e}")
        return None

# Store wifi credentials globally for transition function
current_wifi_credentials = {'ssid': None, 'key': None}

if __name__ == '__main__':
    config_hash = config_file_hash()

    if config_hash['ssl_enabled'] == "1":
        app.run(host = '0.0.0.0', port = int(config_hash['server_port']), ssl_context='adhoc')
    else:
        app.run(host = '0.0.0.0', port = int(config_hash['server_port']))
