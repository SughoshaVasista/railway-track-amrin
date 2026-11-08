import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import pynmea2
import requests
import serial
from picamera2 import Picamera2
from ultralytics import YOLO
from gpiozero import DigitalOutputDevice

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_DIR / "robot.log"),
    ],
)
log = logging.getLogger("railsafe-robot")
STOP_REQUESTED = False


def stop_handler(_signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


class MotorController:
    """Minimal L298N-style direction control; no speed/PWM control in this starter."""
    def __init__(self):
        self.enabled = config.MOTOR_ENABLED
        self.pins = []
        if not self.enabled:
            log.warning("Motor control DISABLED. Detection will not move the robot.")
            return
        if config.MOTOR_DRIVER != "l298n":
            raise RuntimeError("This example only supports a verified L298N-style driver.")
        self.left1 = DigitalOutputDevice(config.MOTOR_LEFT_IN1, initial_value=False)
        self.left2 = DigitalOutputDevice(config.MOTOR_LEFT_IN2, initial_value=False)
        self.right1 = DigitalOutputDevice(config.MOTOR_RIGHT_IN1, initial_value=False)
        self.right2 = DigitalOutputDevice(config.MOTOR_RIGHT_IN2, initial_value=False)
        self.pins = [self.left1, self.left2, self.right1, self.right2]
        self.stop()

    def stop(self):
        if self.enabled:
            for pin in self.pins:
                pin.off()

    def reverse_briefly(self):
        if not self.enabled:
            log.warning("Detection triggered, but motor action skipped because MOTOR_ENABLED=false.")
            return
        log.warning("CRACK DETECTED: stop, brief reverse, stop. Ensure path behind is clear.")
        self.stop()
        time.sleep(0.3)
        # Reverse direction on both motors. If the robot moves forward instead,
        # power down and correct motor wiring/configuration before retesting.
        self.left1.off()
        self.left2.on()
        self.right1.off()
        self.right2.on()
        time.sleep(max(0.1, config.MOTOR_REVERSE_SECONDS))
        self.stop()

    def close(self):
        self.stop()
        for pin in self.pins:
            pin.close()


class GpsReader:
    def __init__(self):
        self.ser = None
        self.last_fix = None
        try:
            self.ser = serial.Serial(
                config.GPS_PORT, config.GPS_BAUD, timeout=config.GPS_READ_TIMEOUT
            )
            log.info("GPS serial opened: %s", config.GPS_PORT)
        except Exception as exc:
            log.warning("GPS unavailable (%s). Events will be logged locally until a fix exists.", exc)

    def update(self):
        if not self.ser:
            return
        # Read a few lines without blocking camera inference for too long.
        for _ in range(4):
            try:
                line = self.ser.readline().decode("ascii", errors="ignore").strip()
                if not line.startswith("$"):
                    continue
                msg = pynmea2.parse(line)
                if getattr(msg, "sentence_type", "") == "GGA":
                    lat = getattr(msg, "latitude", 0.0)
                    lon = getattr(msg, "longitude", 0.0)
                    quality = int(getattr(msg, "gps_qual", 0) or 0)
                    if quality > 0 and lat and lon:
                        satellites = int(getattr(msg, "num_sats", 0) or 0)
                        self.last_fix = {
                            "latitude": float(lat),
                            "longitude": float(lon),
                            "gps_accuracy_m": None,
                            "satellites": satellites or None,
                            "received_monotonic": time.monotonic(),
                        }
            except (ValueError, pynmea2.ParseError, serial.SerialException):
                continue

    def update_forever(self, stop_event):
        while not stop_event.is_set():
            try:
                self.update()
            except Exception:
                log.exception("GPS reader failed; will retry")
                stop_event.wait(1)

    def get_fix(self):
        if not self.last_fix:
            return None
        if time.monotonic() - self.last_fix["received_monotonic"] > config.GPS_MAX_AGE_SECONDS:
            return None
        return {k: v for k, v in self.last_fix.items() if k != "received_monotonic"}

    def close(self):
        if self.ser:
            self.ser.close()


def severity_for(confidence: float) -> str:
    # Demo mapping only. Replace with validated defect-specific severity rules.
    if confidence >= config.SEVERITY_S3_CONFIDENCE:
        return "S3"
    if confidence >= config.SEVERITY_S2_CONFIDENCE:
        return "S2"
    return "S1"


def log_event_locally(event: dict):
    config.EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with config.EVENT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def send_event(event: dict, image_path: Path | None = None) -> bool:
    if not config.ML_INGEST_TOKEN:
        log.error("ML_INGEST_TOKEN is empty; event only logged locally.")
        return False
    url = f"{config.BACKEND_URL}/api/integrations/ml/events/with-image" if image_path else f"{config.BACKEND_URL}/api/integrations/ml/events"
    headers = {"X-ML-API-Key": config.ML_INGEST_TOKEN}
    try:
        if image_path:
            with image_path.open("rb") as photo:
                response = requests.post(url, data={"event": json.dumps(event)}, files={"image": (image_path.name, photo, "image/jpeg")}, headers=headers, timeout=10)
        else:
            response = requests.post(url, json=event, headers=headers, timeout=5)
        if response.status_code >= 400:
            log.error("Backend rejected event (%s): %s", response.status_code, response.text[:500])
            return False
        log.info("Backend accepted event: %s", response.json())
        return True
    except requests.RequestException as exc:
        log.error("Backend unavailable; event saved locally: %s", exc)
        return False


def send_latest_frame(snapshot: dict, jpeg: bytes | None) -> bool:
    if not config.ML_INGEST_TOKEN:
        return False
    headers = {"X-ML-API-Key": config.ML_INGEST_TOKEN}
    try:
        files = {"image": ("latest.jpg", jpeg, "image/jpeg")} if jpeg else {}
        response = requests.post(
            f"{config.BACKEND_URL}/api/integrations/ml/frames",
            data={"snapshot": json.dumps(snapshot)},
            files=files,
            headers=headers,
            timeout=8,
        )
        if response.status_code >= 400:
            log.warning("Backend rejected latest camera snapshot (%s): %s", response.status_code, response.text[:300])
            return False
        return True
    except requests.RequestException as exc:
        log.warning("Latest camera snapshot was not uploaded: %s", exc)
        return False
def send_sensor_telemetry(camera_fps: float, inference_ms: float, detection_count: int, gps_fix) -> bool:
    """Send the hardware readings used by the frontend Hardware Monitor."""
    now = datetime.now(timezone.utc).isoformat()
    if config.SENSOR_API_MODE not in {"local", "integration"} and config.API_KEY:
        # The currently deployed Pi API accepts numeric, axis-tagged readings.
        readings = [
            {"sensor_id": config.CAMERA_SENSOR_ID, "value": round(camera_fps, 2), "axis": "FPS", "timestamp": now},
            {"sensor_id": config.CAMERA_SENSOR_ID, "value": round(inference_ms, 2), "axis": "INFER", "timestamp": now},
            {"sensor_id": config.CAMERA_SENSOR_ID, "value": float(detection_count), "axis": "DETECT", "timestamp": now},
        ]
        if gps_fix:
            readings.extend([
                {"sensor_id": config.GPS_SENSOR_ID, "value": gps_fix["latitude"], "axis": "LAT", "timestamp": now},
                {"sensor_id": config.GPS_SENSOR_ID, "value": gps_fix["longitude"], "axis": "LNG", "timestamp": now},
            ])
            if gps_fix.get("satellites") is not None:
                readings.append({"sensor_id": config.GPS_SENSOR_ID, "value": float(gps_fix["satellites"]), "axis": "SAT", "timestamp": now})
        payload = {"device_id": config.DEVICE_ID, "readings": readings}
        url = f"{config.BACKEND_URL}/api/sensors/readings"
        headers = {"X-API-Key": config.API_KEY}
    elif config.SENSOR_API_MODE not in {"legacy", "deployed"} and config.SENSOR_INGEST_TOKEN:
        camera_value = {
            "fps": round(camera_fps, 2),
            "inference_ms": round(inference_ms, 2),
            "detections": detection_count,
            "width": config.CAMERA_WIDTH,
            "height": config.CAMERA_HEIGHT,
        }
        gps_value = {"fix": "NO_FIX"}
        gps_reading = {"name": "GPS", "value": gps_value, "status": "MISSING_DATA", "recorded_at": now}
        if gps_fix:
            gps_value = {
                "lat": gps_fix["latitude"],
                "lng": gps_fix["longitude"],
                "satellites": gps_fix.get("satellites"),
            }
            gps_reading = {
                "name": "GPS",
                "value": gps_value,
                "status": "OK",
                "recorded_at": now,
                "latitude": gps_fix["latitude"],
                "longitude": gps_fix["longitude"],
            }

        payload = {
            "device_id": config.DEVICE_ID,
            "readings": [
                {"name": "Camera", "value": camera_value, "status": "OK", "unit": "fps", "recorded_at": now},
                gps_reading,
            ],
        }
        url = f"{config.BACKEND_URL}/api/integrations/sensors/readings"
        headers = {"X-Sensor-API-Key": config.SENSOR_INGEST_TOKEN}
    else:
        return False

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=5,
        )
        if response.status_code >= 400:
            log.warning("Backend rejected hardware telemetry (%s): %s", response.status_code, response.text[:400])
            return False
        log.debug("Backend accepted hardware telemetry: %s", response.text[:300])
        return True
    except requests.RequestException as exc:
        log.warning("Backend unavailable; hardware telemetry was not sent: %s", exc)
        return False


