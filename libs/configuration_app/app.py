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

    create_wpa_supplicant(ssid, wifi_key)
    
    # Call set_ap_client_mode() in a thread otherwise the reboot will prevent
    # the response from getting to the browser
    def sleep_and_start_ap():
        time.sleep(2)
        set_ap_client_mode()
    t = Thread(target=sleep_and_start_ap)
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

        temp_conf_file.close()

        # Move the file and set proper permissions
        move_result = os.system('mv ' + temp_file_path + ' /etc/wpa_supplicant/wpa_supplicant.conf')
        if move_result == 0:
            # Set proper permissions (readable/writable by root only)
            os.system('chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf')
            
            os.system('systemctl unmask wpa_supplicant')
            os.system('systemctl enable wpa_supplicant')
            
            
    except Exception as e:
        # Clean up temporary file if it exists
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

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
