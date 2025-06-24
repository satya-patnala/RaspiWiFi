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
        
        # Call set_ap_client_mode() in a thread with a longer delay
        def sleep_and_start_ap():
            time.sleep(8)  # Longer delay to ensure all file operations complete
            # Remove the flag file
            os.system('rm -f /tmp/raspiwifi_configuring')
            set_ap_client_mode()
        t = Thread(target=sleep_and_start_ap)
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
        # Create the temporary file
        temp_conf_file = open(temp_file_path, 'w')

        temp_conf_file.write('ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n')
        temp_conf_file.write('update_config=1\n')
        temp_conf_file.write('\n')
        temp_conf_file.write('network={\n')
        temp_conf_file.write('	ssid="' + ssid + '"\n')

        if wifi_key == '':
            temp_conf_file.write('	key_mgmt=NONE\n')
        else:
            temp_conf_file.write('	psk="' + wifi_key + '"\n')

        temp_conf_file.write('	}\n')

        # Ensure data is written to disk
        temp_conf_file.flush()
        os.fsync(temp_conf_file.fileno())
        temp_conf_file.close()

        # Verify temp file was created successfully
        if not os.path.exists(temp_file_path):
            raise Exception("Temporary file was not created")

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
        except:
            raise Exception("Cannot read or validate wpa_supplicant.conf")
        
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
    
    # Instead of rebooting, restart network services
    os.system('systemctl stop hostapd')
    os.system('systemctl stop dnsmasq')
    os.system('systemctl restart dhcpcd')
    
    # Restart network interface to apply new configuration
    restart_network_interface()
    
    # Start client mode services
    os.system('systemctl start wpa_supplicant')
    os.system('systemctl enable wpa_supplicant')

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


if __name__ == '__main__':
    config_hash = config_file_hash()

    if config_hash['ssl_enabled'] == "1":
        app.run(host = '0.0.0.0', port = int(config_hash['server_port']), ssl_context='adhoc')
    else:
        app.run(host = '0.0.0.0', port = int(config_hash['server_port']))
