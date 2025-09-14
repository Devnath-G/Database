import json
import cv2
import os
import websocket
import subprocess
import time
import asyncio
import threading
from datetime import datetime
from urllib.parse import urlparse, urlencode
import numpy as np
from onvif import ONVIFCamera
from zeep.exceptions import Fault
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import queue

CONFIG_FILE = "/home/metro/facility_config.json"
WS_BASE_URL = "wss://10.3.158.111:3001/diagnostics"
ONVIF_PORT = 80

# **PARALLEL PROCESSING SETUP**
MAX_CONCURRENT_COMMANDS = 20  # Configurable concurrency limit
command_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_COMMANDS)
result_queue = queue.Queue()

# ---------------- Utility ---------------- #
def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"{CONFIG_FILE} not found.")
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def load_device_info():
    config = load_config()
    return {
        "edgeDeviceId": str(config["device"]["id"]),
        "facilityId": config["device"]["facilityId"],
        "macAddress": config["device"]["macAddress"],
        "devices": config["device"]["devices"]
    }

# ---------------- Protocol Functions (Same as before) ---------------- #
def protocol_ping(ip):
    try:
        result = subprocess.run(["ping", "-c", "4", ip], capture_output=True, text=True, check=False)
        success = (result.returncode == 0)
        output = result.stdout.strip() if success else result.stderr.strip()
        print(f"[{datetime.now()}] PING {ip} - {success}")
        return success, output
    except Exception as e:
        return False, str(e)

def protocol_traceroute(ip):
    try:
        result = subprocess.run(["traceroute", ip], capture_output=True, text=True, check=False)
        success = (result.returncode == 0)
        output = result.stdout.strip() if success else result.stderr.strip()
        print(f"[{datetime.now()}] TRACEROUTE {ip} - {success}")
        return success, output
    except Exception as e:
        return False, str(e)

def protocol_snmp(ip, community="public"):
    try:
        result = subprocess.run(["snmpwalk", "-v2c", "-c", community, ip], capture_output=True, text=True, check=False)
        success = (result.returncode == 0)
        output = result.stdout.strip() if success else result.stderr.strip()
        print(f"[{datetime.now()}] SNMP {ip} - {success}")
        return success, output
    except Exception as e:
        return False, str(e)

def protocol_rtsp(rtsp_url):
    try:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            return False, "Failed to open RTSP stream"
        ret, _ = cap.read()
        cap.release()
        if ret:
            print(f"[{datetime.now()}] RTSP {rtsp_url} - SUCCESS")
            return True, "online"
        else:
            print(f"[{datetime.now()}] RTSP {rtsp_url} - FAILED")
            return False, "offline"
    except Exception as e:
        return False, str(e)

def protocol_http(ip, username=None, password=None):
    try:
        url = f"http://{ip}"
        if username and password:
            password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, url, username, password)
            auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
            opener = urllib.request.build_opener(auth_handler)
            with opener.open(url, timeout=5) as response:
                print(f"[{datetime.now()}] HTTP {ip} - SUCCESS ({response.getcode()})")
                return True, f"HTTP status: {response.getcode()}"
        else:
            with urllib.request.urlopen(url, timeout=5) as response:
                print(f"[{datetime.now()}] HTTP {ip} - SUCCESS ({response.getcode()})")
                return True, f"HTTP status: {response.getcode()}"
    except Exception as e:
        print(f"[{datetime.now()}] HTTP {ip} - FAILED ({str(e)})")
        return False, str(e)

def protocol_sq_freeze(rtsp_url):
    try:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            return False, "Failed to open RTSP stream"
        ret1, frame1 = cap.read()
        if not ret1:
            cap.release()
            return False, "Failed to read first frame"
        time.sleep(1)
        ret2, frame2 = cap.read()
        if not ret2:
            cap.release()
            return False, "Failed to read second frame"
        cap.release()
        if frame1.shape != frame2.shape:
            return False, "Frames have different dimensions"
        diff = cv2.absdiff(frame1, frame2)
        mean_diff = np.mean(diff)
        threshold = 1.0
        if mean_diff < threshold:
            print(f"[{datetime.now()}] SQ_Freeze - DETECTED (frozen)")
            return False, "frozen"
        else:
            print(f"[{datetime.now()}] SQ_Freeze - NORMAL")
            return True, "normal"
    except Exception as e:
        return False, str(e)

