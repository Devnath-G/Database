# ==============================
# Edge-Device Onboarding/Registeration 
# ==============================

import socket
import fcntl
import struct
import os
import subprocess
import shutil
import platform
import requests
import json

def get_hostname():
    return socket.gethostname()

def get_mac_address():
    try:
        interfaces = os.listdir('/sys/class/net/')
        interfaces = [i for i in interfaces if not i.startswith(('lo', 'docker', 'br', 'veth'))]

        for iface in interfaces:
            operstate_path = f'/sys/class/net/{iface}/operstate'
            try:
                with open(operstate_path, 'r') as f:
                    state = f.read().strip()
                if state != 'up':
                    continue
            except FileNotFoundError:
                continue

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                info = fcntl.ioctl(
                    s.fileno(),
                    0x8927,
                    struct.pack('256s', iface[:15].encode('utf-8'))
                )
                mac = ':'.join(f'%02x' % b for b in info[18:24])
                return mac
            except Exception:
                continue
    except Exception as e:
        print(f"[ERROR] Could not read MAC address: {e}")
    return None

def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def get_cpu_info():
    try:
        output = subprocess.check_output("lscpu", shell=True, text=True)
        for line in output.splitlines():
            if "Model name" in line:
                return line.split(":")[1].strip()
    except Exception:
        return None

def get_ram_info():
    try:
        output = subprocess.check_output("free -h", shell=True, text=True)
        for line in output.splitlines():
            if line.lower().startswith("mem:"):
                return line.split()[1]
    except Exception:
        return None

def get_os_info():
    try:
        if shutil.which("lsb_release"):
            return subprocess.check_output("lsb_release -d", shell=True, text=True).split(":")[1].strip()
        else:
            return platform.platform()
    except Exception:
        return None

def get_manufacturer_info():
    try:
        with open('/sys/class/dmi/id/sys_vendor') as f:
            manufacturer = f.read().strip()
        with open('/sys/class/dmi/id/product_name') as f:
            product = f.read().strip()
        return f"{manufacturer} {product}"
    except Exception:
        return None

def get_firmware_info():
    try:
        with open('/sys/class/dmi/id/bios_version') as f:
            return f.read().strip()
    except Exception:
        return None

def send_device_info(endpoint):
    hostname = get_hostname()
    mac = get_mac_address()
    ip = get_ip_address()
    cpu = get_cpu_info()
    ram = get_ram_info()
    os_info = get_os_info()
    manufacturer = get_manufacturer_info()
    firmware = get_firmware_info()

    configuration = f"CPU: {cpu}, RAM: {ram}, OS: {os_info}, Manufacturer: {manufacturer}, Firmware: {firmware}"

    device_data = {
        "hostname": hostname,
        "macAddress": mac,
        "configuration": configuration,
        "ipAddress": ip
    }

    # Save device config (pretty JSON)
    try:
        with open("/home/metro/device_config.json", "w") as f:
            json.dump(device_data, f, indent=2)
        print("[INFO] Device configuration saved!")
    except Exception as e:
        print(f"[ERROR] Failed to save device config file: {e}")

    # Send to backend and save full raw response
    try:
        response = requests.post(endpoint, json=device_data)
        if response.status_code == 200:
            print("[SUCCESS] Device information sent successfully.")
            print(response.json())

            # Save raw server response
            try:
                with open("/home/metro/facility_config.json", "w") as f:
                    f.write(response.text)
                print("[INFO] Facility configuration saved!")
            except Exception as e:
                print(f"[ERROR] Failed to save raw facility config: {e}")

        else:
            print(f"[ERROR] Failed to send data. Status code: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"[EXCEPTION] {e}")

if __name__ == "__main__":
    send_device_info("https://visionanalytics.prod.squirrelvision.ai/api/register-edgedevice")
