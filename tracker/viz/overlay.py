from __future__ import annotations

from typing import List, Optional, Tuple

import cv2


GREEN = (0, 255, 0)
AMBER = (0, 200, 255)
WHITE = (255, 255, 255)


def draw_overlay(
    frame,
    detection_bbox: Optional[Tuple[float, float, float, float]],
    track_center: Optional[Tuple[float, float]],
    trail: List[Tuple[float, float]],
    frame_idx: int,
    time_sec: float,
    detected: bool,
    note: str,
    trail_len: int,
):
    color = GREEN if detected else AMBER
    if detection_bbox is not None:
        x1, y1, x2, y2 = map(int, detection_bbox)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    if track_center is not None:
        cx, cy = map(int, track_center)
        cv2.circle(frame, (cx, cy), 4, color, -1)
    for point in trail[-trail_len:]:
        px, py = map(int, point)
        cv2.circle(frame, (px, py), 2, color, -1)

    label = "DETECTED" if detected else "PREDICTED"
    if note == "uninitialised":
        label = "UNINITIALISED"
    cv2.putText(
        frame,
        f"Frame {frame_idx}  Time {time_sec:.2f}s",
        (10, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        WHITE,
        2,
    )
    cv2.putText(
        frame,
        label,
        (10, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
    )
    return frame
