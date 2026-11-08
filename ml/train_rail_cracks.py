from ultralytics import YOLO

if __name__ == "__main__":
    model = YOLO("yolov8n.pt")
    model.train(
        data="data/datasets/railway-crack-retrain-v1/data.yaml",
        epochs=100,
        imgsz=640,
        batch=8,
        device=0,  # NVIDIA GPU
        workers=0, # avoids Windows multiprocessing issues
        project="runs/detect",
        name="rail-crack-v1",
    )