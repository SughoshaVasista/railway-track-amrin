# RailSafe Raspberry Pi Robot Starter

This is a **prototype starter**, not railway-certified control software. Test only on a small model track with the wheels lifted or the robot secured. Never connect it to a real railway system.

## What it does
1. Captures frames continuously on a dedicated camera thread; inference always takes the newest frame (one latest-frame buffer, no growing queue).
2. Runs the existing YOLO model (`best.pt`) and uploads one replaceable latest annotated frame/status per device every few seconds.
3. On a new detection, saves the annotated photo locally and uploads it with the ML event so it appears on the authenticated Alerts and AI pages.
4. Reads NMEA GPS independently; a detection can still be saved when no fresh GPS fix is available.
5. Sends camera/GPS telemetry on its own timed thread and writes a local JSONL event log.

## Important integration limitations
- The Pi image routes require this repository's FastAPI backend, with `ML_INGEST_TOKEN` configured and `DEVICE_ID` registered. The separate legacy hosted API does not have these new routes.
- Latest frames replace one JPEG per device; detection images are retained by alert. Backend image storage is under `UPLOAD_FOLDER` (default `backend/uploads/evidence`).
- Severity is assigned by configurable confidence thresholds as a demo policy. This is not a railway engineering risk assessment. Tune only for a controlled prototype and verify labels against your model/data.
- The motor pin mapping assumes a common L298N-style driver. Confirm your actual driver and wiring before enabling motor control. GPIO pins below must not conflict with sensors. Never power motors from the Pi's 3.3V pin.

## Folder layout
```text
railsafe_pi_robot/
├── robot.py
├── config.py
├── requirements.txt
├── .env.example
├── models/
│   └── best.pt          # copy your trained YOLO weights here
├── data/
│   ├── evidence/        # captured crack photos
│   ├── events.jsonl     # local event log / basic offline log
│   └── pending/         # reserved for future retry queue
└── logs/
```

## 1. Prepare the Pi
Use Raspberry Pi OS 64-bit where compatible with your installed model/runtime.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-picamera2 python3-opencv
mkdir -p ~/railsafe_pi_robot/{models,data/evidence,data/pending,logs}
cd ~/railsafe_pi_robot
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

Copy `robot.py`, `config.py`, `requirements.txt`, and `.env.example` into this directory. Copy your trained model to `models/best.pt`.

Install Python packages:
```bash
pip install -r requirements.txt
```
If `ultralytics`/PyTorch is unsupported or too heavy for your Pi OS/Python version, use your supported TFLite/NCNN runtime instead; do not assume this PyTorch-based example will install on every Pi image.

## 2. Configure `.env`
```bash
cp .env.example .env
nano .env
```
Set:
- `BACKEND_URL`: address reachable from the Pi, e.g. `http://192.168.1.20:8000` if backend runs on your laptop. Do not use `127.0.0.1` for the laptop backend from the Pi.
- `ML_INGEST_TOKEN`: same secret as backend `ML_INGEST_TOKEN`.
- `DEVICE_ID`: ID of a device already registered in backend.
- `GPS_PORT`: usually `/dev/serial0` after enabling UART.
- `CRACK_CLASS_NAMES`: exact class names in your model, e.g. `crack,rail_crack`.
- `CAMERA_CAPTURE_INTERVAL_SECONDS`: camera sampling interval (default `0.2`, about 5 frames/sec).
- `FRAME_UPLOAD_INTERVAL_SECONDS`: latest-frame upload interval (default `3` seconds).
- `TELEMETRY_INTERVAL_SECONDS`: sensor telemetry interval (default `5` seconds).

Do not commit `.env` or API secrets to Git.

## 3. Check the camera
```bash
rpicam-hello --list-cameras
```
If Picamera2 cannot access the camera, fix that before running the full robot.

## 4. Check GPS UART
Enable Serial Port in `sudo raspi-config` → Interface Options → Serial Port:
- Login shell over serial: **No**
- Serial hardware: **Yes**
Reboot if prompted. GPS may not get a fix indoors; test outdoors or near an open sky.

## 5. Motor safety
Default `MOTOR_ENABLED=false`. Keep it false for the first camera/model/network test.
Only if your motor driver is confirmed as L298N-compatible and the pin mapping has been checked:
1. Lift wheels clear of the ground.
2. Check motor supply, common ground, enable jumpers/PWM, and wiring.
3. Change `MOTOR_ENABLED=true`.
4. Use a hardware emergency-stop/power switch.
5. Test at low speed on a model track. The code stops then reverses briefly, then stops again. It does not know whether the path behind is clear.

## 6. Run
```bash
source .venv/bin/activate
python robot.py
```
Stop with `Ctrl+C`.

## Backend and frontend
Start the backend on the laptop bound to `0.0.0.0:8000` only on a trusted private LAN, and allow the port through the laptop firewall as appropriate. Configure the Pi's `BACKEND_URL` with the laptop's LAN IP. The frontend can remain on the laptop at `http://localhost:5173`.

The robot posts latest snapshots to `POST /api/integrations/ml/frames` and defect events plus annotated JPEGs to `POST /api/integrations/ml/events/with-image`, both using `X-ML-API-Key: <ML_INGEST_TOKEN>`. The app reads the latest snapshot from `GET /api/ai/detection` and fetches its protected image from `GET /api/devices/{device_id}/camera/latest`. Alert JPEG evidence is fetched from `GET /api/alerts/{alert_id}/image`. Register the device first using `POST /api/devices` as an admin. Visit `/docs` on the same backend to inspect and try these endpoints.

To populate the frontend Hardware Monitor, register `DEVICE_ID` first and configure the Pi's `.env`:

- For the deployed API documented at `/docs`, set `API_KEY` to its `X-API-Key`, set `CAMERA_SENSOR_ID` and `GPS_SENSOR_ID`, and register those IDs with `POST /api/sensors` using types `CAMERA` and `GPS`. With `SENSOR_API_MODE=auto`, the Pi posts numeric, axis-tagged readings to `POST /api/sensors/readings` every `TELEMETRY_INTERVAL_SECONDS` (default 5 seconds).
- For this repository's local backend, set `SENSOR_INGEST_TOKEN` to the backend's matching value and leave `SENSOR_API_MODE=auto` without `API_KEY`. The Pi posts structured readings to `POST /api/integrations/sensors/readings` with `X-Sensor-API-Key`.

The Hardware page reads the registered device, latest readings, and diagnostics from the API. This starter has camera and GPS inputs only; ultrasonic, accelerometer, and temperature remain unavailable until those sensors are installed and a gateway sends their readings.

For the repository backend, create `backend/.env` from `backend/.env.example`, set a long random `JWT_SECRET_KEY`, `ML_INGEST_TOKEN`, and (if posting structured hardware telemetry) `SENSOR_INGEST_TOKEN`. Start it from `backend/` with `.venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000` on Windows or `.venv/bin/uvicorn ...` on Raspberry Pi/Linux. Point the frontend `VITE_API_BASE_URL` and Pi `BACKEND_URL` to this same backend. Use `/docs` to register the Pi device after signing in as admin.
