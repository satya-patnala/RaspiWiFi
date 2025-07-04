import os
import subprocess

def cleanup_old_network_connections():
	"""
	Remove all previously saved WiFi connections from NetworkManager
	before initializing RaspiWiFi to prevent conflicts
	"""
	print("Cleaning up old NetworkManager WiFi connections...")
	try:
		# Get list of all NetworkManager connections
		result = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'], 
		                       capture_output=True, text=True)
		
		if result.returncode == 0:
			connections = result.stdout.strip().split('\n')
			for conn_line in connections:
				if conn_line and ':802-11-wireless' in conn_line:
					name = conn_line.split(':')[0]
					if name:
						print(f"Deleting NetworkManager WiFi connection: {name}")
						subprocess.run(['nmcli', 'connection', 'delete', name], 
						              capture_output=True)
		
		# Also remove connection files directly
		os.system('rm -f /etc/NetworkManager/system-connections/*.nmconnection 2>/dev/null')
		print("Old WiFi connections cleaned up successfully")
		
	except Exception as e:
		print(f"Warning: Error cleaning up old connections: {str(e)}")

def install_prereqs():
	os.system('clear')
	os.system('apt update')	
	os.system('clear')
	os.system('apt install python3 python3-rpi.gpio python3-pip dnsmasq hostapd -y')
	os.system('clear')
	print("Installing Flask web server...")	
	os.system('pip3 install flask pyopenssl')
	
	# Robust service management during setup
	print("Configuring system services...")
	
	# Function to robustly manage services during setup
	def setup_service(service_name, should_enable=True, should_start=True):
		print(f"Setting up {service_name}...")
		
		# Unmask first
		result = os.system(f'systemctl unmask {service_name} 2>/dev/null')
		if result != 0:
			print(f"Warning: Could not unmask {service_name}")
		
		# Enable if requested
		if should_enable:
			result = os.system(f'systemctl enable {service_name} 2>/dev/null')
			if result != 0:
				print(f"Warning: Could not enable {service_name}")
		
		# Start if requested
		if should_start:
			result = os.system(f'systemctl start {service_name} 2>/dev/null')
			if result != 0:
				print(f"Warning: Could not start {service_name}")
		
		# Verify the service state
		os.system(f'systemctl is-enabled {service_name} 2>/dev/null && echo "{service_name} is enabled" || echo "{service_name} is not enabled"')
		if should_start:
			os.system(f'systemctl is-active {service_name} 2>/dev/null && echo "{service_name} is running" || echo "{service_name} is not running"')
	
	# Unmask and enable hostapd and dnsmasq (but don't start them yet)
	setup_service('hostapd', should_enable=True, should_start=False)
	setup_service('dnsmasq', should_enable=True, should_start=False)
	
	# Disable NetworkManager to avoid conflicts with dhcpcd
	print("Disabling NetworkManager to avoid network conflicts...")
	os.system('systemctl disable NetworkManager 2>/dev/null')
	os.system('systemctl stop NetworkManager 2>/dev/null')
	
	# Ensure dhcpcd is enabled and running
	setup_service('dhcpcd', should_enable=True, should_start=True)
	
	os.system('clear')

def copy_configs(wpa_enabled_choice):
	# Clean up old NetworkManager WiFi connections before setup
	cleanup_old_network_connections()
	
	os.system('mkdir /usr/lib/raspiwifi')
	os.system('mkdir /etc/raspiwifi')
	os.system('cp -a libs/* /usr/lib/raspiwifi/')
	os.system('mv /etc/wpa_supplicant/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf.original')
	os.system('rm -f ./tmp/*')
	os.system('mv /etc/dnsmasq.conf /etc/dnsmasq.conf.original')
	os.system('cp /usr/lib/raspiwifi/reset_device/static_files/dnsmasq.conf /etc/')

	if wpa_enabled_choice.lower() == "y":
		os.system('cp /usr/lib/raspiwifi/reset_device/static_files/hostapd.conf.wpa /etc/hostapd/hostapd.conf')
	else:
		os.system('cp /usr/lib/raspiwifi/reset_device/static_files/hostapd.conf.nowpa /etc/hostapd/hostapd.conf')
	
	os.system('mv /etc/dhcpcd.conf /etc/dhcpcd.conf.original')
	os.system('cp /usr/lib/raspiwifi/reset_device/static_files/dhcpcd.conf /etc/')
	os.system('mkdir /etc/cron.raspiwifi')
	os.system('cp /usr/lib/raspiwifi/reset_device/static_files/aphost_bootstrapper /etc/cron.raspiwifi')
	os.system('chmod +x /etc/cron.raspiwifi/aphost_bootstrapper')
	os.system('echo "# RaspiWiFi Startup" >> /etc/crontab')
	os.system('echo "@reboot root run-parts /etc/cron.raspiwifi/" >> /etc/crontab')
	os.system('mv /usr/lib/raspiwifi/reset_device/static_files/raspiwifi.conf /etc/raspiwifi')
	os.system('touch /etc/raspiwifi/host_mode')
	
	# Configure static IP for wlan0 before completing setup
	configure_static_ip()
	
	# Also ensure static IP is set immediately
	ensure_wlan0_static_ip()

