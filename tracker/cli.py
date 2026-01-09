from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import yaml
from tqdm import tqdm

from tracker.detectors.bg_subtraction import BackgroundSubtractionDetector
from tracker.detectors.hsv_yellow import HSVYellowDetector
from tracker.io.ffmpeg import extract_frames, probe_video
from tracker.io.video import FramesDirSource, VideoFrameSource
from tracker.trackers.kalman import KalmanTracker
from tracker.trackers.naive import NaiveTracker
from tracker.utils.geometry import clamp_roi, distance
from tracker.utils.logging import setup_logger
from tracker.viz.overlay import draw_overlay

LOGGER = setup_logger("tracker")


def parse_roi(value: Optional[str]) -> Optional[Tuple[int, int, int, int]]:
    if not value:
        return None
    parts = [int(v.strip()) for v in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("ROI must be x,y,w,h")
    return parts[0], parts[1], parts[2], parts[3]


def load_config(config_path: Optional[Path]) -> Dict:
    if config_path is None:
        config_path = Path(__file__).parent / "configs" / "default.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_frame_rate(rate: Optional[str]) -> Optional[float]:
    if not rate or rate == "0/0":
        return None
    if "/" in rate:
        num, denom = rate.split("/", 1)
        return float(num) / float(denom)
    return float(rate)


def build_detector(name: str, config: Dict):
    if name == "hsv_yellow":
        cfg = config["hsv_yellow"]
        return HSVYellowDetector(
            lower=tuple(cfg["lower"]),
            upper=tuple(cfg["upper"]),
            morph_kernel=int(cfg.get("morph_kernel", 5)),
            min_area=int(cfg.get("min_area", 20)),
        )
    if name == "background_subtraction":
        cfg = config["background_subtraction"]
        return BackgroundSubtractionDetector(
            history=int(cfg.get("history", 300)),
            var_threshold=int(cfg.get("var_threshold", 16)),
            detect_shadows=bool(cfg.get("detect_shadows", False)),
            min_area=int(cfg.get("min_area", 20)),
        )
    raise ValueError(f"Unknown detector: {name}")


def build_tracker(name: str, fps: float):
    if name == "naive":
        return NaiveTracker()
    if name == "kalman":
        return KalmanTracker(fps=fps)
    raise ValueError(f"Unknown tracker: {name}")


def ensure_output_dirs(output_dir: Path, debug: bool) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir / "debug"
    if debug:
        debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def write_meta(output_dir: Path, meta: Dict) -> None:
    with (output_dir / "run_meta.json").open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)


def compute_stats(records: List[Dict], fps: float, interpolated: int) -> Dict:
    total_frames = len(records)
    detected_frames = sum(1 for r in records if r["detected"] == 1)
    detection_rate = detected_frames / total_frames if total_frames else 0.0
    longest_missing = 0
    current = 0
    speeds = []
    last_pos = None
    for record in records:
        if record["detected"] == 0:
            current += 1
            longest_missing = max(longest_missing, current)
        else:
            current = 0
        pos = record["track_cx"], record["track_cy"]
        if record["track_cx"] is not None and record["track_cy"] is not None:
            if last_pos is not None:
                speeds.append(distance(last_pos, pos) * fps)
            last_pos = pos
    mean_speed = float(np.mean(speeds)) if speeds else 0.0
    return {
        "total_frames": total_frames,
        "detected_frames": detected_frames,
        "detection_rate": detection_rate,
        "longest_missing_streak": longest_missing,
        "mean_pixel_speed": mean_speed,
        "number_of_interpolated_points": interpolated,
    }


def interpolate_gaps(records: List[Dict], max_gap: int) -> int:
    if max_gap <= 0:
        return 0
    interpolated = 0
    idx = 0
    while idx < len(records):
        if records[idx]["detected"] == 1:
            idx += 1
            continue
        start = idx - 1
        while idx < len(records) and records[idx]["detected"] == 0:
            idx += 1
        end = idx
        gap = end - start - 1
        if gap <= 0:
            continue
        if gap <= max_gap and start >= 0 and end < len(records):
            start_pos = (records[start]["track_cx"], records[start]["track_cy"])
            end_pos = (records[end]["track_cx"], records[end]["track_cy"])
            if None not in start_pos and None not in end_pos:
                for i in range(1, gap + 1):
                    alpha = i / (gap + 1)
                    cx = start_pos[0] + alpha * (end_pos[0] - start_pos[0])
                    cy = start_pos[1] + alpha * (end_pos[1] - start_pos[1])
                    records[start + i]["track_cx"] = float(cx)
                    records[start + i]["track_cy"] = float(cy)
                    records[start + i]["note"] = "interpolated"
                    interpolated += 1
    return interpolated


