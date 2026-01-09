import cv2
import numpy as np

from tracker.detectors.hsv_yellow import HSVYellowDetector


def test_hsv_yellow_detector_on_synthetic():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    center = (80, 120)
    cv2.circle(frame, center, 10, (0, 255, 255), -1)

    detector = HSVYellowDetector(lower=(20, 100, 100), upper=(35, 255, 255))
    detections = detector.detect(frame)

    assert len(detections) == 1
    det_center = detections[0]["centre"]
    assert abs(det_center[0] - center[0]) <= 3
    assert abs(det_center[1] - center[1]) <= 3
