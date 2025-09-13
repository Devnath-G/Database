import requests
import cv2
import time
import numpy as np
import json
import os

# === Load facility ID from config ===
CONFIG_PATH = "/home/ubuntu/facility_config.json"

if not os.path.exists(CONFIG_PATH):
    print(f"[ERROR] Configuration file not found at {CONFIG_PATH}")
    exit(1)

with open(CONFIG_PATH, "r") as f:
    config_data = json.load(f)

# Extract facilityId
try:
    FACILITY_ID = config_data["device"]["facilityId"]
except (KeyError, TypeError):
    print("[ERROR] 'facilityId' not found in configuration file.")
    exit(1)

# === API Endpoints ===
BASE_URL = f"http://10.3.158.111:3000/api/facilities?facilityId={FACILITY_ID}"
SNAPSHOT_URL_TEMPLATE = "http://10.3.158.111:3000/api/snapshot?deviceId={device_id}"

print(f"[INFO] Fetching facility info from {BASE_URL}")
response = requests.get(BASE_URL)
response.raise_for_status()
data = response.json()

# === Extract RTSP devices ===
devices = []
for zone in data.get("zones", []):
    for device in zone.get("devices", []):
        rtsp_link = device.get("rtsp_link")
        device_id = device.get("id")
        if rtsp_link and device_id:
            devices.append((device_id, rtsp_link))

if not devices:
    print("[INFO] No devices found.")
    exit()

# === Snapshot and upload ===
for device_id, rtsp_link in devices:
    print(f"[PROCESSING] Device {device_id} - {rtsp_link}")

    cap = cv2.VideoCapture(rtsp_link)
    if not cap.isOpened():
        print(f"[FAIL] Unable to open stream for device {device_id}")
        continue

    time.sleep(5)  # wait for stream to stabilize

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print(f"[FAIL] Couldn't read frame from device {device_id}")
        continue

    # Encode image as JPEG in memory
    success, img_encoded = cv2.imencode('.jpg', frame)
    if not success:
        print(f"[FAIL] JPEG encoding failed for device {device_id}")
        continue

    snapshot_bytes = img_encoded.tobytes()
    files = {
        "snapshot": ("snapshot.jpg", snapshot_bytes, "image/jpeg"),
        "deviceId": (None, str(device_id)),
        "isEdgeDevice": (None, "true"),
        "type": (None, "snapshot"),
    }

    upload_url = SNAPSHOT_URL_TEMPLATE.format(device_id=device_id)
    print(f"[UPLOAD] Sending snapshot to {upload_url}")
    res = requests.post(upload_url, files=files)

    if res.status_code != 200:
        print(f"[UPLOAD FAILED] Device {device_id} - Status: {res.status_code}")
        try:
            print(f"[DETAILS] {res.json()}")
        except:
            print("[DETAILS] Could not parse error response")
    else:
        print(f"[SUCCESS] Snapshot uploaded for device {device_id}")