def update_main_config_file(entered_ssid, auto_config_choice, auto_config_delay, ssl_enabled_choice, server_port_choice, wpa_enabled_choice, wpa_entered_key):
	if entered_ssid != "":
		os.system('sed -i \'s/RaspiWiFi Setup/' + entered_ssid + '/\' /etc/raspiwifi/raspiwifi.conf')
	if wpa_enabled_choice.lower() == "y":
		os.system('sed -i \'s/wpa_enabled=0/wpa_enabled=1/\' /etc/raspiwifi/raspiwifi.conf')
		os.system('sed -i \'s/wpa_key=0/wpa_key=' + wpa_entered_key + '/\' /etc/raspiwifi/raspiwifi.conf')
	if auto_config_choice.lower() == "y":
		os.system('sed -i \'s/auto_config=0/auto_config=1/\' /etc/raspiwifi/raspiwifi.conf')
	if auto_config_delay != "":
		os.system('sed -i \'s/auto_config_delay=300/auto_config_delay=' + auto_config_delay + '/\' /etc/raspiwifi/raspiwifi.conf')
	if ssl_enabled_choice.lower() == "y":
		os.system('sed -i \'s/ssl_enabled=0/ssl_enabled=1/\' /etc/raspiwifi/raspiwifi.conf')
	if server_port_choice != "":
		os.system('sed -i \'s/server_port=80/server_port=' + server_port_choice + '/\' /etc/raspiwifi/raspiwifi.conf')

def configure_static_ip():
	"""Configure wlan0 with static IP 10.0.0.1 before rebooting"""
	# Stop any conflicting network managers
	os.system('systemctl stop NetworkManager 2>/dev/null')
	os.system('systemctl disable NetworkManager 2>/dev/null')
	
	# Ensure dhcpcd is running
	os.system('systemctl enable dhcpcd')
	os.system('systemctl start dhcpcd')
		# Ensure wlan0 has static IP configuration
	dhcpcd_config = """# RaspiWiFi Configuration
interface wlan0
static ip_address=10.0.0.1/24
static routers=10.0.0.1
static domain_name_servers=8.8.8.8 8.8.4.4
"""
	
	# Write the static IP configuration to dhcpcd.conf
	with open('/etc/dhcpcd.conf', 'w') as dhcpcd_file:
		dhcpcd_file.write(dhcpcd_config)
	
	# Set the IP immediately using ifconfig (for instant effect)
	os.system('ip link set wlan0 down')
	os.system('sleep 1')
	os.system('ip link set wlan0 up')
	os.system('sleep 2')
	os.system('ifconfig wlan0 10.0.0.1 netmask 255.255.255.0 up')
	
	# Restart dhcpcd service to apply persistent changes
	os.system('systemctl restart dhcpcd')
	
	# Give it a moment to apply
	os.system('sleep 3')
	
	# Verify the IP was set correctly
	os.system('ifconfig wlan0 | grep "inet 10.0.0.1"')

def ensure_wlan0_static_ip():
	"""Ensure wlan0 always has the static IP when in AP mode"""
	# Check if we're in host mode (AP mode)
	if os.path.exists('/etc/raspiwifi/host_mode'):
		# Stop NetworkManager if it's running
		os.system('systemctl stop NetworkManager 2>/dev/null')
		
		# Set static IP immediately
		os.system('ip link set wlan0 down 2>/dev/null')
		os.system('sleep 1')
		os.system('ip link set wlan0 up')
		os.system('sleep 1')
		os.system('ifconfig wlan0 10.0.0.1 netmask 255.255.255.0 up')
		
		# Verify it worked
		result = os.system('ifconfig wlan0 | grep "inet 10.0.0.1" > /dev/null')
		if result != 0:
			print("Warning: Failed to set wlan0 static IP")
		else:
			print("wlan0 static IP set successfully")
