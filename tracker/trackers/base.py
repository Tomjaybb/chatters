from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class Tracker(ABC):
    def __init__(self):
        self.track_id = 1

    @abstractmethod
    def update(self, detections: List[Dict], frame_idx: int, time_sec: float) -> Dict:
        raise NotImplementedError

    @property
    def is_initialized(self) -> bool:
        return False
