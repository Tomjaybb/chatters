from __future__ import annotations

from typing import Dict, List

import cv2
import numpy as np

from tracker.detectors.base import Detector
from tracker.utils.geometry import bbox_to_center


class BackgroundSubtractionDetector(Detector):
    def __init__(
        self,
        history: int = 300,
        var_threshold: int = 16,
        detect_shadows: bool = False,
        min_area: int = 20,
    ):
        super().__init__()
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history, varThreshold=var_threshold, detectShadows=detect_shadows
        )
        self.min_area = min_area
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(self, frame_bgr) -> List[Dict]:
        fg_mask = self.subtractor.apply(frame_bgr)
        _, mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
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
