from flask import Flask, render_template, request
import subprocess
import os
import time
from threading import Thread
import fileinput

app = Flask(__name__)
app.debug = True


@app.route('/')
def index():
    # Ensure static IP is set for AP mode
    ensure_ap_mode_ip()
    
    wifi_ap_array = scan_wifi_networks()
    config_hash = config_file_hash()

    return render_template('app.html', wifi_ap_array = wifi_ap_array, config_hash = config_hash)


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

    try:
        # Create a flag file to prevent reset.py from interfering
        os.system('touch /tmp/raspiwifi_configuring')
        
        # Create wpa_supplicant.conf and verify it was created successfully
        create_wpa_supplicant(ssid, wifi_key)
        
        # Double-check the file exists before proceeding
        if not os.path.exists('/etc/wpa_supplicant/wpa_supplicant.conf'):
            raise Exception("wpa_supplicant.conf was not created successfully")
        
        # Stop any conflicting services immediately
        os.system('systemctl stop hostapd')
        os.system('systemctl stop dnsmasq')
        
        # Call transition to client mode in a thread with a longer delay
        def sleep_and_transition():
            time.sleep(8)  # Longer delay to ensure all file operations complete
            # Remove the flag file
            os.system('rm -f /tmp/raspiwifi_configuring')
            # Use the new transition function instead of set_ap_client_mode
            transition_to_client_mode()
        t = Thread(target=sleep_and_transition)
        t.start()

        return render_template('save_credentials.html', ssid = ssid)
        
    except Exception as e:
        # Remove flag file on error
        os.system('rm -f /tmp/raspiwifi_configuring')
        # Return error page if file creation failed
        return render_template('save_credentials.html', ssid = ssid, error = str(e))


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
        # Clear any NetworkManager connections that might interfere
        os.system('rm -f /etc/NetworkManager/system-connections/*')
        
        # Stop NetworkManager if running to prevent interference
        os.system('systemctl stop NetworkManager 2>/dev/null')
        
        # Create the temporary file
        temp_conf_file = open(temp_file_path, 'w')

        # Write ONLY the basic configuration and the new network
        # This ensures no old networks are present
        temp_conf_file.write('ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n')
        temp_conf_file.write('update_config=1\n')
        temp_conf_file.write('country=US\n')  # Add country code for better compatibility
        temp_conf_file.write('\n')
        temp_conf_file.write('network={\n')
        temp_conf_file.write('	ssid="' + ssid + '"\n')

        if wifi_key == '':
            temp_conf_file.write('	key_mgmt=NONE\n')
        else:
            temp_conf_file.write('	psk="' + wifi_key + '"\n')
            temp_conf_file.write('	key_mgmt=WPA-PSK\n')

        temp_conf_file.write('	priority=1\n')  # Give this network highest priority
        temp_conf_file.write('	}\n')

        # Ensure data is written to disk
        temp_conf_file.flush()
        os.fsync(temp_conf_file.fileno())
        temp_conf_file.close()

        # Verify temp file was created successfully
        if not os.path.exists(temp_file_path):
            raise Exception("Temporary file was not created")

        # Move the file and set proper permissions WITHOUT stopping wpa_supplicant
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
        except:
            raise Exception("Cannot read or validate wpa_supplicant.conf")
        
        # Tell wpa_supplicant to reload the configuration without stopping the service
        os.system('wpa_cli -i wlan0 reconfigure')
        
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

def transition_to_client_mode():
    """Properly transition from AP mode to WiFi client mode with NetworkManager support"""
    
    # Stop all potentially conflicting network services
    os.system('systemctl stop hostapd')
    os.system('systemctl stop dnsmasq') 
    os.system('systemctl disable hostapd')
    os.system('systemctl disable dnsmasq')
    os.system('systemctl stop NetworkManager 2>/dev/null')
    
    # Clear any existing NetworkManager connections
    os.system('rm -f /etc/NetworkManager/system-connections/*')
    
    # Remove static IP configuration for wlan0 to allow DHCP
    os.system('ip addr flush dev wlan0')
    os.system('ip link set wlan0 down')
    os.system('ip link set wlan0 up')
    
    # Kill any existing wpa_supplicant processes
    os.system('killall wpa_supplicant 2>/dev/null')
    
    # Start fresh wpa_supplicant with our configuration
    os.system('systemctl start wpa_supplicant')
    os.system('systemctl enable wpa_supplicant')
    
    # Wait a moment for wpa_supplicant to start and read config
    time.sleep(5)
    
    # Force wpa_supplicant to reconfigure and connect
    os.system('wpa_cli -i wlan0 reconfigure')
    os.system('wpa_cli -i wlan0 reassociate')
    
    # Wait for connection attempt
    time.sleep(10)
    
    # Request DHCP lease for the WiFi connection
    os.system('dhclient -r wlan0 2>/dev/null')  # Release any existing lease
    os.system('dhclient wlan0')
    
    # Enable NetworkManager for desktop GUI compatibility after connection is established
    # This makes the WiFi icon work in the Raspberry Pi desktop
    time.sleep(5)
    os.system('systemctl unmask NetworkManager')
    os.system('systemctl enable NetworkManager')
    os.system('systemctl start NetworkManager')

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
    import subprocess
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

if __name__ == '__main__':
    # Ensure static IP is set when app starts
    ensure_ap_mode_ip()
    
    config_hash = config_file_hash()

    if config_hash['ssl_enabled'] == "1":
        app.run(host = '0.0.0.0', port = int(config_hash['server_port']), ssl_context='adhoc')
    else:
        app.run(host = '0.0.0.0', port = int(config_hash['server_port']))
