# ESP32 connection to the local AMRIN backend

The local setup uses the computer as the HTTP server and SQLite host:

```text
ESP32 sensor readings ──HTTP──> POST /api/integrations/sensors/readings ──> SQLite
ESP32-CAM JPEG ─────────HTTP──> POST /api/integrations/ml/camera/frame ──> local YOLO ──> alerts/evidence in SQLite + uploads
Browser dashboard ──────HTTP──> Vite /api proxy ────────────────────────> backend on port 5000
```

The backend is configured to listen on `0.0.0.0:5000`; the Vite dashboard listens on `0.0.0.0:5173`. Both the computer and ESP32 must be on the same trusted Wi-Fi/LAN. The ESP32 must use the computer's current private LAN address in its URLs; `localhost` on the ESP32 means the ESP32 itself. The address can change if the router changes its DHCP lease.

## Device already registered

The local SQLite database contains the camera device ID `esp32-cam-01`. Send this exact ID with sensor and camera requests. Other IDs must first be registered in the backend database.

## Sensor readings

Send JSON to `http://<computer-lan-ip>:5000/api/integrations/sensors/readings` with header `X-Sensor-API-Key` set to the local `SENSOR_INGEST_TOKEN` from `backend/.env`:

```json
{
  "device_id": "esp32-cam-01",
  "source": "esp32",
  "readings": [
    { "name": "temperature", "value": 28.4, "unit": "C", "status": "OK" },
    { "name": "vibration", "value": 0.12, "unit": "g", "status": "OK" }
  ]
}
```

Replace the sample values with readings from the sensors actually wired to the board. Each accepted reading is stored in SQLite and can be combined with a camera detection for alert context.

## Camera frames and local inference

POST a multipart form to `http://<computer-lan-ip>:5000/api/integrations/ml/camera/frame`. ML ingest endpoints currently do not require an API key; keep them on a trusted network. Form fields:

- `device_id`: `esp32-cam-01`
- `image`: a JPEG file from the camera
- `captured_at`: optional ISO 8601 timestamp, such as `2026-10-29T12:30:00Z`
- `latitude` and `longitude`: optional GPS coordinates

The backend runs the calibrated `best.pt` model on its CPU. It saves the latest frame, stores detections and alert metadata in SQLite, and keeps an annotated JPEG as protected evidence for positive detections. Repeated detections of the same class from the same device are limited by the configured alert cooldown.

## API keys and local network

Copy the two API keys from `backend/.env` into a private ESP32 secrets header that is excluded from version control. Do not put the keys in a public firmware repository. The current Vite proxy lets a browser on another LAN device use the dashboard without hard-coding a computer IP in the frontend. A Windows firewall may need to allow private-network access to ports `5173` and `5000`.

This repository does not yet contain ESP32 firmware or the physical sensor model/pin mapping. Once the exact ESP32 board and attached sensor models are known, add their board-specific capture and reading code; the HTTP endpoints and database side are ready for it.