def run_extract(args: argparse.Namespace) -> None:
    video_path = Path(args.video)
    output_dir = Path(args.out)
    probe = probe_video(video_path)
    LOGGER.info("Input video: %s", video_path)
    LOGGER.info("Probe info: %s", probe)
    if probe.get("avg_frame_rate") != probe.get("r_frame_rate"):
        LOGGER.warning("Variable or odd FPS detected: avg %s vs r %s", probe.get("avg_frame_rate"), probe.get("r_frame_rate"))
    derived_fps = parse_frame_rate(probe.get("avg_frame_rate"))
    extract_fps = args.fps or derived_fps
    extract_frames(video_path, output_dir, args.fps, args.scale_width)
    meta = {
        "video": str(video_path),
        "fps": extract_fps,
        "scale_width": args.scale_width,
        "probe": probe,
    }
    with (output_dir / "frames_meta.json").open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)


def open_video_writer(output_dir: Path, fps: float, frame_size: Tuple[int, int]) -> Tuple[Optional[cv2.VideoWriter], Path]:
    width, height = frame_size
    mp4_path = output_dir / "annotated.mp4"
    writer = cv2.VideoWriter(str(mp4_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if writer.isOpened():
        return writer, mp4_path
    writer.release()
    avi_path = output_dir / "annotated.avi"
    writer = cv2.VideoWriter(str(avi_path), cv2.VideoWriter_fourcc(*"XVID"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Unable to open video writer")
    LOGGER.warning("mp4v failed, falling back to AVI/XVID")
    return writer, avi_path


def run_track(args: argparse.Namespace) -> None:
    output_dir = Path(args.out)
    debug_dir = ensure_output_dirs(output_dir, args.debug)
    config = load_config(Path(args.config) if args.config else None)

    if args.video:
        source = VideoFrameSource(Path(args.video))
        fps = source.fps()
        frame_count = source.frame_count()
    else:
        source = FramesDirSource(Path(args.frames))
        frame_count = source.frame_count()
        fps = args.fps
        if args.fps_auto:
            meta_path = Path(args.frames) / "frames_meta.json"
            if meta_path.exists():
                with meta_path.open("r", encoding="utf-8") as handle:
                    meta = json.load(handle)
                    fps = meta.get("fps") or fps
        if fps is None:
            raise RuntimeError("FPS is required for frames mode")

    LOGGER.info("Tracking source: %s", args.video or args.frames)
    LOGGER.info("FPS: %.3f", fps)
    LOGGER.info("Frame count: %s", frame_count)

    detector = build_detector(args.detector, config)
    tracker = build_tracker(args.tracker, fps)

    writer = None
    output_video_path = None
    if args.write_video:
        frame_size = source.frame_size()
        writer, output_video_path = open_video_writer(output_dir, fps, frame_size)

    records: List[Dict] = []
    trail: List[Tuple[float, float]] = []

    roi = parse_roi(args.roi)

    for frame_idx, frame in tqdm(source.frames(), total=frame_count, desc="Tracking"):
        height, width = frame.shape[:2]
        roi_clamped = clamp_roi(roi, width, height)
        frame_for_det = frame
        if roi_clamped:
            x, y, w, h = roi_clamped
            frame_for_det = frame[y : y + h, x : x + w]

        detections = detector.detect(frame_for_det)
        if roi_clamped:
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                det["bbox"] = (x1 + x, y1 + y, x2 + x, y2 + y)
                cx, cy = det["centre"]
                det["centre"] = (cx + x, cy + y)
        state = tracker.update(detections, frame_idx, frame_idx / fps)

        detection = state["detection"]
        det_bbox = detection["bbox"] if detection else None
        det_cx = detection["centre"][0] if detection else None
        det_cy = detection["centre"][1] if detection else None
        confidence = detection["confidence"] if detection else None

        record = {
            "frame_idx": frame_idx,
            "time_sec": frame_idx / fps,
            "detected": state["detected"],
            "det_x1": det_bbox[0] if det_bbox else None,
            "det_y1": det_bbox[1] if det_bbox else None,
            "det_x2": det_bbox[2] if det_bbox else None,
            "det_y2": det_bbox[3] if det_bbox else None,
            "det_cx": det_cx,
            "det_cy": det_cy,
            "track_cx": state["track_cx"],
            "track_cy": state["track_cy"],
            "track_vx": state["track_vx"],
            "track_vy": state["track_vy"],
            "confidence": confidence if confidence is not None else 1.0,
            "missing_count": state["missing_count"],
            "note": state["note"],
        }
        records.append(record)

        if state["track_cx"] is not None and state["track_cy"] is not None:
            trail.append((state["track_cx"], state["track_cy"]))

        if args.write_video and writer is not None:
            draw_overlay(
                frame,
                det_bbox,
                (state["track_cx"], state["track_cy"]) if state["track_cx"] is not None else None,
                trail,
                frame_idx,
                frame_idx / fps,
                state["detected"] == 1,
                state["note"],
                args.trail_len,
            )
            writer.write(frame)

        if args.debug and detector.last_debug:
            mask = detector.last_debug.get("mask")
            if mask is not None:
                cv2.imwrite(str(debug_dir / f"mask_{frame_idx:06d}.png"), mask)

    interpolated = interpolate_gaps(records, args.max_gap)

    df = pd.DataFrame(records)
    if args.write_csv:
        df.to_csv(output_dir / "track.csv", index=False)
    if args.write_json:
        df.to_json(output_dir / "track.json", orient="records", indent=2)

    if writer is not None:
        writer.release()
    if output_video_path:
        LOGGER.info("Annotated video written to %s", output_video_path)

    meta = {
        "input": args.video or args.frames,
        "fps": fps,
        "frame_count": frame_count,
        "detector": args.detector,
        "tracker": args.tracker,
        "output_video": str(output_video_path) if output_video_path else None,
        "config": config,
    }
    meta.update(compute_stats(records, fps, interpolated))
    write_meta(output_dir, meta)

    if hasattr(source, "release"):
        source.release()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-object detection + tracking pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract frames using ffmpeg")
    extract_parser.add_argument("--video", required=True, help="Input video")
    extract_parser.add_argument("--out", required=True, help="Output frames directory")
    extract_parser.add_argument("--fps", type=float, default=None, help="Override FPS")
    extract_parser.add_argument("--scale_width", type=int, default=None, help="Scale width")
    extract_parser.set_defaults(func=run_extract)

    track_parser = subparsers.add_parser("track", help="Track single object")
    source_group = track_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--video", help="Input video")
    source_group.add_argument("--frames", help="Frames directory")
    track_parser.add_argument("--out", required=True, help="Output directory")
    track_parser.add_argument(
        "--detector",
        required=True,
        choices=["hsv_yellow", "background_subtraction"],
        help="Detector name",
    )
    track_parser.add_argument(
        "--tracker",
        required=True,
        choices=["naive", "kalman"],
        help="Tracker name",
    )
    track_parser.add_argument("--fps", type=float, default=None, help="FPS for frames mode")
    track_parser.add_argument("--fps_auto", action="store_true", help="Infer fps from frames_meta.json")
    track_parser.add_argument("--write_video", action="store_true", default=True)
    track_parser.add_argument("--no_write_video", action="store_false", dest="write_video")
    track_parser.add_argument("--write_csv", action="store_true", default=True)
    track_parser.add_argument("--no_write_csv", action="store_false", dest="write_csv")
    track_parser.add_argument("--write_json", action="store_true", default=True)
    track_parser.add_argument("--no_write_json", action="store_false", dest="write_json")
    track_parser.add_argument("--trail_len", type=int, default=30)
    track_parser.add_argument("--max_gap", type=int, default=10)
    track_parser.add_argument("--roi", type=str, default=None, help="x,y,w,h")
    track_parser.add_argument("--debug", action="store_true", help="Write debug masks")
    track_parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    track_parser.set_defaults(func=run_track)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
