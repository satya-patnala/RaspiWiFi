import RPi.GPIO as GPIO
import os
import time
import subprocess
import reset_lib

# Add boot delay to prevent immediate reboot loops
print("RaspiWiFi: Waiting 10 seconds before checking configuration...")
time.sleep(10)

GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

counter = 0
serial_last_four = subprocess.check_output(['cat', '/proc/cpuinfo'])[-5:-1].decode('utf-8')
config_hash = reset_lib.config_file_hash()
ssid_prefix = config_hash['ssid_prefix'] + " "
reboot_required = False


# Check if configuration is in progress and skip reboot if so
if os.path.exists('/tmp/raspiwifi_configuring'):
    print("Configuration in progress, skipping automatic reboot")
    reboot_required = False
elif os.path.exists('/tmp/raspiwifi_recent_boot'):
    print("Recent boot detected, skipping reboot to prevent loops")
    reboot_required = False
else:
    # Create flag to prevent reboot loops
    os.system('touch /tmp/raspiwifi_recent_boot')
    # Remove the flag after 60 seconds
    os.system('(sleep 60; rm -f /tmp/raspiwifi_recent_boot) &')
    
    reboot_required = reset_lib.wpa_check_activate(config_hash['wpa_enabled'], config_hash['wpa_key'])
    if not reboot_required:
        reboot_required = reset_lib.update_ssid(ssid_prefix, serial_last_four)

if reboot_required == True:
    print("RaspiWiFi: Configuration change detected, rebooting in 5 seconds...")
    time.sleep(5)
    os.system('reboot')

# This is the main logic loop waiting for a button to be pressed on GPIO 18 for 10 seconds.
# If that happens the device will reset to its AP Host mode allowing for reconfiguration on a new network.
while True:
    while GPIO.input(18) == 1:
        time.sleep(1)
        counter = counter + 1

        print(counter)

        if counter == 9:
            reset_lib.reset_to_host_mode()

        if GPIO.input(18) == 0:
            counter = 0
            break

    time.sleep(1)
