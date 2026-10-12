"""Image I/O, line detection, and transparent measurement overlay."""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from .vp import VPResult

MAX_PIXELS = 32_000_000


def load_bgr(path: str | Path) -> np.ndarray:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    data = np.fromfile(str(path), dtype=np.uint8)
    if len(data) > 120_000_000:
        raise ValueError("Input file too large for this baseline")
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[0] * image.shape[1] > MAX_PIXELS:
        raise ValueError("Unreadable or excessively large raster image")
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        raise ValueError("Output must be .png or .jpg")
    ok, buf = cv2.imencode(suffix, image)
    if not ok:
        raise RuntimeError("Failed to encode output")
    buf.tofile(str(path))


def detect_segments(image: np.ndarray, min_length_px: float = 35.0,
                    method: str = "lsd") -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if method == "lsd":
        detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
        raw = detector.detect(gray)[0]
        if raw is None:
            return np.empty((0, 4), dtype=float)
        seg = raw.reshape(-1, 4)
    elif method == "hough":
        edges = cv2.Canny(gray, 60, 160)
        raw = cv2.HoughLinesP(edges, rho=1, theta=np.pi / 180,
                              threshold=35, minLineLength=int(min_length_px), maxLineGap=10)
        if raw is None:
            return np.empty((0, 4), dtype=float)
        seg = raw.reshape(-1, 4)
    else:
        raise ValueError("method must be 'lsd' or 'hough'")
    length = np.linalg.norm(seg[:, 2:4] - seg[:, 0:2], axis=1)
    return np.asarray(seg[length >= min_length_px], dtype=float)


def overlay_measurements(img: np.ndarray, segments: np.ndarray, fits: list[VPResult]) -> np.ndarray:
    output = img.copy()
    colors = [(0, 200, 50), (235, 165, 15), (235, 70, 190)]  # BGR
    assigned = np.full(len(segments), -1, dtype=int)
    for k, fit in enumerate(fits):
        assigned[np.asarray(fit.inlier_indices, dtype=int)] = k
    for i, s in enumerate(segments):
        coords = tuple(np.round(s).astype(int))
        color = (100, 100, 100) if assigned[i] == -1 else colors[assigned[i] % len(colors)]
        cv2.line(output, coords[:2], coords[2:], color, 2 if assigned[i] >= 0 else 1, cv2.LINE_AA)
    h, w = output.shape[:2]
    for k, fit in enumerate(fits):
        x, y = fit.xy
        if 0 <= x < w and 0 <= y < h:
            p = (int(round(x)), int(round(y)))
            cv2.drawMarker(output, p, colors[k % len(colors)], markerType=cv2.MARKER_CROSS,
                           markerSize=22, thickness=3)
            cv2.putText(output, f"VP{k+1} ({x:.0f},{y:.0f})", (min(w-170, max(8, p[0]+12)),
                        min(h-10, max(18,p[1]-10))), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        colors[k % len(colors)], 1, cv2.LINE_AA)
    return output
