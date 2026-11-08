from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image, UnidentifiedImageError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def dataset_root(data: dict, yaml_path: Path) -> Path:
    root = Path(data.get("path", yaml_path.parent))
    return root if root.is_absolute() else (yaml_path.parent / root).resolve()


def find_images(root: Path, split: str, split_value: str) -> tuple[Path | None, list[Path]]:
    declared = Path(split_value)
    image_dir = declared if declared.is_absolute() else root / declared
    if not image_dir.is_dir():
        # Common exports use train/valid/test folders regardless of yaml path spelling.
        alias = "valid" if split == "val" else split
        image_dir = root / alias / "images"
    if not image_dir.is_dir():
        return None, []
    return image_dir, sorted(path for path in image_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check YOLO object-detection dataset files and labels.")
    parser.add_argument("--data", type=Path, default=Path("data/datasets/railway-crack-detection-15/data.yaml"))
    parser.add_argument("--strict", action="store_true", help="Treat images without labels as an error.")
    args = parser.parse_args()
    yaml_path = args.data.resolve()
    if not yaml_path.is_file():
        raise SystemExit(f"Dataset YAML not found: {yaml_path}. Download the dataset first.")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    names = data.get("names", [])
    if isinstance(names, dict):
        names = [names[key] for key in sorted(names, key=lambda value: int(value))]
    if not names:
        raise SystemExit("data.yaml must define class names")
    root = dataset_root(data, yaml_path)
    class_counts: dict[str, Counter] = {}
    errors, warnings = [], []
    total_images = 0
    for split in ("train", "val", "test"):
        if split not in data:
            if split == "test":
                warnings.append("No test split was defined in data.yaml")
            continue
        image_dir, images = find_images(root, split, str(data[split]))
        if image_dir is None:
            errors.append(f"{split}: image folder was not found ({data[split]})")
            continue
        counts = Counter()
        corrupt = 0
        missing_labels = 0
        invalid_labels = 0
        if image_dir.name == "images":
            labels_dir = image_dir.parent / "labels"
        elif image_dir.parent.name == "images":
            labels_dir = image_dir.parent.parent / "labels" / image_dir.name
        else:
            labels_dir = image_dir / "labels"
        for image_path in images:
            total_images += 1
            try:
                with Image.open(image_path) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                corrupt += 1
                errors.append(f"Unreadable image: {image_path}")
                continue
            label_path = labels_dir / image_path.relative_to(image_dir).with_suffix(".txt")
            if not label_path.is_file():
                missing_labels += 1
                warnings.append(f"{split}: image has no label file: {image_path.name}")
                continue
            for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    invalid_labels += 1
                    errors.append(f"Malformed label {label_path}:{line_number}")
                    continue
                try:
                    class_id = int(float(parts[0]))
                    x, y, width, height = map(float, parts[1:])
                    if not 0 <= class_id < len(names) or not all(0 <= value <= 1 for value in (x, y, width, height)) or width == 0 or height == 0:
                        raise ValueError("class or normalized box coordinate is out of range")
                    counts[str(names[class_id])] += 1
                except ValueError as exc:
                    invalid_labels += 1
                    errors.append(f"Invalid label {label_path}:{line_number} ({exc})")
        class_counts[split] = counts
        print(f"{split}: {len(images)} images | {sum(counts.values())} boxes | {corrupt} corrupt | {missing_labels} unlabeled | {invalid_labels} invalid labels")
        print("  classes:", dict(counts))
    print(f"Dataset root: {root}")
    print(f"Classes ({len(names)}): {names}")
    print(f"Total images: {total_images}")
    for warning in warnings[:20]:
        print("WARNING:", warning)
    if len(warnings) > 20:
        print(f"WARNING: plus {len(warnings) - 20} more warnings")
    for error in errors:
        print("ERROR:", error)
    if args.strict and warnings:
        raise SystemExit(1)
    if errors:
        raise SystemExit(1)
    print("Dataset verification completed with no corrupt or malformed files.")


if __name__ == "__main__":
    main()

