import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ML_INGEST_TOKEN = os.getenv("ML_INGEST_TOKEN", "")
SENSOR_INGEST_TOKEN = os.getenv("SENSOR_INGEST_TOKEN", "")
API_KEY = os.getenv("API_KEY", "")
SENSOR_API_MODE = os.getenv("SENSOR_API_MODE", "auto").strip().lower()
TELEMETRY_INTERVAL_SECONDS = max(1.0, float(os.getenv("TELEMETRY_INTERVAL_SECONDS", "5")))
DEVICE_ID = os.getenv("DEVICE_ID", "railsafe-pi-01")
CAMERA_SENSOR_ID = os.getenv("CAMERA_SENSOR_ID", f"{DEVICE_ID}-camera")
GPS_SENSOR_ID = os.getenv("GPS_SENSOR_ID", f"{DEVICE_ID}-gps")
SOURCE_NAME = os.getenv("SOURCE_NAME", "railsafe-pi")
CITY = os.getenv("CITY", "")

DEFAULT_MODEL_PATH = BASE_DIR.parent / "models" / "best.pt"
if not DEFAULT_MODEL_PATH.is_file():
    DEFAULT_MODEL_PATH = BASE_DIR / "models" / "best.pt"
MODEL_PATH = Path(os.getenv("MODEL_PATH", str(DEFAULT_MODEL_PATH))).expanduser()
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
CAMERA_CAPTURE_INTERVAL_SECONDS = max(0.05, float(os.getenv("CAMERA_CAPTURE_INTERVAL_SECONDS", "0.2")))
FRAME_UPLOAD_INTERVAL_SECONDS = max(1.0, float(os.getenv("FRAME_UPLOAD_INTERVAL_SECONDS", "3")))
INFERENCE_SIZE = int(os.getenv("INFERENCE_SIZE", "416"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))
CRACK_CLASS_NAMES = {
    name.strip().lower()
    for name in os.getenv("CRACK_CLASS_NAMES", "crack,rail_crack,rail crack").split(",")
    if name.strip()
}
SEVERITY_S3_CONFIDENCE = float(os.getenv("SEVERITY_S3_CONFIDENCE", "0.85"))
SEVERITY_S2_CONFIDENCE = float(os.getenv("SEVERITY_S2_CONFIDENCE", "0.65"))

# Use only after verifying the exact motor driver, wiring, and pin conflicts.
MOTOR_ENABLED = os.getenv("MOTOR_ENABLED", "false").lower() == "true"
MOTOR_DRIVER = os.getenv("MOTOR_DRIVER", "l298n").lower()
MOTOR_LEFT_IN1 = int(os.getenv("MOTOR_LEFT_IN1", "12"))
MOTOR_LEFT_IN2 = int(os.getenv("MOTOR_LEFT_IN2", "16"))
MOTOR_RIGHT_IN1 = int(os.getenv("MOTOR_RIGHT_IN1", "20"))
MOTOR_RIGHT_IN2 = int(os.getenv("MOTOR_RIGHT_IN2", "21"))
MOTOR_REVERSE_SECONDS = float(os.getenv("MOTOR_REVERSE_SECONDS", "0.8"))

GPS_PORT = os.getenv("GPS_PORT", "/dev/serial0")
GPS_BAUD = int(os.getenv("GPS_BAUD", "9600"))
GPS_READ_TIMEOUT = float(os.getenv("GPS_READ_TIMEOUT", "0.2"))
GPS_MAX_AGE_SECONDS = float(os.getenv("GPS_MAX_AGE_SECONDS", "10"))

EVIDENCE_DIR = BASE_DIR / "data" / "evidence"
PENDING_DIR = BASE_DIR / "data" / "pending"
EVENT_LOG = BASE_DIR / "data" / "events.jsonl"
LOG_DIR = BASE_DIR / "logs"

for directory in (EVIDENCE_DIR, PENDING_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)
