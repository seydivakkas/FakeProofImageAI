"""Optional P9-I07 LOCAL visual screenshot capture, not Windows end-user acceptance.

Requires Tkinter, Pillow, an available display/Xvfb, and a virtual environment
with installed project. No network access, no real photos, no screenshot-derived
science claims. User must inspect outputs manually against the design mockups.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from aiforensics.desktop_app import DesktopApp, PAGES


def capture(out_dir, resolution=(1366, 768)):
    from PIL import ImageGrab
    dest = Path(out_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fakeproof-p9-i07-") as work:
        app = DesktopApp(workspace=work)
        app.geometry(f"{resolution[0]}x{resolution[1]}+0+0")
        app.update()
        results = []
        try:
            for i, page in enumerate(PAGES, 1):
                app.go(page)
                app.update_idletasks()
                app.update()
                x, y = app.winfo_rootx(), app.winfo_rooty()
                w, h = app.winfo_width(), app.winfo_height()
                image = ImageGrab.grab(bbox=(x, y, x+w, y+h))
                name = f"{i:02d}_{['overview','import','planning','calibration','measurements','evidence','dependencies','export','settings'][i-1]}.png"
                path = dest / name
                image.save(path)
                results.append({"page": page, "png": name,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "width": image.width, "height": image.height})
        finally:
            app.destroy()
    index = {"type": "SYNTHETIC_GUI_CAPTURE_NOT_WINDOWS_ACCEPTANCE",
             "resolution": list(resolution),
             "design_pixel_match_tested": False,
             "entries": results}
    (dest / "screenshots.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="outputs/p9_i07_screenshots")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    if not (1024 <= args.width <= 8192 and 640 <= args.height <= 4320):
        parser.error("Invalid display dimensions")
    print(json.dumps(capture(args.out, (args.width, args.height)),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
