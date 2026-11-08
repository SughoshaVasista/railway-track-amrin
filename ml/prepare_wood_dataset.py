"""Convert external YOLO datasets into the single-class 'crack' layout the ml/ scripts expect.

Output layout (works with verify_dataset, train, calibrate, evaluate, infer):
  <output>/data.yaml            names: [crack]
  <output>/train/images|labels
  <output>/valid/images|labels
  <output>/test/images|labels   (only if available)
Every image gets a label file; background images get an empty one.

Modes
  Stage 1 (default): sources keep their own train/valid/test splits.
  Stage 2 mix (--own DIR): val/test come ONLY from your own dataset; all external
      images (every split) and negatives go into train.

Rules applied to external labels
  * Classes named in --keep (case-insensitive) become class 0 'crack'.
  * Images that contain a crack-like class you did NOT keep (e.g. 'Knot with Crack')
    or a class listed in --ambiguous are skipped, so a real crack is never
    turned into a fake background image.
  * All other classes (knots, holes, ...) are dropped, so those regions become background.
  * Polygon labels are converted to bounding boxes.

Examples
  python -m ml.prepare_wood_dataset --source data/raw/wh1-buv5v-v1 --keep crack \\
      --negatives data/raw/vnwoodknot/knot_free --output data/datasets/wood-crack-stage1
  python -m ml.prepare_wood_dataset --own data/datasets/wood-own --source data/raw/wh1-buv5v-v1 \\
      --output data/datasets/wood-stage2
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image, UnidentifiedImageError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MARKER = ".prepared_wood_dataset"
# output split -> accepted folder names inside a source dataset
SPLIT_FOLDERS = {"train": ("train",), "valid": ("valid", "val"), "test": ("test",)}


def read_names(yaml_path: Path) -> list[str]:
    if not yaml_path.is_file():
        raise SystemExit(f"data.yaml not found: {yaml_path}")
    names = yaml.safe_load(yaml_path.read_text(encoding="utf-8")).get("names", [])
    if isinstance(names, dict):
        names = [names[key] for key in sorted(names, key=lambda value: int(value))]
    return [str(name) for name in names]


def find_split(root: Path, split: str) -> tuple[Path, Path] | None:
    for folder in SPLIT_FOLDERS[split]:
        images, labels = root / folder / "images", root / folder / "labels"
        if images.is_dir():
            return images, labels
    return None


def list_images(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def readable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return False


def clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def convert_label_file(label_path: Path, keep_ids: set[int], skip_ids: set[int]) -> list[str] | None:
    """Return remapped label lines, or None when the image must be skipped."""
    lines: list[str] = []
    if not label_path.is_file():
        return lines
    for raw in label_path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if not parts:
            continue
        try:
            class_id = int(float(parts[0]))
            values = [float(v) for v in parts[1:]]
        except ValueError:
            return None
        if class_id in skip_ids:
            return None
        if class_id not in keep_ids:
            continue
        if len(values) == 4:
            xc, yc, w, h = values
            x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
        elif len(values) >= 6 and len(values) % 2 == 0:  # polygon -> bounding box
            xs, ys = values[0::2], values[1::2]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        else:
            return None
        x1, y1, x2, y2 = clamp(x1), clamp(y1), clamp(x2), clamp(y2)
        if x2 - x1 <= 1e-4 or y2 - y1 <= 1e-4:
            continue
        lines.append(f"0 {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
    return lines


class Writer:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.images: Counter = Counter()
        self.boxes: Counter = Counter()
        self.empty: Counter = Counter()

    def emit(self, split: str, name: str, image: Path, lines: list[str]) -> None:
        image_dir = self.output / split / "images"
        label_dir = self.output / split / "labels"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        target = image_dir / f"{name}{image.suffix.lower()}"
        shutil.copy2(image, target)
        (label_dir / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        self.images[split] += 1
        self.boxes[split] += len(lines)
        if not lines:
            self.empty[split] += 1


def process_source(source: Path, tag: str, keep: set[str], extra_skip: set[str], writer: Writer,
                   force_train: bool, skipped: Counter) -> None:
    names = read_names(source / "data.yaml")
    lowered = [name.strip().lower() for name in names]
    keep_ids = {i for i, name in enumerate(lowered) if name in keep}
    if not keep_ids:
        raise SystemExit(f"{source}: none of {sorted(keep)} found in classes {names}")
    skip_ids = {i for i, name in enumerate(lowered) if i not in keep_ids and ("crack" in name or name in extra_skip)}
    print(f"{tag}: classes={names} | kept={[names[i] for i in sorted(keep_ids)]} | "
          f"images with these are skipped={[names[i] for i in sorted(skip_ids)]}")
    found_any = False
    for split in SPLIT_FOLDERS:
        located = find_split(source, split)
        if not located:
            continue
        found_any = True
        image_dir, label_dir = located
        for image in list_images(image_dir):
            if not readable(image):
                skipped["unreadable"] += 1
                continue
            label_path = label_dir / image.relative_to(image_dir).with_suffix(".txt")
            lines = convert_label_file(label_path, keep_ids, skip_ids)
            if lines is None:
                skipped["ambiguous_or_malformed"] += 1
                continue
            stem = "_".join(image.relative_to(image_dir).with_suffix("").parts)
            writer.emit("train" if force_train else split, f"{tag}_{split}_{stem}", image, lines)
    if not found_any:
        raise SystemExit(f"{source}: no train/valid/test folders with an images/ directory were found")


def process_own(own: Path, writer: Writer) -> None:
    names = [name.strip().lower() for name in read_names(own / "data.yaml")]
    if names != ["crack"]:
        raise SystemExit(f"--own dataset must have exactly one class named 'crack', found {names}")
    for split in SPLIT_FOLDERS:
        located = find_split(own, split)
        if not located:
            continue
        image_dir, label_dir = located
        for image in list_images(image_dir):
            label_path = label_dir / image.relative_to(image_dir).with_suffix(".txt")
            text = label_path.read_text(encoding="utf-8") if label_path.is_file() else ""
            lines = [line for line in text.splitlines() if line.strip()]
            stem = "_".join(image.relative_to(image_dir).with_suffix("").parts)
            writer.emit(split, f"own_{split}_{stem}", image, lines)


def add_negatives(dirs: list[Path], writer: Writer, limit: int | None, val_fraction: float,
                  allow_val: bool, rng: random.Random) -> int:
    pool: list[tuple[str, Path]] = []
    for index, directory in enumerate(dirs):
        if not directory.is_dir():
            raise SystemExit(f"Negatives directory not found: {directory}")
        pool.extend((f"neg{index}", path) for path in list_images(directory))
    rng.shuffle(pool)
    if limit is not None:
        pool = pool[:limit]
    added = 0
    for tag, image in pool:
        if not readable(image):
            continue
        split = "valid" if allow_val and rng.random() < val_fraction else "train"
        writer.emit(split, f"{tag}_{added:05d}_{image.stem}", image, [])
        added += 1
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a single-class 'crack' dataset from external YOLO datasets.")
    parser.add_argument("--source", type=Path, nargs="*", default=[], help="YOLO dataset folders (contain data.yaml).")
    parser.add_argument("--own", type=Path, default=None, help="Your own single-class dataset; its val/test are kept.")
    parser.add_argument("--negatives", type=Path, nargs="*", default=[], help="Folders of crack-free images (empty labels).")
    parser.add_argument("--keep", nargs="+", default=["crack"], help="Class names to map to 'crack'.")
    parser.add_argument("--ambiguous", nargs="*", default=[], help="Extra class names whose images are skipped.")
    parser.add_argument("--all-to-train", action="store_true", help="Put every external split into train (implied by --own).")
    parser.add_argument("--max-negatives", type=int, default=None)
    parser.add_argument("--val-negative-fraction", type=float, default=0.1, help="Stage 1 only: share of negatives sent to valid.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/datasets/wood-crack-stage1"))
    parser.add_argument("--force", action="store_true", help="Replace an output folder created by this script.")
    args = parser.parse_args()

    if not args.source and not args.own:
        raise SystemExit("Give at least one --source or --own dataset.")
    if not 0 <= args.val_negative_fraction <= 1:
        raise SystemExit("--val-negative-fraction must be in [0, 1].")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        if args.force and (output / MARKER).is_file():
            shutil.rmtree(output)
        else:
            raise SystemExit(f"Output exists: {output}. Use --force (only works on folders this script created).")
    output.mkdir(parents=True, exist_ok=True)
    (output / MARKER).write_text("created by ml.prepare_wood_dataset\n", encoding="utf-8")

    rng = random.Random(args.seed)
    writer = Writer(output)
    skipped: Counter = Counter()
    keep = {name.strip().lower() for name in args.keep}
    extra_skip = {name.strip().lower() for name in args.ambiguous}
    force_train = bool(args.own) or args.all_to_train

    if args.own:
        process_own(args.own.resolve(), writer)
    for index, source in enumerate(args.source):
        process_source(source.resolve(), f"s{index}", keep, extra_skip, writer, force_train, skipped)
    negatives_added = 0
    if args.negatives:
        negatives_added = add_negatives(
            [p.resolve() for p in args.negatives], writer, args.max_negatives,
            args.val_negative_fraction, allow_val=not force_train, rng=rng,
        )

    if not writer.images["train"]:
        raise SystemExit("No training images were produced; check class names and paths.")
    if not writer.images["valid"]:
        raise SystemExit("No validation images were produced. Use sources with a valid/ split, or pass --own.")

    config = {"path": str(output), "train": "train/images", "val": "valid/images"}
    if writer.images["test"]:
        config["test"] = "test/images"
    config["nc"] = 1
    config["names"] = ["crack"]
    (output / "data.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    summary = {
        "sources": [str(p) for p in args.source], "own": str(args.own) if args.own else None,
        "negatives": [str(p) for p in args.negatives], "kept_classes": sorted(keep),
        "images": dict(writer.images), "boxes": dict(writer.boxes),
        "background_images": dict(writer.empty), "skipped": dict(skipped),
        "note": "External data is for pretraining; report each source and its licence.",
    }
    (output / "dataset_sources.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    for split in SPLIT_FOLDERS:
        if writer.images[split]:
            print(f"{split}: {writer.images[split]} images | {writer.boxes[split]} crack boxes | "
                  f"{writer.empty[split]} background")
    if skipped:
        print("Skipped:", dict(skipped))
    if negatives_added:
        print(f"Negatives added: {negatives_added}")
    print(f"Dataset config: {output / 'data.yaml'}")
    print(f"Next: python -m ml.verify_dataset --data \"{output / 'data.yaml'}\"")


if __name__ == "__main__":
    main()