def protocol_sq_longfreeze(rtsp_url):
    try:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            return False, "Failed to open RTSP stream"
        ret1, frame1 = cap.read()
        if not ret1:
            cap.release()
            return False, "Failed to read first frame"
        time.sleep(5)
        ret2, frame2 = cap.read()
        if not ret2:
            cap.release()
            return False, "Failed to read second frame"
        cap.release()
        if frame1.shape != frame2.shape:
            return False, "Frames have different dimensions"
        diff = cv2.absdiff(frame1, frame2)
        mean_diff = np.mean(diff)
        threshold = 1.0
        if mean_diff < threshold:
            print(f"[{datetime.now()}] SQ_LongFreeze - DETECTED (long_frozen)")
            return False, "long_frozen"
        else:
            print(f"[{datetime.now()}] SQ_LongFreeze - NORMAL")
            return True, "normal"
    except Exception as e:
        return False, str(e)

def protocol_sq_blind(rtsp_url):
    try:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            return False, "Failed to open RTSP stream"
        ret, frame = cap.read()
        if not ret:
            cap.release()
            return False, "Failed to read frame"
        cap.release()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        std_dev = np.std(gray)
        brightness_threshold = 30.0
        variance_threshold = 10.0
        if mean_brightness < brightness_threshold and std_dev < variance_threshold:
            print(f"[{datetime.now()}] SQ_Blind - DETECTED (blinded)")
            return False, "blinded"
        else:
            print(f"[{datetime.now()}] SQ_Blind - NORMAL")
            return True, "normal"
    except Exception as e:
        return False, str(e)

def protocol_onvif_get_device_info_and_rtsp(ip, username, password):
    try:
        cam = ONVIFCamera(ip, ONVIF_PORT, username, password)
        device = cam.create_devicemgmt_service()
        info = device.GetDeviceInformation()
        device_info = {
            'Manufacturer': info.Manufacturer,
            'Model': info.Model,
            'FirmwareVersion': info.FirmwareVersion,
            'SerialNumber': info.SerialNumber,
            'HardwareId': info.HardwareId
        }
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        profile = profiles[0]
        stream_setup = {
            'StreamSetup': {
                'Stream': 'RTP-Unicast',
                'Transport': {'Protocol': 'RTSP'}
            },
            'ProfileToken': profile.token
        }
        uri = media.GetStreamUri(stream_setup)
        print(f"[{datetime.now()}] ONVIF {ip} - SUCCESS")
        return True, {
            "device_info": device_info,
            "rtsp_url": uri.Uri
        }
    except Exception as e:
        print(f"[{datetime.now()}] ONVIF {ip} - FAILED ({str(e)})")
        return False, str(e)

# Map protocol names to functions
PROTOCOL_MAP = {
    "ping": protocol_ping,
    "traceroute": protocol_traceroute,
    "snmp": protocol_snmp,
    "rtsp": protocol_rtsp,
    "http": protocol_http,
    "SQ_Freeze": protocol_sq_freeze,
    "SQ_LongFreeze": protocol_sq_longfreeze,
    "SQ_Blind": protocol_sq_blind,
    "onvif_get_device_info_and_rtsp": protocol_onvif_get_device_info_and_rtsp
}

# **PARALLEL PROTOCOL EXECUTION WRAPPER**
def execute_protocol_parallel(protocol, target_ip, rtsp_link, username, password, camera_id, command_id, is_scheduled, scheduler_id):
    """Execute protocol and put result in queue for WebSocket sending"""
    print(f"[{datetime.now()}] PARALLEL START: {protocol} for camera {camera_id} (command: {command_id})")
   
    try:
        success, result = execute_protocol_func(protocol, target_ip, rtsp_link, username, password, camera_id)
       
        response = {
            "type": "command_result",
            "commandId": command_id,
            "success": success,
            "result": result,
            "cameraId": camera_id,
            "isScheduled": is_scheduled,
            "schedulerId": scheduler_id
        }
       
        result_queue.put(response)
        print(f"[{datetime.now()}] PARALLEL COMPLETE: {protocol} for camera {camera_id} - {'SUCCESS' if success else 'FAILED'}")
       
    except Exception as e:
        error_response = {
            "type": "command_result",
            "commandId": command_id,
            "success": False,
            "result": str(e),
            "cameraId": camera_id,
            "isScheduled": is_scheduled,
            "schedulerId": scheduler_id
        }
        result_queue.put(error_response)
        print(f"[{datetime.now()}] PARALLEL ERROR: {protocol} for camera {camera_id} - {str(e)}")

def execute_protocol_func(protocol, target_ip, rtsp_link, username, password, camera_id):
    func = PROTOCOL_MAP.get(protocol)
    if not func:
        return False, f"Unknown protocol {protocol}"
   
    url = None
    if protocol in ["rtsp", "SQ_Freeze", "SQ_LongFreeze", "SQ_Blind"]:
        url = rtsp_link
        if username and password and rtsp_link:
            parsed = urlparse(rtsp_link)
            if parsed.scheme == 'rtsp':
                netloc = f"{username}:{password}@{parsed.netloc}"
                url = parsed._replace(netloc=netloc).geturl()
   
    if protocol in ["ping", "traceroute"]:
        return func(target_ip)
    elif protocol == "snmp":
        community = password if password else "public"
        return func(target_ip, community=community)
    elif protocol in ["rtsp", "SQ_Freeze", "SQ_LongFreeze", "SQ_Blind"]:
        return func(url)
    elif protocol in ["http", "onvif_get_device_info_and_rtsp"]:
        return func(target_ip, username, password)
    else:
        return func(camera_id)