def detect_crack(result, model_names):
    found = []
    if result.boxes is None:
        return found
    for box in result.boxes:
        cls_id = int(box.cls.item())
        confidence = float(box.conf.item())
        label = str(model_names.get(cls_id, cls_id)).strip()
        if confidence < config.CONFIDENCE_THRESHOLD:
            continue
        if label.lower() not in config.CRACK_CLASS_NAMES:
            continue
        xyxy = [round(float(v), 1) for v in box.xyxy[0].tolist()]
        found.append({"class": label, "confidence": confidence, "box": xyxy})
    return found


def make_event(detection, gps_fix, image_name, inference_ms):
    now = datetime.now(timezone.utc).isoformat()
    confidence = max(d["confidence"] for d in detection)
    event = {
        "schema_version": "1.0",
        "source_event_id": str(uuid4()),
        "detected_at": now,
        "source": config.SOURCE_NAME,
        "device_id": config.DEVICE_ID,
        "defect": "rail_crack",
        "severity": severity_for(confidence),
        "confidence": round(confidence, 4),
        "latitude": gps_fix.get("latitude") if gps_fix else None,
        "longitude": gps_fix.get("longitude") if gps_fix else None,
        "gps_accuracy_m": gps_fix.get("gps_accuracy_m") if gps_fix else None,
        "track": None,
        "chainage": None,
        "boxes": detection,
        "sensor_fusion": {
            "evidence_filename_on_pi": image_name,
            "evidence_upload_status": "UPLOADED_WITH_ALERT_EVENT",
        },
        "model_version": Path(config.MODEL_PATH).name,
        "inference_ms": round(inference_ms, 2),
        "city": config.CITY or None,
    }
    return event


