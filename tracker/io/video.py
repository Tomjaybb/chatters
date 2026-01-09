from __future__ import annotations

from pathlib import Path
from typing import Generator, List, Optional, Tuple

import cv2


def list_frames(frames_dir: Path) -> List[Path]:
    return sorted(frames_dir.glob("*.png"))


class VideoFrameSource:
    def __init__(self, video_path: Path):
        self.video_path = video_path
        self.cap = cv2.VideoCapture(str(video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Unable to open video: {video_path}")

    def fps(self) -> float:
        return float(self.cap.get(cv2.CAP_PROP_FPS))

    def frame_count(self) -> int:
        return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def frame_size(self) -> Tuple[int, int]:
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return width, height

    def frames(self) -> Generator[Tuple[int, any], None, None]:
        idx = 0
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break
            yield idx, frame
            idx += 1

    def release(self) -> None:
        self.cap.release()


class FramesDirSource:
    def __init__(self, frames_dir: Path):
        self.frames_dir = frames_dir
        self.frame_paths = list_frames(frames_dir)
        if not self.frame_paths:
            raise RuntimeError(f"No PNG frames found in {frames_dir}")

    def frame_count(self) -> int:
        return len(self.frame_paths)

    def frame_size(self) -> Tuple[int, int]:
        first = cv2.imread(str(self.frame_paths[0]))
        if first is None:
            raise RuntimeError(f"Unable to read frame {self.frame_paths[0]}")
        height, width = first.shape[:2]
        return width, height

    def frames(self) -> Generator[Tuple[int, any], None, None]:
        for idx, path in enumerate(self.frame_paths):
            frame = cv2.imread(str(path))
            if frame is None:
                raise RuntimeError(f"Unable to read frame {path}")
            yield idx, frame
