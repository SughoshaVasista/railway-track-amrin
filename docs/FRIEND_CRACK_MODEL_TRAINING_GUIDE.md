# RailSafe crack model training handoff

This guide covers continuing **crack detection only** on the wooden tabletop track and metal rail examples. It deliberately excludes MEGA setup/download; the project owner and friend will handle dataset transfer separately.

## Current project state

- The detector has one class: `railway-cracks`. It should detect cracks on wood and metal without classifying the material.
- Dataset config: `data/datasets/railway-crack-retrain-v1/data.yaml`.
- Four photos of the tabletop wooden model were added to `train/images` with empty label files. These are normal-track/wood-grain negatives, not positive wooden-crack examples. Add verified, labeled wooden cracks before expecting reliable wooden crack detection.
- Existing trained checkpoint: `runs/detect/runs/detect/rail-crack-v1/weights/best.pt`.
- The recent held-out test run evaluated 38 images containing 18 labeled boxes: precision 0.609, recall 0.778, mAP@50 0.680, mAP@50–95 0.359. This small test set makes the metrics uncertain; it also does not establish performance on real wooden cracks.
- The backend `.env` currently points at that checkpoint. The backend performs inference on CPU; the NVIDIA GPU is used for training.

## 1. Prepare the project on the training PC

Copy/clone the project and the dataset into the same expected layout. Keep the dataset config and split folders together. In PowerShell, change to the project root:

```powershell
Set-Location "C:\path\to\RailSafe-Main_project-main"
```

Confirm the GPU and Python environment are available:

```powershell
.\.venv-training\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
```

If the project’s training environment is missing, create it and install the training requirements. Install a CUDA-enabled PyTorch build appropriate for the computer’s NVIDIA driver before training; verify `torch.cuda.is_available()` returns `True`.

```powershell
py -3.11 -m venv .venv-training
.\.venv-training\Scripts\python.exe -m pip install --upgrade pip
.\.venv-training\Scripts\python.exe -m pip install -r ml\requirements.txt
```

## 2. Add and label images

Put images into the correct split’s `images` folder and a same-basename YOLO `.txt` file in its `labels` folder:

```text
data/datasets/railway-crack-retrain-v1/
  train/images/   train/labels/
  val/images/     val/labels/
  test/images/    test/labels/
```

Each positive crack box has one line in YOLO detection format:

```text
0 x_center y_center width height
```

Coordinates are normalized from 0 to 1. Use class ID `0` (`railway-cracks`) for every crack, regardless of whether it is on wood or metal. An empty label file means the image was inspected and contains no crack. Do not use an empty file for an image whose crack annotation is missing or uncertain.

Include real positive cracks from the project’s wooden model and metal samples, plus clean wood, grain, joints, shadows, and intact rail negatives. Use varied camera distances, angles, lighting, and crack sizes. Keep images from the same physical crack or capture session in only one split. Never move test images into training after checking test results.

Public sources previously identified (inspect labels and license, and convert before mixing): [Roboflow wood crack set](https://universe.roboflow.com/seunghwan-u9ndk/wood-crack) is an 80-image segmentation dataset, so its masks need conversion to boxes; the [Zenodo wood-defect record](https://zenodo.org/records/4694695) has annotations but its images are a separate, very large download; the [wooden sleeper paper](https://arxiv.org/abs/2305.05103) does not expose a direct dataset download on its paper page. Generic board imagery is supplementary and may not match the project’s tabletop model.

## 3. Verify before training

```powershell
.\.venv-training\Scripts\python.exe -m ml.verify_dataset `
  --data data/datasets/railway-crack-retrain-v1/data.yaml
```

Check that train/val/test image and box counts are nonzero and that each positive label uses class `0`. The four existing model photos should count as unlabeled negatives (images with empty label files), not crack boxes. Do not train if the dataset reports missing images, corrupt files, or invalid labels.

## 4. Continue from the current best model

Run from the project root. This fine-tunes the checkpoint weights; it is not an optimizer-state resume.

```powershell
.\.venv-training\Scripts\python.exe -m ml.train `
  --data data/datasets/railway-crack-retrain-v1/data.yaml `
  --model runs/detect/runs/detect/rail-crack-v1/weights/best.pt `
  --epochs 50 `
  --imgsz 640 `
  --batch 4 `
  --device 0 `
  --project runs/detect `
  --name rail-crack-v2
```

If CUDA runs out of memory, rerun with `--batch 2`. Training results and weights should appear under `runs/detect/rail-crack-v2/`; the best checkpoint is `runs/detect/rail-crack-v2/weights/best.pt`.

## 5. Evaluate on the held-out test split

```powershell
.\.venv-training\Scripts\python.exe -m ml.evaluate `
  --model runs/detect/rail-crack-v2/weights/best.pt `
  --data data/datasets/railway-crack-retrain-v1/data.yaml `
  --split test `
  --imgsz 640 `
  --name rail-crack-v2-test
```

Compare precision, recall, mAP@50, mAP@50–95, and the saved confusion matrix with the previous test result. Do not call mAP “accuracy.” Review false positives and missed cracks on actual wooden-model and metal-rail test photos. Confidence is the score attached to each individual predicted box; tune the operating confidence threshold on validation data, not the test split.

## 6. Test predictions visually

```powershell
.\.venv-training\Scripts\python.exe -m ml.infer `
  --model runs/detect/rail-crack-v2/weights/best.pt `
  --source "C:\path\to\held-out-photos" `
  --output runs/predict/rail-crack-v2-check `
  --imgsz 640
```

Open the annotated images and `detections.csv` in the output folder. Keep these photos out of training if they are meant to represent a held-out check.

## 7. Connect the new checkpoint to the website (owner/operator)

Only after reviewing the test results, set `ML_MODEL_PATH` in `backend/.env` to the absolute path of the approved checkpoint, for example:

```env
ML_MODEL_PATH=C:/path/to/RailSafe-Main_project-main/runs/detect/rail-crack-v2/weights/best.pt
```

Restart the backend after changing this setting. The web model demo sends images to the backend; it does not load the training checkpoint directly in the browser. Backend inference currently uses CPU. Test using a registered device and the normal authenticated application flow.

## Important scope note

This model predicts the single crack class. S1/S2/S3 severity is assigned by application logic and must be checked separately against labeled examples. Missing rail/sleeper detection is a future, separate dataset/model task; this training does not add that capability.
