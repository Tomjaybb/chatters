# Padel Tracking Milestone: Single-Object Pipeline

This repository contains a modular single-object detection + tracking pipeline aimed at the first milestone of an AI padel tracking project. The pipeline extracts frames (optional), detects a synthetic yellow ball, tracks it across frames, and produces annotated video plus structured CSV/JSON outputs.

## Requirements

- Python 3.10+
- ffmpeg + ffprobe on PATH
- Python packages: `opencv-python`, `numpy`, `pandas`, `tqdm`, `pyyaml`

Install dependencies:

```bash
pip install opencv-python numpy pandas tqdm pyyaml
```

## Project structure

```
tracker/
  main.py           # CLI entry point: python -m tracker
  cli.py            # argparse subcommands
  io/
    video.py        # OpenCV video + frames reader
    ffmpeg.py       # ffprobe + ffmpeg helpers
  detectors/
    base.py
    hsv_yellow.py
    bg_subtraction.py
  trackers/
    base.py
    naive.py
    kalman.py
  viz/
    overlay.py      # drawing overlays
  utils/
    geometry.py
    logging.py
  configs/
    default.yaml
  tests/
    test_geometry.py
    test_hsv_detector_on_synthetic.py
    test_kalman_basic.py
```

## CLI usage

### 1) Extract frames

```bash
python -m tracker extract --video input.mp4 --out frames --fps 30 --scale_width 1280
```

This writes `frames/%06d.png` and `frames/frames_meta.json` (fps + probe info).

### 2) Track (video mode)

```bash
python -m tracker track --video input.mp4 --out outputs/run1 --detector hsv_yellow --tracker kalman
```

### 3) Track (frames mode)

```bash
python -m tracker track --frames frames --out outputs/run1 --detector hsv_yellow --tracker kalman --fps 30
```

Use `--fps_auto` to read FPS from `frames/frames_meta.json` when available.

## Outputs

- `outputs/run1/annotated.mp4` (or `.avi` fallback)
- `outputs/run1/track.csv`
- `outputs/run1/track.json`
- `outputs/run1/run_meta.json`
- `outputs/run1/debug/` masks (if `--debug`)

## Extending detectors

Detector modules implement `Detector.detect(frame_bgr) -> list[dict]`. A future YOLO detector can be added by returning the same bbox/centre structure (see `tracker/detectors/base.py`).

## Running tests

```bash
pytest tracker/tests
```
test
