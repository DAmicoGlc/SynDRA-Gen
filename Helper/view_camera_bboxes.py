#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "This script requires Pillow. Install it with: pip install pillow"
    ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overlay SimulatrixMV camera bounding boxes on RGB .bin frames."
    )
    parser.add_argument(
        "camera_root",
        type=Path,
        help="Path to one camera folder, e.g. Saved/CameraCheck/.../RGBCamera_Check",
    )
    parser.add_argument("--width", type=int, default=1280, help="Image width in pixels.")
    parser.add_argument("--height", type=int, default=960, help="Image height in pixels.")
    parser.add_argument(
        "--frame",
        type=int,
        default=None,
        help="Single frame index to inspect, e.g. 42. If omitted, all frames are processed.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output folder for overlay PNGs. Defaults to <camera_root>/BBoxPreview.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open the generated overlay image(s) with the default image viewer.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of frames processed when --frame is not set. Use 0 for no limit.",
    )
    return parser.parse_args()


def load_rgb_bin(bin_path: Path, width: int, height: int) -> Image.Image:
    expected_size = width * height * 3
    raw = bin_path.read_bytes()
    if len(raw) != expected_size:
        raise ValueError(
            f"{bin_path} has {len(raw)} bytes, expected {expected_size} "
            f"for a {width}x{height} BGR frame."
        )
    return Image.frombytes("RGB", (width, height), raw, "raw", "BGR")


def load_boxes(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def box_color(label_id_text: str) -> tuple[int, int, int]:
    try:
        label_id = int(float(label_id_text))
    except ValueError:
        label_id = abs(hash(label_id_text)) % 256

    return (
        55 + ((label_id * 67) % 200),
        55 + ((label_id * 29) % 200),
        55 + ((label_id * 113) % 200),
    )


def draw_boxes(image: Image.Image, boxes: list[dict[str, str]]) -> Image.Image:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    for box in boxes:
        try:
            min_x = float(box["min_x"])
            min_y = float(box["min_y"])
            max_x = float(box["max_x"])
            max_y = float(box["max_y"])
        except (KeyError, ValueError):
            continue

        label = box.get("label", "Unlabeled")
        label_id = box.get("label_id", "-1")
        actor = box.get("actor", "")
        touches_boundary = box.get("touches_boundary", "0") == "1"

        color = box_color(label_id)
        if touches_boundary:
            color = (255, 180, 40)

        text = f"{label} [{label_id}]"
        if actor and actor != "None":
            text += f" {actor}"

        draw.rectangle((min_x, min_y, max_x, max_y), outline=color, width=3)

        text_anchor = (min_x + 4, max(min_y - 18, 0))
        text_bbox = draw.textbbox(text_anchor, text)
        draw.rectangle(text_bbox, fill=color)
        draw.text(text_anchor, text, fill=(255, 255, 255))

    return overlay


def iter_frame_indices(bin_dir: Path, csv_dir: Path, requested_frame: int | None) -> list[int]:
    if requested_frame is not None:
        return [requested_frame]

    indices: set[int] = set()
    for path in bin_dir.glob("frame_*.bin"):
        try:
            indices.add(int(path.stem.split("_")[-1]))
        except ValueError:
            continue
    for path in csv_dir.glob("frame_*.csv"):
        try:
            indices.add(int(path.stem.split("_")[-1]))
        except ValueError:
            continue
    return sorted(indices)


def main() -> int:
    args = parse_args()
    camera_root = args.camera_root.resolve()
    bin_dir = camera_root / "Bin_folder"
    csv_dir = camera_root / "BBoxes"
    output_dir = args.output.resolve() if args.output else (camera_root / "BBoxPreview")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bin_dir.exists():
        print(f"Missing Bin_folder: {bin_dir}", file=sys.stderr)
        return 1
    if not csv_dir.exists():
        print(f"Missing BBoxes folder: {csv_dir}", file=sys.stderr)
        return 1

    frame_indices = iter_frame_indices(bin_dir, csv_dir, args.frame)
    if args.limit > 0 and args.frame is None:
        frame_indices = frame_indices[:args.limit]

    if not frame_indices:
        print("No frames found.", file=sys.stderr)
        return 1

    generated_paths: list[Path] = []
    for frame_index in frame_indices:
        bin_path = bin_dir / f"frame_{frame_index:06d}.bin"
        csv_path = csv_dir / f"frame_{frame_index:06d}.csv"

        if not bin_path.exists():
            print(f"Skipping frame {frame_index}: missing {bin_path.name}")
            continue

        image = load_rgb_bin(bin_path, args.width, args.height)
        boxes = load_boxes(csv_path)
        overlay = draw_boxes(image, boxes)

        output_path = output_dir / f"frame_{frame_index:06d}.png"
        overlay.save(output_path)
        generated_paths.append(output_path)
        print(f"Saved {output_path} with {len(boxes)} boxes")

        if args.show:
            overlay.show(title=output_path.name)

    return 0 if generated_paths else 1


if __name__ == "__main__":
    raise SystemExit(main())
