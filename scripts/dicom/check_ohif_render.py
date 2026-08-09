#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that OHIF renders a non-black DICOM canvas.")
    parser.add_argument(
        "url",
        nargs="?",
        default="http://127.0.0.1:3001/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1",
        help="OHIF viewer URL to inspect.",
    )
    parser.add_argument("--output", type=Path, default=Path("/tmp/cohortome-ohif-canvas.png"), help="Canvas screenshot path.")
    parser.add_argument("--wait-ms", type=int, default=15000, help="Milliseconds to wait after page load.")
    parser.add_argument("--min-nonblack-ratio", type=float, default=0.05, help="Minimum fraction of pixels above black.")
    parser.add_argument("--min-stddev", type=float, default=5.0, help="Minimum grayscale standard deviation.")
    args = parser.parse_args()

    try:
        from PIL import Image, ImageStat
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(f"Missing dependency for OHIF render check: {exc}") from exc

    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: errors.append(str(err)))
        response = page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response else "unknown"
        page.wait_for_timeout(args.wait_ms)
        canvases = page.locator("canvas")
        canvas_count = canvases.count()
        if canvas_count == 0:
            page.screenshot(path=str(args.output.with_name("cohortome-ohif-page.png")), full_page=True)
            browser.close()
            raise SystemExit(f"No OHIF canvas found at {args.url} (HTTP {status}).")
        boxes = []
        for index in range(canvas_count):
            box = canvases.nth(index).bounding_box()
            if box:
                boxes.append((index, box))
        if not boxes:
            browser.close()
            raise SystemExit("OHIF canvases exist but none have a visible bounding box.")
        target_index, _ = max(boxes, key=lambda item: item[1]["width"] * item[1]["height"])
        canvases.nth(target_index).screenshot(path=str(args.output))
        browser.close()

    if errors:
        raise SystemExit("OHIF emitted console errors:\n" + "\n".join(errors[:10]))

    image = Image.open(args.output).convert("L")
    stats = ImageStat.Stat(image)
    low, high = image.getextrema()
    stddev = float(stats.stddev[0])
    mean = float(stats.mean[0])
    nonblack = sum(1 for pixel in image.getdata() if pixel > 8)
    nonblack_ratio = nonblack / (image.width * image.height)
    print(
        f"OHIF canvas OK: {args.output} size={image.size} min={low} max={high} "
        f"mean={mean:.2f} stddev={stddev:.2f} nonblack_ratio={nonblack_ratio:.4f}"
    )
    if nonblack_ratio < args.min_nonblack_ratio or stddev < args.min_stddev:
        raise SystemExit("OHIF canvas appears effectively black.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
