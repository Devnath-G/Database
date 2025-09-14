#!/bin/bash

# ============================
# DL Streamer Facility Pipeline (Lightweight, No Encoding, No Compositor)
# ============================

# Use Case
USE_CASE="traffic_monitoring"

# Model Configurations
MODEL_DIR="/home/metro/models/person-vehicle-bike-detection"
MODEL_NAME="person-vehicle-bike-detection-2004"
MODEL_XML="$MODEL_DIR/${MODEL_NAME}.xml"
MODEL_BIN="$MODEL_DIR/${MODEL_NAME}.bin"
MODEL_PROC="$MODEL_DIR/${MODEL_NAME}.json"

# Facility Configuration file
STREAM_JSON="/home/metro/facility_config.json"

# ----------------------------
# Extract facilityId using Python
# ----------------------------
FACILITY_ID=$(python3 -c "
import json
with open('$STREAM_JSON') as f:
    data = json.load(f)
print(data['device']['facilityId'])
")

# ----------------------------
# Extract RTSP streams for given USE_CASE using Python
# ----------------------------
RTSP_STREAMS=($(python3 -c "
import json
use_case = '$USE_CASE'
with open('$STREAM_JSON') as f:
    data = json.load(f)
streams = [d['rtsp_link'] for d in data['device']['devices']
           if 'enabledUseCases' in d and use_case in d['enabledUseCases']]
for s in streams:
    print(s)
"))

# ----------------------------
# Error handling
# ----------------------------
if [ -z "$FACILITY_ID" ]; then
    echo "[ERROR] Facility ID not found in metadata file."
    exit 1
fi

if [ ${#RTSP_STREAMS[@]} -eq 0 ]; then
    echo "[ERROR] No RTSP streams found for use case \"$USE_CASE\". Exiting."
    exit 1
fi

echo "[INFO] Using facilityId=$FACILITY_ID"
echo "[INFO] Found ${#RTSP_STREAMS[@]} RTSP stream(s) for use case \"$USE_CASE\"."

# Video dimensions for detection
PROCESS_WIDTH=640
PROCESS_HEIGHT=640

# Use CPU for gvadetect
DEVICE="CPU"

# ----------------------------
# Build lightweight pipeline per stream
# ----------------------------
PIPELINE_BASE="rtspsrc latency=100 protocols=tcp"

# Watchdog wrapper
while true; do
    echo "[INFO] Starting lightweight detection pipeline..."
    
    # Build pipelines for each stream
    for i in "${!RTSP_STREAMS[@]}"; do
        STREAM_PIPELINE="\
rtspsrc location=${RTSP_STREAMS[$i]} latency=100 protocols=tcp ! \
rtph264depay ! avdec_h264 ! \
queue max-size-buffers=0 max-size-time=100000000 leaky=downstream ! \
videoconvert ! videoscale ! video/x-raw,width=$PROCESS_WIDTH,height=$PROCESS_HEIGHT,format=NV12 ! \
gvadetect model=$MODEL_XML model_proc=$MODEL_PROC device=$DEVICE threshold=0.2 nireq=4 batch-size=1 model-instance-id=live pre-process-backend=opencv ! \
gvatrack tracking-type=zero-term-imageless ! \
gvapython module=/home/metro/metadata.py class=WebSocketDetector"

        # Run each stream in background
        gst-launch-1.0 -e $STREAM_PIPELINE &
    done

    # Wait for all pipelines to exit
    wait
    echo "[WARN] One or more pipelines stopped. Restarting in 5 seconds..."
    sleep 5
done
