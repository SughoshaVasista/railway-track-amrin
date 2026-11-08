"""Export the public Hugging Face wood-surface dataset as single-class YOLO data.

Crack boxes are retained. Images marked ``knot_with_crack`` are excluded because
their provided boxes cover knots rather than the crack itself. Other defect
classes are retained as background examples to teach the detector hard negatives.
The source dataset is wood lumber, not railway sleepers; validate on ESP32-CAM
images before deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from datasets import load_dataset
from PIL import Image


REPO_ID = "iluvvatar/wood_surface_defects"
SPLITS = ("train", "val", "test")


def split_for(identifier: object) -> str:
    bucket = int.from_bytes(hashlib.sha256(str(identifier).encode()).digest()[:4], "big") % 10
    return "val" if bucket == 0 else "test" if bucket == 1 else "train"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/datasets/wood-surface-defects-hf"))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Output directory is not empty: {output}")

    dataset = load_dataset(REPO_ID, split="train")
    for split in SPLITS:
        (output / split / "images").mkdir(parents=True, exist_ok=True)
        (output / split / "labels").mkdir(parents=True, exist_ok=True)

    stats = {split: {"images": 0, "crack_images": 0, "crack_boxes": 0} for split in SPLITS}
    excluded_knot_crack = 0
    for row_index, row in enumerate(dataset, start=1):
        objects = row.get("objects") or []
        labels = [str(item.get("label", "")).strip().lower().replace(" ", "_") for item in objects]
        if "knot_with_crack" in labels:
            excluded_knot_crack += 1
            continue

        split = split_for(row.get("id", row["image"].get("path", "row")))
        image = row["image"]
        if isinstance(image, dict):
            image_path_or_bytes = image.get("path")
            image = (
                Image.open(image_path_or_bytes)
                if image_path_or_bytes
                else Image.open(io.BytesIO(image["bytes"]))
            )
        image = image.convert("RGB")
        filename = f"{row.get('id', stats[split]['images']):s}.jpg" if isinstance(row.get("id"), str) else f"{row.get('id', stats[split]['images']):012d}.jpg"
        image.save(output / split / "images" / filename, format="JPEG", quality=95)

        yolo_rows = []
        for item in objects:
            label = str(item.get("label", "")).strip().lower().replace(" ", "_")
            if label != "crack":
                continue
            x, y, width, height = map(float, item["bb"])
            if not all(0 <= value <= 1 for value in (x, y, width, height)) or width <= 0 or height <= 0:
                raise ValueError(f"Invalid normalized box for image {filename}: {item['bb']}")
            yolo_rows.append(f"0 {x:.7f} {y:.7f} {width:.7f} {height:.7f}")

        (output / split / "labels" / f"{Path(filename).stem}.txt").write_text(
            "\n".join(yolo_rows) + ("\n" if yolo_rows else ""), encoding="utf-8"
        )
        stats[split]["images"] += 1
        stats[split]["crack_images"] += bool(yolo_rows)
        stats[split]["crack_boxes"] += len(yolo_rows)
        if row_index % 1000 == 0:
            print(f"Converted {row_index}/{len(dataset)} source rows", flush=True)

    data_yaml = {
        "path": str(output),
        "train": "train/images",
        "val": "val/images",
        "test": "test/images",
        "names": ["crack"],
        "nc": 1,
    }
    import yaml

    (output / "data.yaml").write_text(yaml.safe_dump(data_yaml, sort_keys=False), encoding="utf-8")
    (output / "SOURCE.txt").write_text(
        "Source: iluvvatar/wood_surface_defects on Hugging Face, CC BY 4.0.\n"
        "Based on Kodytek, Bodzas and Bilik (2022), F1000Research 10:581, version 2.\n"
        "DOI: https://doi.org/10.12688/f1000research.52903.2\n"
        "This is industrial sawn timber, not railway sleepers.\n",
        encoding="utf-8",
    )
    (output / "conversion_stats.json").write_text(
        json.dumps({"source": REPO_ID, "excluded_knot_with_crack_images": excluded_knot_crack, "splits": stats}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "excluded_knot_with_crack_images": excluded_knot_crack, "splits": stats}, indent=2))


if __name__ == "__main__":
    main()
