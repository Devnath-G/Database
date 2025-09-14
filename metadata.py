# ===================================================
# Homographic Post-Processing Script (w/WebSocket) 
# ===================================================

import json
import os
import time
import threading
import websocket
import queue

DEBUG = False

# Constants
PROCESSING_WIDTH = 640
PROCESSING_HEIGHT = 640
GRID_SIZE = 300
WS_URL = "wss://visionanalyticsws.prod.squirrelvision.ai/edge"
METADATA_PATH = "/home/metro/facility_config.json"

class StreamIDCounter:
    _instance = None
    _counter = 0
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StreamIDCounter, cls).__new__(cls)
        return cls._instance

    def get_next_id(self):
        with self._lock:
            current_id = self._counter
            self._counter += 1
        return current_id

class WebSocketDetector:
    def __init__(self):
        self.stream_id = StreamIDCounter().get_next_id()
        self.device_id, self.rtsp_url = self._get_device_metadata(self.stream_id)

        # Print mapping info
        print(f"[MAPPING] Stream {self.stream_id} -> deviceId: {self.device_id} -> RTSP: {self.rtsp_url}")

        self.ws_lock = threading.Lock()
        self.ws = None
        self.stop_processing = False
        self.message_queue = queue.Queue(maxsize=100)
        self.last_sent_detections = {}

        self._start_websocket_thread()
        self._start_message_processor()

    def _get_device_metadata(self, stream_index):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            flat_devices = [
                dev for dev in data.get("device", {}).get("devices", [])
                if dev.get("rtsp_link")
            ]
            device = flat_devices[stream_index]
            return device.get("id"), device.get("rtsp_link")
        except Exception as e:
            print(f"[ERROR] Failed to get device metadata for stream {stream_index}: {e}")
            return f"unknown_stream_{stream_index}", "N/A"

    def _start_websocket_thread(self):
        self.ws_thread = threading.Thread(target=self._manage_websocket, daemon=True)
        self.ws_thread.start()

    def _start_message_processor(self):
        self.message_thread = threading.Thread(target=self._process_messages, daemon=True)
        self.message_thread.start()

    def _manage_websocket(self):
        while not self.stop_processing:
            if not self.ws or not self.ws.connected:
                self._connect_websocket()
            else:
                self._send_heartbeat()
            time.sleep(2)

    def _connect_websocket(self):
        attempt = 0
        while not self.stop_processing:
            try:
                attempt += 1
                if DEBUG:
                    print(f"[INFO] Stream {self.stream_id} - Attempting WebSocket connection (attempt {attempt})")
                with self.ws_lock:
                    self.ws = websocket.create_connection(WS_URL, timeout=10)
                    self.ws.settimeout(10)
                    if DEBUG:
                        print(f"[INFO] Stream {self.stream_id} - Connected to WebSocket: {WS_URL}")
                break
            except Exception as e:
                if DEBUG:
                    print(f"[ERROR] Stream {self.stream_id} - WebSocket connection failed: {str(e)}")
                time.sleep(min(2 ** (attempt // 2), 10))

    def _send_heartbeat(self):
        if self.ws and self.ws.connected:
            try:
                with self.ws_lock:
                    self.ws.send(json.dumps({"event": "heartbeat"}))
                if DEBUG:
                    print(f"[DEBUG] Stream {self.stream_id} - Sent heartbeat")
            except Exception as e:
                if DEBUG:
                    print(f"[ERROR] Stream {self.stream_id} - Heartbeat failed: {str(e)}")
                with self.ws_lock:
                    self.ws = None

    def _process_messages(self):
        while not self.stop_processing:
            try:
                message = self.message_queue.get(timeout=1)
                self._send_message(message)
                self.message_queue.task_done()
            except queue.Empty:
                continue

    def _send_message(self, message):
        if not self.ws or not self.ws.connected:
            self._connect_websocket()
            if not self.ws or not self.ws.connected:
                if DEBUG:
                    print(f"[ERROR] Stream {self.stream_id} - WebSocket not connected, dropping message")
                return
        try:
            with self.ws_lock:
                self.ws.send(json.dumps(message))
            if DEBUG:
                print(f"[DEBUG] Stream {self.stream_id} - Sent data: {json.dumps(message)}")
        except Exception as e:
            if DEBUG:
                print(f"[ERROR] Stream {self.stream_id} - Failed to send data: {str(e)}")
            with self.ws_lock:
                self.ws = None
            self._connect_websocket()

    def process_frame(self, frame):
        rois = list(frame.regions())
        class_detections = {}

        for roi in rois:
            x, y, w, h = roi.rect()

            if not hasattr(roi, "object_id") or not callable(roi.object_id):
                continue
            obj_id = roi.object_id()
            if obj_id is None:
                continue

            if not hasattr(roi, "label") or not callable(roi.label):
                continue
            label = roi.label() or "unknown"

            # Compute center coordinates
            center_x = (x + w / 2) / PROCESSING_WIDTH
            center_y = (y + h / 2) / PROCESSING_HEIGHT
            grid_x = min(max(center_x * GRID_SIZE, 0), GRID_SIZE)
            grid_y = min(max(center_y * GRID_SIZE, 0), GRID_SIZE)

            # Group detections by label
            if label not in class_detections:
                class_detections[label] = []
            class_detections[label].append({"x": int(grid_x), "y": int(grid_y)})

            if DEBUG:
                print(f"[Detect] Stream {self.stream_id} - {label} at ({x}, {y}, {w}, {h})")

        if class_detections:
            people_count = len(class_detections.get("person", []))
            vehicle_count = len(class_detections.get("vehicle", []))

            message = {
                "deviceId": self.device_id,
                "detections": class_detections,
                "people_count": people_count,
                "vehicle_count": vehicle_count
            }

            # Only send if detections changed
            if class_detections != self.last_sent_detections:
                self.last_sent_detections = json.loads(json.dumps(class_detections)) 
                try:
                    self.message_queue.put_nowait(message)
                except queue.Full:
                    if DEBUG:
                        print(f"[WARNING] Stream {self.stream_id} - Message queue full, dropping message")
            else:
                if DEBUG:
                    print(f"[SKIP] Stream {self.stream_id} - No change in detections")

        return True

    def __del__(self):
        self.stop_processing = True
        if self.ws:
            with self.ws_lock:
                self.ws.close()