# **RESULT SENDER THREAD**
def result_sender_thread(ws):
    """Background thread to send results from queue to WebSocket"""
    while True:
        try:
            # Get result from queue (blocks until available)
            result = result_queue.get(timeout=1)
            if ws and ws.sock and ws.sock.connected:
                ws.send(json.dumps(result))
                print(f"[{datetime.now()}] RESULT SENT: {result['commandId']}")
            result_queue.task_done()
        except queue.Empty:
            # No results to send, continue
            continue
        except Exception as e:
            print(f"[{datetime.now()}] Error sending result: {e}")

# **ENHANCED WEBSOCKET CALLBACKS**
ws_instance = None

def on_open(ws):
    global ws_instance
    ws_instance = ws
   
    device_info = load_device_info()
    ws.send(json.dumps({
        "type": "register_edge_device",
        "edgeDeviceId": device_info["edgeDeviceId"],
        "facilityId": device_info["facilityId"],
        "macAddress": device_info["macAddress"]
    }))
    print(f"[{datetime.now()}] Connected & Registered: Edge Device {device_info['edgeDeviceId']} with {MAX_CONCURRENT_COMMANDS} parallel workers")
   
    # **START RESULT SENDER THREAD**
    sender_thread = threading.Thread(target=result_sender_thread, args=(ws,), daemon=True)
    sender_thread.start()

def on_message(ws, message):
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        print(f"[{datetime.now()}] Invalid JSON received: {message}")
        return

    msg_type = data.get("type")
   
    if msg_type == "execute_protocol":
        protocol = data.get("protocol")
        camera_id = data.get("cameraId")
        command_id = data.get("commandId")
        target_ip = data.get("targetIp")
        rtsp_link = data.get("rtspLink")
        username = data.get("username")
        password = data.get("password")
        is_scheduled = data.get("isScheduled", False)
        scheduler_id = data.get("schedulerId", None)

        print(f"[{datetime.now()}] PARALLEL DISPATCH: {protocol} for camera {camera_id}{ ' (scheduled)' if is_scheduled else ''}")

        # **SUBMIT TO THREAD POOL FOR PARALLEL EXECUTION**
        future = command_executor.submit(
            execute_protocol_parallel,
            protocol, target_ip, rtsp_link, username, password, camera_id,
            command_id, is_scheduled, scheduler_id
        )
       
        print(f"[{datetime.now()}] QUEUED: {protocol} for camera {camera_id} (active workers: {len(command_executor._threads)})")
       
    elif msg_type == "ping":
        ws.send(json.dumps({"type": "pong"}))
        print(f"[{datetime.now()}] Pong sent")
       
    elif msg_type == "connection_established":
        print(f"[{datetime.now()}] Server: Connection established - {data.get('message')}")
       
    elif msg_type == "registration_success":
        print(f"[{datetime.now()}] Server: {data.get('message')}")
       
    elif msg_type == "error":
        print(f"[{datetime.now()}] Server error: {data.get('message')}")
       
    else:
        print(f"[{datetime.now()}] Unhandled message: {data}")

def on_close(ws, close_status_code, close_msg):
    print(f"[{datetime.now()}] WebSocket closed. Shutting down thread pool...")
    command_executor.shutdown(wait=False)
    print(f"[{datetime.now()}] Reconnecting in 5 seconds...")
    time.sleep(5)
    start_ws_client()

def on_error(ws, error):
    print(f"[{datetime.now()}] WebSocket error: {error}")

# **START CLIENT WITH PARALLEL PROCESSING**
def start_ws_client():
    device_info = load_device_info()
    query_params = {
        "facilityId": device_info["facilityId"],
        "isEdgeDevice": "true",
        "edgeDeviceId": device_info["edgeDeviceId"],
        "macAddress": device_info["macAddress"]
    }
    ws_url = f"{WS_BASE_URL}?{urlencode(query_params)}"
   
    print(f"[{datetime.now()}] Starting WebSocket client with {MAX_CONCURRENT_COMMANDS} parallel workers...")
   
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_close=on_close,
        on_error=on_error
    )
    ws.run_forever()

if __name__ == "__main__":
    websocket.enableTrace(False)
    print(f"[{datetime.now()}] Edge Device starting with parallel processing enabled...")
    start_ws_client()