def main():
    if not config.MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {config.MODEL_PATH}. Copy your trained weights to that path."
        )

    log.info("Loading YOLO model: %s", config.MODEL_PATH)
    model = YOLO(str(config.MODEL_PATH))
    motors = MotorController()
    gps = GpsReader()
    frame_lock = threading.Lock()
    latest_frame = {"frame": None, "captured_at": None, "captured_utc": None, "fps": 0.0, "revision": 0}
    camera_stop = threading.Event()

    def capture_frames():
        camera = None
        previous_capture = None
        while not camera_stop.is_set():
            try:
                if camera is None:
                    camera = Picamera2()
                    camera.configure(camera.create_video_configuration(
                        main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT), "format": "RGB888"}
                    ))
                    camera.start()
                    time.sleep(1)
                    log.info("Camera connected")
                frame = camera.capture_array()
                now = time.monotonic()
                fps = 1.0 / max(now - previous_capture, 0.001) if previous_capture else 0.0
                previous_capture = now
                with frame_lock:
                    latest_frame.update(frame=frame, captured_at=now, captured_utc=datetime.now(timezone.utc).isoformat(), fps=fps, revision=latest_frame["revision"] + 1)
                camera_stop.wait(config.CAMERA_CAPTURE_INTERVAL_SECONDS)
            except Exception as exc:
                log.warning("Camera capture failed; retrying in 3s: %s", exc)
                if camera is not None:
                    try:
                        camera.stop()
                        camera.close()
                    except Exception:
                        pass
                camera = None
                camera_stop.wait(3)
        if camera is not None:
            try:
                camera.stop()
                camera.close()
            except Exception:
                log.exception("Camera shutdown failed")

    camera_thread = threading.Thread(target=capture_frames, name="camera-capture", daemon=True)
    camera_thread.start()
    gps_thread = threading.Thread(target=lambda: gps.update_forever(camera_stop), name="gps-reader", daemon=True)
    # GPS reading runs independently so serial timeouts never stall camera inference.
    gps_thread.start()
    telemetry_lock = threading.Lock()
    telemetry_state = {"camera_fps": 0.0, "inference_ms": 0.0, "detection_count": 0}

    def report_telemetry():
        if not (config.SENSOR_INGEST_TOKEN or config.API_KEY):
            log.warning("API_KEY and SENSOR_INGEST_TOKEN are empty; hardware telemetry will not be posted.")
            return
        while not camera_stop.wait(config.TELEMETRY_INTERVAL_SECONDS):
            with telemetry_lock:
                values = dict(telemetry_state)
            send_sensor_telemetry(**values, gps_fix=gps.get_fix())

    telemetry_thread = threading.Thread(target=report_telemetry, name="sensor-uploader", daemon=True)
    telemetry_thread.start()
    publish_lock = threading.Lock()
    publish_latest = {"snapshot": None, "jpeg": None, "revision": 0}

    def publish_frames():
        sent_revision = 0
        while not camera_stop.wait(config.FRAME_UPLOAD_INTERVAL_SECONDS):
            with publish_lock:
                item = dict(publish_latest)
            if item["snapshot"] is None or item["revision"] == sent_revision:
                continue
            if send_latest_frame(item["snapshot"], item["jpeg"]):
                sent_revision = item["revision"]

    publisher_thread = threading.Thread(target=publish_frames, name="frame-uploader", daemon=True)
    publisher_thread.start()
    time.sleep(2)
    log.info("Robot loop started. Ctrl+C to stop.")

    # Prevent one physical crack staying in view from creating dozens of alerts.
    latched = False
    last_processed_revision = 0
    try:
        while not STOP_REQUESTED:
            with frame_lock:
                frame_rgb = latest_frame["frame"]
                camera_fps = latest_frame["fps"]
                captured_at = latest_frame["captured_at"]
                captured_utc = latest_frame["captured_utc"]
                frame_revision = latest_frame["revision"]
            if frame_rgb is None or captured_at is None or time.monotonic() - captured_at > 5:
                time.sleep(0.1)
                continue
            if frame_revision == last_processed_revision:
                time.sleep(0.01)
                continue
            last_processed_revision = frame_revision
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            started = time.perf_counter()
            try:
                prediction = model.predict(
                    source=frame_bgr,
                    imgsz=config.INFERENCE_SIZE,
                    conf=config.CONFIDENCE_THRESHOLD,
                    verbose=False,
                )[0]
                inference_ms = (time.perf_counter() - started) * 1000
                detections = detect_crack(prediction, model.names)
                inference_status = "DETECTION" if detections else "NO_DEFECT"
                annotated_frame = prediction.plot()
            except Exception:
                inference_ms = (time.perf_counter() - started) * 1000
                detections = []
                inference_status = "ERROR"
                annotated_frame = frame_bgr
                log.exception("Model inference failed for camera frame %s", frame_revision)
            with telemetry_lock:
                telemetry_state.update(camera_fps=camera_fps, inference_ms=inference_ms, detection_count=len(detections))

            encoded_ok, encoded = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            lead_detection = max(detections, key=lambda item: item["confidence"]) if detections else None
            snapshot = {
                "device_id": config.DEVICE_ID,
                "camera_status": "CONNECTED",
                "inference_status": inference_status,
                "inference_error": "Inference failed; see Pi service logs." if inference_status == "ERROR" else None,
                "captured_at": captured_utc,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "inference_ms": round(inference_ms, 2),
                "model_name": Path(config.MODEL_PATH).name,
                "model_version": Path(config.MODEL_PATH).name,
                "model_loaded": True,
                "class": lead_detection["class"] if lead_detection else None,
                "defect": lead_detection["class"] if lead_detection else None,
                "confidence": lead_detection["confidence"] if lead_detection else None,
                "severity": severity_for(lead_detection["confidence"]) if lead_detection else None,
                "image_width": int(frame_bgr.shape[1]),
                "image_height": int(frame_bgr.shape[0]),
                "boxes": [{"class": item["class"], "confidence": item["confidence"], "x": item["box"][0], "y": item["box"][1], "width": item["box"][2] - item["box"][0], "height": item["box"][3] - item["box"][1]} for item in detections],
            }
            with publish_lock:
                publish_latest.update(snapshot=snapshot, jpeg=encoded.tobytes() if encoded_ok else None, revision=publish_latest["revision"] + 1)

            if not detections:
                latched = False
                time.sleep(0.02)
                continue

            if latched:
                continue
            latched = True

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_name = f"crack_{timestamp}_{uuid4().hex[:8]}.jpg"
            image_path = config.EVIDENCE_DIR / image_name
            annotated = annotated_frame
            cv2.imwrite(str(image_path), annotated)
            log.warning("Crack candidate: %s; photo saved: %s", detections, image_path)

            # Stop/reverse action is disabled until explicitly configured.
            motors.reverse_briefly()

            gps_fix = gps.get_fix()
            event = make_event(detections, gps_fix, image_name, inference_ms)
            log_event_locally({
                **event,
                "image_path": str(image_path),
                "backend_status": "PENDING_OR_SENT",
            })
            send_event(event, image_path)

    finally:
        motors.close()
        gps.close()
        camera_stop.set()
        camera_thread.join(timeout=5)
        gps_thread.join(timeout=2)
        publisher_thread.join(timeout=5)
        telemetry_thread.join(timeout=5)
        log.info("Robot stopped safely.")


if __name__ == "__main__":
    main()
