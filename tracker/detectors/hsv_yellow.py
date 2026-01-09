from __future__ import annotations

from typing import Dict, List, Tuple

import cv2
import numpy as np

from tracker.detectors.base import Detector
from tracker.utils.geometry import bbox_to_center


class HSVYellowDetector(Detector):
    def __init__(
        self,
        lower: Tuple[int, int, int],
        upper: Tuple[int, int, int],
        morph_kernel: int = 5,
        min_area: int = 10,
    ):
        super().__init__()
        self.lower = np.array(lower, dtype=np.uint8)
        self.upper = np.array(upper, dtype=np.uint8)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_kernel, morph_kernel))
        self.min_area = min_area

    def detect(self, frame_bgr) -> List[Dict]:
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower, self.upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
        self.last_debug = {"mask": mask}

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_area = 0.0
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self.min_area:
                continue
            if area > best_area:
                best_area = area
                best = contour
        if best is None:
            return []

        x, y, w, h = cv2.boundingRect(best)
        bbox = (float(x), float(y), float(x + w), float(y + h))
        cx, cy = bbox_to_center(bbox)
        return [
            {
                "bbox": bbox,
                "centre": (cx, cy),
                "confidence": 1.0,
                "area": best_area,
            }
        ]
