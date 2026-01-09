from __future__ import annotations

from math import sqrt
from typing import Optional, Tuple


BBox = Tuple[float, float, float, float]
Point = Tuple[float, float]


def bbox_to_center(bbox: BBox) -> Point:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def distance(a: Point, b: Point) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def clamp_roi(roi: Optional[Tuple[int, int, int, int]], width: int, height: int):
    if roi is None:
        return None
    x, y, w, h = roi
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h
