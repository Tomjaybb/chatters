import numpy as np

from tracker.trackers.kalman import KalmanTracker


def test_kalman_tracker_basic():
    tracker = KalmanTracker(fps=30.0)
    detections = []
    for i in range(5):
        detections = [
            {
                "centre": (float(50 + i * 2), float(60 + i * 2)),
                "bbox": (0.0, 0.0, 1.0, 1.0),
                "confidence": 1.0,
                "area": 1.0,
            }
        ]
        state = tracker.update(detections, i, i / 30.0)
    assert state["track_cx"] is not None
    assert state["track_cy"] is not None
    assert np.isfinite(state["track_vx"])
    assert np.isfinite(state["track_vy"])
