from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import Lock
from time import perf_counter



class InvalidCameraFrame(ValueError):
    pass


@dataclass(frozen=True)
class VisionResult:
    boxes: list[dict]
    image_width: int
    image_height: int
    inference_ms: float
    annotated_jpeg: bytes


_model_lock = Lock()
_inference_lock = Lock()
_model_path: Path | None = None
_model = None


def _get_model(path: Path):
    global _model_path, _model
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Local ML model was not found: {resolved}")
    if _model is not None and _model_path == resolved:
        return _model
    with _model_lock:
        if _model is None or _model_path != resolved:
            from ultralytics import YOLO

            _model = YOLO(str(resolved), task="detect")
            _model_path = resolved
    return _model


def infer_camera_jpeg(
    image_bytes: bytes,
    model_path: str,
    confidence: float,
    iou: float,
    image_size: int,
) -> VisionResult:
    import numpy as np
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.format != "JPEG":
                raise InvalidCameraFrame("Camera image must be a JPEG")
            width, height = source.size
            if width < 1 or height < 1 or width * height > 20_000_000:
                raise InvalidCameraFrame("Camera image dimensions are not supported")
            frame = np.asarray(source.convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidCameraFrame("Camera upload is not a valid JPEG image") from exc

    with _inference_lock:
        model = _get_model(Path(model_path))
        started = perf_counter()
        result = model.predict(
            source=frame,
            conf=confidence,
            iou=iou,
            imgsz=image_size,
            device="cpu",
            verbose=False,
        )[0]
        inference_ms = (perf_counter() - started) * 1000

    boxes: list[dict] = []
    if result.boxes is not None:
        for detected in result.boxes:
            class_id = int(detected.cls[0].item())
            coords = [float(value) for value in detected.xyxy[0].tolist()]
            boxes.append({
                "class": str(result.names.get(class_id, class_id)),
                "confidence": float(detected.conf[0].item()),
                "box": coords,
            })

    annotated_rgb = result.plot()[:, :, ::-1]
    output = BytesIO()
    Image.fromarray(annotated_rgb).save(output, format="JPEG", quality=88, optimize=True)
    return VisionResult(
        boxes=boxes,
        image_width=width,
        image_height=height,
        inference_ms=round(inference_ms, 2),
        annotated_jpeg=output.getvalue(),
    )
