from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from tracker.trackers.base import Tracker
from tracker.utils.geometry import distance


class KalmanTracker(Tracker):
    def __init__(self, fps: float, process_var: float = 1.0, meas_var: float = 5.0):
        super().__init__()
        self.dt = 1.0 / fps
        self.process_var = process_var
        self.meas_var = meas_var
        self.state: Optional[np.ndarray] = None
        self.P: Optional[np.ndarray] = None
        self.missing_count = 0

    @property
    def is_initialized(self) -> bool:
        return self.state is not None

    def _system_matrices(self):
        dt = self.dt
        F = np.array(
            [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]],
            dtype=float,
        )
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        q = self.process_var
        Q = q * np.array(
            [
                [dt ** 4 / 4, 0, dt ** 3 / 2, 0],
                [0, dt ** 4 / 4, 0, dt ** 3 / 2],
                [dt ** 3 / 2, 0, dt ** 2, 0],
                [0, dt ** 3 / 2, 0, dt ** 2],
            ],
            dtype=float,
        )
        R = self.meas_var * np.eye(2)
        return F, H, Q, R

    def _choose_detection(self, detections: List[Dict]) -> Optional[Dict]:
        if not detections:
            return None
        if self.state is None:
            return max(detections, key=lambda d: d.get("area", 0.0))
        predicted = (float(self.state[0]), float(self.state[1]))
        return min(detections, key=lambda d: distance(predicted, d["centre"]))

    def update(self, detections: List[Dict], frame_idx: int, time_sec: float) -> Dict:
        chosen = self._choose_detection(detections)
        F, H, Q, R = self._system_matrices()
        note = "uninitialised"
        detected = 0

        if self.state is None:
            if chosen is None:
                return {
                    "track_id": self.track_id,
                    "detected": 0,
                    "detection": None,
                    "track_cx": None,
                    "track_cy": None,
                    "track_vx": None,
                    "track_vy": None,
                    "missing_count": self.missing_count,
                    "note": note,
                }
            cx, cy = chosen["centre"]
            self.state = np.array([cx, cy, 0.0, 0.0], dtype=float)
            self.P = np.eye(4)
            self.missing_count = 0
            detected = 1
            note = "initialised"
        else:
            self.state = F @ self.state
            self.P = F @ self.P @ F.T + Q
            if chosen is not None:
                z = np.array([[chosen["centre"][0]], [chosen["centre"][1]]])
                y = z - H @ self.state.reshape(-1, 1)
                S = H @ self.P @ H.T + R
                K = self.P @ H.T @ np.linalg.inv(S)
                self.state = (self.state.reshape(-1, 1) + K @ y).flatten()
                I = np.eye(4)
                self.P = (I - K @ H) @ self.P
                self.missing_count = 0
                detected = 1
                note = "updated"
            else:
                self.missing_count += 1
                note = "predicted"

        return {
            "track_id": self.track_id,
            "detected": detected,
            "detection": chosen,
            "track_cx": float(self.state[0]) if self.state is not None else None,
            "track_cy": float(self.state[1]) if self.state is not None else None,
            "track_vx": float(self.state[2]) if self.state is not None else None,
            "track_vy": float(self.state[3]) if self.state is not None else None,
            "missing_count": self.missing_count,
            "note": note,
        }
