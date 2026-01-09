from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class Detector(ABC):
    def __init__(self):
        self.last_debug: Dict[str, any] = {}

    @abstractmethod
    def detect(self, frame_bgr) -> List[dict]:
        """Return detections for a frame.

        Future YOLO detectors should implement this same interface and return
        the same bbox/centre structure to keep the pipeline unchanged.
        """
        raise NotImplementedError
