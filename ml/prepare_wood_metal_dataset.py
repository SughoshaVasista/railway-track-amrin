"""Combine prepared wood and railway crack datasets into a two-class YOLO set.

The source folders must already be in YOLO detection format, with one crack
class each. Source files are copied; the originals are never modified.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SPLITS = {"train": ("train",), "val": ("val", "valid"), "test": ("test",)}


def read_names(config: dict) -> list[str]:
    names = config.get("names", [])
    if isinstance(names, dict):
        names = [names[key] for key in sorted(names, key=lambda item: int(item))]
    return [str(name).strip().lower() for name in names]


def resolve_root(config: dict, yaml_path: Path) -> Path:
    root = Path(config.get("path", yaml_path.parent))
    return root.resolve() if root.is_absolute() else (yaml_path.parent / root).resolve()


def source_split(root: Path, config: dict, split: str) -> tuple[Path, Path] | None:
    value = config.get(split)
    candidates: list[Path] = []
    if value:
        image_dir = Path(str(value))
        candidates.append(image_dir if image_dir.is_absolute() else root / image_dir)
    for alias in SPLITS[split]:
        candidates.append(root / alias / "images")
    image_dir = next((path for path in candidates if path.is_dir()), None)
    if image_dir is None:
        return None

    if image_dir.name == "images":
        labels_dir = image_dir.parent / "labels"
    elif image_dir.parent.name == "images":
        labels_dir = image_dir.parent.parent / "labels" / image_dir.name
    else:
        labels_dir = image_dir / "labels"
    return image_dir, labels_dir


def map_labels(label_path: Path, source_class_id: int, target_class_id: int) -> list[str]:
    if not label_path.is_file():
        raise SystemExit(f"Missing label file: {label_path}")
    mapped = []
    for line_number, raw in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        parts = raw.split()
        if not parts:
            continue
        try:
            class_id = int(parts[0])
            values = [float(value) for value in parts[1:]]
        except ValueError as exc:
            raise SystemExit(f"Invalid label at {label_path}:{line_number}") from exc
        if class_id != source_class_id:
            raise SystemExit(
                f"Unexpected class id {class_id} at {label_path}:{line_number}; "
                f"expected {source_class_id}"
            )
        if len(values) != 4 or not all(0 <= value <= 1 for value in values):
            raise SystemExit(f"Invalid YOLO box at {label_path}:{line_number}")
        if values[2] == 0 or values[3] == 0:
            raise SystemExit(f"Zero-area box at {label_path}:{line_number}")
        mapped.append(f"{target_class_id} " + " ".join(f"{value:.7f}" for value in values))
    return mapped


def copy_source(source: Path, target: Path, expected_names: set[str], target_class_id: int, tag: str) -> dict[str, int]:
    yaml_path = source / "data.yaml"
    if not yaml_path.is_file():
        raise SystemExit(f"Dataset config not found: {yaml_path}")
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    names = read_names(config)
    matching = [index for index, name in enumerate(names) if name in expected_names]
    if len(matching) != 1 or len(names) != 1:
        raise SystemExit(
            f"{source}: expected one class named in {sorted(expected_names)}, found {names}"
        )
    root = resolve_root(config, yaml_path)
    counts = {split: 0 for split in SPLITS}
    for split in SPLITS:
        located = source_split(root, config, split)
        if located is None:
            continue
        image_dir, labels_dir = located
        for image in sorted(path for path in image_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES):
            relative = image.relative_to(image_dir)
            label = labels_dir / relative.with_suffix(".txt")
            rows = map_labels(label, matching[0], target_class_id)
            filename = f"{tag}_{split}_{relative.as_posix().replace('/', '_')}"
            target_image_dir = target / "images" / split
            target_label_dir = target / "labels" / split
            target_image_dir.mkdir(parents=True, exist_ok=True)
            target_label_dir.mkdir(parents=True, exist_ok=True)
            destination = target_image_dir / filename
            if destination.exists():
                raise SystemExit(f"Refusing to overwrite existing file: {destination}")
            shutil.copy2(image, destination)
            (target_label_dir / Path(filename).with_suffix(".txt")).write_text(
                "\n".join(rows) + ("\n" if rows else ""), encoding="utf-8"
            )
            counts[split] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wood", type=Path, default=Path("data/datasets/wood-crack-stage1"))
    parser.add_argument("--metal", type=Path, default=Path("data/datasets/railway-crack-retrain-v1"))
    parser.add_argument("--output", type=Path, default=Path("data/datasets/wood-metal-cracks"))
    args = parser.parse_args()

    output = args.output.resolve()
    if any(output.rglob("*.jpg")) or any(output.rglob("*.jpeg")) or any(output.rglob("*.png")):
        raise SystemExit(f"Output already contains images; refusing to overwrite: {output}")
    for split in SPLITS:
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    wood_counts = copy_source(args.wood.resolve(), output, {"crack"}, 0, "wood")
    metal_counts = copy_source(
        args.metal.resolve(), output, {"railway-cracks", "metal_crack", "crack"}, 1, "metal"
    )
    data = {
        # Ultralytics resolves relative `path` against its process cwd rather
        # than the YAML's directory, so emit the resolved dataset root.
        "path": output.as_posix(),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {0: "wood_crack", 1: "metal_crack"},
    }
    (output / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"Wood images by split: {wood_counts}")
    print(f"Metal images by split: {metal_counts}")
    print(f"Combined dataset: {output}")


if __name__ == "__main__":
    main()
