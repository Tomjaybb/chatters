from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from tracker.trackers.base import Tracker
from tracker.utils.geometry import distance


class NaiveTracker(Tracker):
    def __init__(self):
        super().__init__()
        self.last_position: Optional[Tuple[float, float]] = None
        self.last_velocity: Optional[Tuple[float, float]] = None
        self.last_frame_idx: Optional[int] = None
        self.missing_count = 0

    @property
    def is_initialized(self) -> bool:
        return self.last_position is not None

    def _choose_detection(self, detections: List[Dict]) -> Optional[Dict]:
        if not detections:
            return None
        if self.last_position is None:
            return max(detections, key=lambda d: d.get("area", 0.0))
        return min(detections, key=lambda d: distance(self.last_position, d["centre"]))

    def update(self, detections: List[Dict], frame_idx: int, time_sec: float) -> Dict:
        chosen = self._choose_detection(detections)
        note = "uninitialised"
        detected = 0
        if chosen is not None:
            detected = 1
            position = chosen["centre"]
            if self.last_position is not None and self.last_frame_idx is not None:
                dt_frames = max(frame_idx - self.last_frame_idx, 1)
                vx = (position[0] - self.last_position[0]) / dt_frames
                vy = (position[1] - self.last_position[1]) / dt_frames
                self.last_velocity = (vx, vy)
            self.last_position = position
            self.last_frame_idx = frame_idx
            self.missing_count = 0
            note = "updated"
        elif self.last_position is not None:
            self.missing_count += 1
            note = "predicted"
            if self.last_velocity is not None and self.last_frame_idx is not None:
                dt_frames = max(frame_idx - self.last_frame_idx, 1)
                position = (
                    self.last_position[0] + self.last_velocity[0] * dt_frames,
                    self.last_position[1] + self.last_velocity[1] * dt_frames,
                )
                self.last_position = position
                self.last_frame_idx = frame_idx
            else:
                position = self.last_position
        else:
            position = None

        vx, vy = (None, None)
        if self.last_velocity is not None:
            vx, vy = self.last_velocity

        return {
            "track_id": self.track_id,
            "detected": detected,
            "detection": chosen,
            "track_cx": None if position is None else float(position[0]),
            "track_cy": None if position is None else float(position[1]),
            "track_vx": vx,
            "track_vy": vy,
            "missing_count": self.missing_count,
            "note": note,
        }
