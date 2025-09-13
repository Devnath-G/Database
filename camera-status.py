import json
import cv2
import os
import requests

# Accessing Facility Configuration
CONFIG_FILE = "/home/metro/facility_config.json"

# Sending data to backend
BASE_URL = "https://visionanalytics.prod.squirrelvision.ai/api/devices" 

def load_config(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"{file_path} not found.")
    
    with open(file_path, "r") as f:
        data = json.load(f)
    return data

def check_rtsp_stream(rtsp_url, timeout=5):
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        return False
    cap.set(cv2.CAP_PROP_POS_MSEC, timeout * 1000)
    ret, _ = cap.read()
    cap.release()
    return ret

def update_device_status(device_id, status):
    """Send status update to the backend API."""
    url = f"{BASE_URL}/{device_id}"
    payload = { "status": status }
    
    try:
        response = requests.put(url, json=payload)
        if response.status_code == 200:
            print(f"[INFO] Updated device {device_id} to {status}")
        else:
            print(f"[INFO] Failed to update device {device_id} ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"[INFO] Error updating device {device_id}: {e}")

def main():
    config = load_config(CONFIG_FILE)
    facility_id = config["device"]["facilityId"]
    print(f"Facility ID: {facility_id}")

    for device in config["device"]["devices"]:
        camera_name = device["name"]
        rtsp_link = device["rtsp_link"]
        device_id = device["id"]

        print(f"\nChecking Camera: {camera_name}")
        is_online = check_rtsp_stream(rtsp_link)
        status = "online" if is_online else "offline"
        
        print(f"RTSP: {rtsp_link}")
        print(f"Status: {status}")

        # Update status in backend
        update_device_status(device_id, status)

if __name__ == "__main__":
    main()
