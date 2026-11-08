"""Download external wood-defect datasets into data/raw/ for Stage 1 pretraining.

Sub-commands
  roboflow  Download a Roboflow Universe project in YOLOv8 format (needs ROBOFLOW_API_KEY).
  kaggle    Download a Kaggle dataset via kagglehub (pip install kagglehub; needs Kaggle login).
  zenodo    List or download files of a Zenodo record (no account needed).
  extract   Unpack a zip/tar you downloaded manually (e.g. Mendeley Data, which needs a browser).

Examples (run from the repo root)
  python -m ml.download_wood_datasets roboflow --workspace wh1 --project=-buv5v --version 1
  python -m ml.download_wood_datasets kaggle --slug itiresearch/wood-anomaly-detection-one-class-classification
  python -m ml.download_wood_datasets zenodo --record 4694695                  # list files only
  python -m ml.download_wood_datasets zenodo --record 4694695 --match Bouding  # download matching files
  python -m ml.download_wood_datasets extract --archive VNWoodKnot.zip --destination data/raw/vnwoodknot

Check every dataset's licence on its page and cite it in your report.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAW_ROOT = Path("data/raw")


def safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._" else "-" for ch in value).strip("-")
    return cleaned or "dataset"


def cmd_roboflow(args: argparse.Namespace) -> None:
    api_key = os.getenv("ROBOFLOW_API_KEY")
    if not api_key:
        raise SystemExit("Set ROBOFLOW_API_KEY in your environment or .env file first.")
    try:
        from roboflow import Roboflow
    except ImportError as exc:
        raise SystemExit("Install ML dependencies first: pip install -r ml/requirements.txt") from exc
    destination = (args.destination or RAW_ROOT / f"{safe_name(args.workspace)}-{safe_name(args.project)}-v{args.version}").resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        project = Roboflow(api_key=api_key).workspace(args.workspace).project(args.project)
        project.version(args.version).download("yolov8", location=str(destination))
    except Exception as exc:  # roboflow raises many different exception types
        raise SystemExit(
            f"Roboflow download failed: {exc}\n"
            "Open the project page, check the workspace, project slug and the latest version number, "
            "or download the YOLOv8 export manually and unzip it into data/raw/."
        ) from exc
    if not (destination / "data.yaml").is_file():
        raise SystemExit(f"Export finished but data.yaml is missing in {destination}")
    print(f"Downloaded to {destination}")
    print("Next: python -m ml.prepare_wood_dataset --source", destination)


def cmd_kaggle(args: argparse.Namespace) -> None:
    try:
        import kagglehub
    except ImportError as exc:
        raise SystemExit("Install it with: pip install kagglehub (and sign in to Kaggle).") from exc
    cached = Path(kagglehub.dataset_download(args.slug))
    destination = (args.destination or RAW_ROOT / safe_name(args.slug.split("/")[-1])).resolve()
    if destination.exists():
        raise SystemExit(f"Destination already exists: {destination}")
    shutil.copytree(cached, destination)
    print(f"Downloaded to {destination}")
    print("Inspect the folder layout: many Kaggle sets have no box labels (classification or anomaly data).")


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "wood-dataset-downloader"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def cmd_zenodo(args: argparse.Namespace) -> None:
    meta = fetch_json(f"https://zenodo.org/api/records/{args.record}")
    files = meta.get("files", [])
    if not files:
        raise SystemExit("No files listed for that Zenodo record.")
    entries = []
    for item in files:
        name = item.get("key") or item.get("filename") or ""
        link = (item.get("links") or {}).get("self") or (item.get("links") or {}).get("download")
        entries.append((name, int(item.get("size", 0)), link))
    print(f"{meta.get('metadata', {}).get('title', 'Zenodo record')} ({len(entries)} files)")
    for name, size, _ in entries:
        print(f"  {size / 1e6:10.1f} MB  {name}")
    if not args.match:
        print("Pass --match <text> to download files whose name contains that text.")
        return
    selected = [entry for entry in entries if args.match.lower() in entry[0].lower()]
    if not selected:
        raise SystemExit(f"No file name contains {args.match!r}.")
    total = sum(size for _, size, _ in selected)
    print(f"Selected {len(selected)} file(s), {total / 1e9:.2f} GB total.")
    if total > 2e9 and not args.yes:
        raise SystemExit("That is over 2 GB. Re-run with --yes if you really want it.")
    destination = (args.destination or RAW_ROOT / f"zenodo-{args.record}").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for name, _, link in selected:
        if not link:
            print(f"Skipping {name}: no download link in API response")
            continue
        target = destination / name
        print(f"Downloading {name} ...")
        request = urllib.request.Request(link, headers={"User-Agent": "wood-dataset-downloader"})
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
    print(f"Saved to {destination}")
    print("Check the label format (VOC XML, JSON, or YOLO txt) before converting; this script does not guess it.")


def cmd_extract(args: argparse.Namespace) -> None:
    archive = args.archive.resolve()
    if not archive.is_file():
        raise SystemExit(f"Archive not found: {archive}")
    destination = (args.destination or RAW_ROOT / safe_name(archive.stem)).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(archive), str(destination))
    print(f"Extracted to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download wood-defect datasets for Stage 1 pretraining.")
    sub = parser.add_subparsers(dest="command", required=True)

    rf = sub.add_parser("roboflow", help="Roboflow Universe project, YOLOv8 format")
    rf.add_argument("--workspace", default="wh1")
    rf.add_argument("--project", default="-buv5v", help="Project slug; use --project=-buv5v because it starts with a dash.")
    rf.add_argument("--version", type=int, default=1, help="Check the project page for the latest version number.")
    rf.add_argument("--destination", type=Path, default=None)
    rf.set_defaults(func=cmd_roboflow)

    kg = sub.add_parser("kaggle", help="Kaggle dataset via kagglehub")
    kg.add_argument("--slug", default="itiresearch/wood-anomaly-detection-one-class-classification")
    kg.add_argument("--destination", type=Path, default=None)
    kg.set_defaults(func=cmd_kaggle)

    zn = sub.add_parser("zenodo", help="List or download files from a Zenodo record")
    zn.add_argument("--record", default="4694695")
    zn.add_argument("--match", default=None, help="Download only files whose name contains this text.")
    zn.add_argument("--yes", action="store_true", help="Allow downloads over 2 GB.")
    zn.add_argument("--destination", type=Path, default=None)
    zn.set_defaults(func=cmd_zenodo)

    ex = sub.add_parser("extract", help="Unpack a manually downloaded archive")
    ex.add_argument("--archive", type=Path, required=True)
    ex.add_argument("--destination", type=Path, default=None)
    ex.set_defaults(func=cmd_extract)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
