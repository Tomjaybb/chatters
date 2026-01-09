import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found on PATH")


def probe_video(video_path: Path) -> dict:
    ensure_ffmpeg_available()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,r_frame_rate,nb_frames,width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    format_info = data.get("format", {})
    return {
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "r_frame_rate": stream.get("r_frame_rate"),
        "nb_frames": stream.get("nb_frames"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration": format_info.get("duration"),
    }


def extract_frames(
    video_path: Path,
    output_dir: Path,
    fps: Optional[float],
    scale_width: Optional[int],
) -> None:
    ensure_ffmpeg_available()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = output_dir / "%06d.png"
    vf_parts = []
    if fps:
        vf_parts.append(f"fps={fps}")
    if scale_width:
        vf_parts.append(f"scale={scale_width}:-2")
    vf = ",".join(vf_parts) if vf_parts else None

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    if vf:
        cmd += ["-vf", vf]
    cmd.append(str(output_pattern))
    subprocess.run(cmd, check=True)
