#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise SystemExit("This script requires Pillow. Install it with: pip install pillow numpy") from exc


POINT_STRIDE_FLOATS = 6
POINT_DTYPE = np.dtype("<f4")
BOX_EDGES = (
    (0, 1), (0, 2), (0, 4),
    (1, 3), (1, 5),
    (2, 3), (2, 6),
    (3, 7),
    (4, 5), (4, 6),
    (5, 7),
    (6, 7),
)


@dataclass
class LidarBBox:
    timestamp: float | None
    label_id: int | None
    label_name: str
    corners: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert and visualize SynDRA-Gen camera and LiDAR exports."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    image_parser = subparsers.add_parser(
        "image-bin-to-png",
        help="Convert one RGB, depth, or segmentation .bin image to .png.",
    )
    image_parser.add_argument("bin_file", type=Path, help="Input .bin file.")
    image_parser.add_argument(
        "--image-type",
        choices=("rgb", "depth", "segmentation"),
        required=True,
        help="Type of image stored in the .bin file.",
    )
    image_parser.add_argument("--width", type=int, required=True, help="Image width.")
    image_parser.add_argument("--height", type=int, required=True, help="Image height.")
    image_parser.add_argument("--output", type=Path, default=None, help="Output .png path.")
    image_parser.add_argument(
        "--segmentation-color",
        choices=("gray", "palette"),
        default="palette",
        help="How to render segmentation labels.",
    )
    image_parser.add_argument(
        "--depth-preview",
        action="store_true",
        help="Also save an 8-bit normalized preview next to the 16-bit depth PNG.",
    )

    pcd_parser = subparsers.add_parser(
        "pointcloud-bin-to-pcd",
        help="Convert one LiDAR .bin point cloud to an ASCII .pcd file.",
    )
    pcd_parser.add_argument("bin_file", type=Path, help="Input LiDAR .bin file.")
    pcd_parser.add_argument("--output", type=Path, default=None, help="Output .pcd path.")
    pcd_parser.add_argument(
        "--drop-invalid",
        action="store_true",
        help="Skip points with invalid coordinates or class_id < 0.",
    )

    front_view_parser = subparsers.add_parser(
        "pointcloud-front-view",
        help="Render a LiDAR front-view PNG from one .bin point cloud.",
    )
    front_view_parser.add_argument("bin_file", type=Path, help="Input LiDAR .bin file.")
    front_view_parser.add_argument("--output", type=Path, default=None, help="Output .png path.")
    front_view_parser.add_argument("--width", type=int, default=1600, help="Output width.")
    front_view_parser.add_argument("--height", type=int, default=900, help="Output height.")
    front_view_parser.add_argument("--hfov", type=float, default=120.0, help="Horizontal FOV in degrees.")
    front_view_parser.add_argument("--vfov", type=float, default=60.0, help="Vertical FOV in degrees.")
    front_view_parser.add_argument("--max-range", type=float, default=120.0, help="Maximum range in meters.")
    front_view_parser.add_argument(
        "--color-by",
        choices=("class", "depth"),
        default="class",
        help="Point coloring mode.",
    )
    front_view_parser.add_argument("--point-size", type=int, default=2, help="Rendered point size in pixels.")

    image_bbox_parser = subparsers.add_parser(
        "overlay-image-bboxes",
        help="Overlay camera bounding boxes on one RGB camera frame.",
    )
    image_bbox_parser.add_argument(
        "camera_root",
        type=Path,
        help="Camera folder path, for example Saved/DataAcquired/.../RGBCamera_Check",
    )
    image_bbox_parser.add_argument("--width", type=int, required=True, help="Image width.")
    image_bbox_parser.add_argument("--height", type=int, required=True, help="Image height.")
    image_bbox_parser.add_argument("--frame", type=int, default=0, help="Frame index.")
    image_bbox_parser.add_argument("--output", type=Path, default=None, help="Output .png path.")

    point_bbox_parser = subparsers.add_parser(
        "overlay-pointcloud-bboxes",
        help="Overlay LiDAR 3D boxes on a rendered front-view point-cloud image.",
    )
    point_bbox_parser.add_argument(
        "lidar_root",
        type=Path,
        help="LiDAR folder path, for example Saved/DataAcquired/.../BeamsStackLidar_Check",
    )
    point_bbox_parser.add_argument("--frame", type=int, default=0, help="Frame index.")
    point_bbox_parser.add_argument("--output", type=Path, default=None, help="Output .png path.")
    point_bbox_parser.add_argument("--width", type=int, default=1600, help="Output width.")
    point_bbox_parser.add_argument("--height", type=int, default=900, help="Output height.")
    point_bbox_parser.add_argument("--hfov", type=float, default=120.0, help="Horizontal FOV in degrees.")
    point_bbox_parser.add_argument("--vfov", type=float, default=60.0, help="Vertical FOV in degrees.")
    point_bbox_parser.add_argument("--max-range", type=float, default=120.0, help="Maximum range in meters.")
    point_bbox_parser.add_argument("--point-size", type=int, default=2, help="Rendered point size in pixels.")

    return parser.parse_args()


def color_from_id(class_id: int) -> tuple[int, int, int]:
    hue = (class_id * 0.6180339887498949) % 1.0
    r, g, b = hsv_to_rgb(hue, 0.65, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6
    if i == 0:
        return v, t, p
    if i == 1:
        return q, v, p
    if i == 2:
        return p, v, t
    if i == 3:
        return p, q, v
    if i == 4:
        return t, p, v
    return v, p, q


def default_output_path(input_path: Path, suffix: str) -> Path:
    return input_path.with_suffix(suffix)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_rgb_bin(path: Path, width: int, height: int) -> Image.Image:
    raw = path.read_bytes()
    expected = width * height * 3
    if len(raw) != expected:
        raise ValueError(f"{path} has {len(raw)} bytes, expected {expected} for an RGB frame.")
    return Image.frombytes("RGB", (width, height), raw, "raw", "BGR")


def read_depth_bin(path: Path, width: int, height: int) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.uint8)
    expected = width * height * 2
    if raw.size != expected:
        raise ValueError(f"{path} has {raw.size} bytes, expected {expected} for a depth frame.")
    raw = raw.reshape((height, width, 2))
    return (raw[:, :, 0].astype(np.uint16) << 8) | raw[:, :, 1].astype(np.uint16)


def read_segmentation_bin(path: Path, width: int, height: int) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.uint8)
    expected = width * height
    if raw.size != expected:
        raise ValueError(f"{path} has {raw.size} bytes, expected {expected} for a segmentation frame.")
    return raw.reshape((height, width))


def segmentation_to_image(labels: np.ndarray, mode: str) -> Image.Image:
    if mode == "gray":
        return Image.fromarray(labels, mode="L")

    palette = np.zeros((256, 3), dtype=np.uint8)
    for class_id in range(256):
        palette[class_id] = np.array(color_from_id(class_id), dtype=np.uint8)
    rgb = palette[labels]
    return Image.fromarray(rgb, mode="RGB")


def save_depth_png(depth: np.ndarray, output_path: Path, save_preview: bool) -> None:
    ensure_parent(output_path)
    image = Image.fromarray(depth, mode="I;16")
    image.save(output_path)

    if save_preview:
        preview_path = output_path.with_name(f"{output_path.stem}_preview.png")
        if np.max(depth) == np.min(depth):
            preview = np.zeros_like(depth, dtype=np.uint8)
        else:
            preview = ((depth.astype(np.float32) - float(np.min(depth))) / float(np.max(depth) - np.min(depth)) * 255.0)
            preview = preview.astype(np.uint8)
        Image.fromarray(preview, mode="L").save(preview_path)


def load_point_cloud(bin_path: Path) -> np.ndarray:
    raw = np.fromfile(bin_path, dtype=POINT_DTYPE)
    if raw.size == 0:
        return np.empty((0, POINT_STRIDE_FLOATS), dtype=np.float32)
    if raw.size % POINT_STRIDE_FLOATS != 0:
        raise ValueError(f"{bin_path} does not contain a whole number of LiDAR points.")
    return raw.reshape((-1, POINT_STRIDE_FLOATS))


def filter_points(points: np.ndarray, drop_invalid: bool) -> np.ndarray:
    mask = np.isfinite(points).all(axis=1)
    if drop_invalid:
        mask &= points[:, 3] >= 0
    return points[mask]


def write_ascii_pcd(points: np.ndarray, output_path: Path) -> None:
    ensure_parent(output_path)
    valid_points = filter_points(points, drop_invalid=False)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# .PCD v0.7 - Point Cloud Data file format\n")
        handle.write("VERSION 0.7\n")
        handle.write("FIELDS x y z class_id channel timestamp\n")
        handle.write("SIZE 4 4 4 4 4 4\n")
        handle.write("TYPE F F F I I F\n")
        handle.write("COUNT 1 1 1 1 1 1\n")
        handle.write(f"WIDTH {valid_points.shape[0]}\n")
        handle.write("HEIGHT 1\n")
        handle.write("VIEWPOINT 0 0 0 1 0 0 0\n")
        handle.write(f"POINTS {valid_points.shape[0]}\n")
        handle.write("DATA ascii\n")
        for row in valid_points:
            handle.write(
                f"{row[0]:.6f} {row[1]:.6f} {row[2]:.6f} "
                f"{int(row[3])} {int(row[4])} {row[5]:.6f}\n"
            )


def project_front_view(
    xyz: np.ndarray,
    width: int,
    height: int,
    hfov_deg: float,
    vfov_deg: float,
    max_range_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = xyz[:, 0]
    y = xyz[:, 1]
    z = xyz[:, 2]

    distance = np.linalg.norm(xyz, axis=1)
    yaw = np.degrees(np.arctan2(y, x))
    pitch = np.degrees(np.arctan2(z, np.sqrt(np.maximum(x * x + y * y, 1e-8))))

    mask = np.isfinite(distance)
    mask &= x > 1e-4
    mask &= distance <= max_range_m
    mask &= np.abs(yaw) <= hfov_deg * 0.5
    mask &= np.abs(pitch) <= vfov_deg * 0.5

    yaw = yaw[mask]
    pitch = pitch[mask]
    distance = distance[mask]

    u = ((yaw + hfov_deg * 0.5) / hfov_deg) * (width - 1)
    v = (1.0 - ((pitch + vfov_deg * 0.5) / vfov_deg)) * (height - 1)

    uv = np.column_stack((u, v))
    return uv, distance, mask


def render_point_cloud_front_view(
    points: np.ndarray,
    width: int,
    height: int,
    hfov_deg: float,
    vfov_deg: float,
    max_range_m: float,
    color_by: str,
    point_size: int,
) -> Image.Image:
    image = Image.new("RGB", (width, height), color=(10, 10, 14))
    draw = ImageDraw.Draw(image)

    valid_points = filter_points(points, drop_invalid=True)
    if valid_points.size == 0:
        return image

    xyz = valid_points[:, :3]
    class_ids = valid_points[:, 3].astype(np.int32, copy=False)
    uv, distance, mask = project_front_view(xyz, width, height, hfov_deg, vfov_deg, max_range_m)
    class_ids = class_ids[mask]

    order = np.argsort(distance)[::-1]
    radius = max(0, point_size // 2)
    for idx in order:
        px, py = uv[idx]
        x0 = int(round(px)) - radius
        y0 = int(round(py)) - radius
        x1 = int(round(px)) + radius
        y1 = int(round(py)) + radius

        if color_by == "depth":
            t = max(0.0, min(1.0, distance[idx] / max_range_m))
            color = (
                int(255 * (1.0 - t)),
                int(180 * (1.0 - abs(t - 0.5) * 2.0)),
                int(255 * t),
            )
        else:
            color = color_from_id(int(class_ids[idx]))

        draw.ellipse((x0, y0, x1, y1), fill=color)

    return image


def load_camera_boxes(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def draw_image_boxes(image: Image.Image, boxes: list[dict[str, str]]) -> Image.Image:
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
        boundary = box.get("touches_boundary", "0") == "1"

        try:
            color = color_from_id(int(float(label_id)))
        except ValueError:
            color = (255, 80, 80)
        if boundary:
            color = (255, 190, 70)

        text = f"{label} [{label_id}]"
        if actor and actor != "None":
            text += f" {actor}"

        draw.rectangle((min_x, min_y, max_x, max_y), outline=color, width=3)
        text_anchor = (min_x + 4, max(min_y - 18, 0))
        text_bbox = draw.textbbox(text_anchor, text)
        draw.rectangle(text_bbox, fill=color)
        draw.text(text_anchor, text, fill=(255, 255, 255))

    return overlay


def try_parse_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def load_lidar_bboxes(path: Path) -> list[LidarBBox]:
    if not path.exists():
        return []

    boxes: list[LidarBBox] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, skipinitialspace=True)
        for row in reader:
            if not row:
                continue

            row = [item.strip() for item in row]
            timestamp: float | None = None
            label_id: int | None = None
            label_name = "Unknown"
            corners: np.ndarray | None = None

            if len(row) == 11:
                timestamp = float(row[0])
                label_id = try_parse_int(row[1])
                label_name = row[2]
                corner_values: list[float] = []
                for field in row[3:11]:
                    xyz = [value for value in field.split() if value]
                    if len(xyz) != 3:
                        corner_values = []
                        break
                    corner_values.extend(float(value) for value in xyz)
                if len(corner_values) == 24:
                    corners = np.array(corner_values, dtype=np.float32).reshape((8, 3))
            elif len(row) in (26, 27):
                timestamp = float(row[0])
                if len(row) == 27:
                    label_id = try_parse_int(row[1])
                    label_name = row[2]
                    start = 3
                else:
                    label_name = row[1]
                    start = 2
                values = np.array([float(value) for value in row[start:start + 24]], dtype=np.float32)
                if values.size == 24:
                    corners = values.reshape((8, 3))

            if corners is None:
                continue

            boxes.append(
                LidarBBox(
                    timestamp=timestamp,
                    label_id=label_id,
                    label_name=label_name,
                    corners=corners,
                )
            )

    return boxes


def draw_lidar_boxes_on_front_view(
    image: Image.Image,
    boxes: list[LidarBBox],
    width: int,
    height: int,
    hfov_deg: float,
    vfov_deg: float,
    max_range_m: float,
) -> Image.Image:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    for box in boxes:
        uv, _, mask = project_front_view(box.corners, width, height, hfov_deg, vfov_deg, max_range_m)
        if np.count_nonzero(mask) < 2:
            continue

        corners_2d = np.full((8, 2), np.nan, dtype=np.float32)
        corners_2d[mask] = uv

        if box.label_id is None:
            color = color_from_id(abs(hash(box.label_name)) % 256)
        else:
            color = color_from_id(box.label_id)

        for start, end in BOX_EDGES:
            if np.isnan(corners_2d[start]).any() or np.isnan(corners_2d[end]).any():
                continue
            draw.line(
                (
                    float(corners_2d[start, 0]),
                    float(corners_2d[start, 1]),
                    float(corners_2d[end, 0]),
                    float(corners_2d[end, 1]),
                ),
                fill=color,
                width=2,
            )

        visible_points = corners_2d[~np.isnan(corners_2d).any(axis=1)]
        if visible_points.shape[0] > 0:
            anchor_x = float(np.min(visible_points[:, 0]))
            anchor_y = float(np.min(visible_points[:, 1]))
            text = box.label_name if box.label_name else "BBox"
            text_bbox = draw.textbbox((anchor_x, anchor_y), text)
            draw.rectangle(text_bbox, fill=color)
            draw.text((anchor_x, anchor_y), text, fill=(255, 255, 255))

    return overlay


def command_image_bin_to_png(args: argparse.Namespace) -> int:
    output_path = args.output.resolve() if args.output else default_output_path(args.bin_file.resolve(), ".png")

    if args.image_type == "rgb":
        image = read_rgb_bin(args.bin_file, args.width, args.height)
        ensure_parent(output_path)
        image.save(output_path)
    elif args.image_type == "depth":
        depth = read_depth_bin(args.bin_file, args.width, args.height)
        save_depth_png(depth, output_path, args.depth_preview)
    else:
        labels = read_segmentation_bin(args.bin_file, args.width, args.height)
        image = segmentation_to_image(labels, args.segmentation_color)
        ensure_parent(output_path)
        image.save(output_path)

    print(f"Saved {output_path}")
    return 0


def command_pointcloud_bin_to_pcd(args: argparse.Namespace) -> int:
    output_path = args.output.resolve() if args.output else default_output_path(args.bin_file.resolve(), ".pcd")
    points = load_point_cloud(args.bin_file)
    if args.drop_invalid:
        points = filter_points(points, drop_invalid=True)
    write_ascii_pcd(points, output_path)
    print(f"Saved {output_path}")
    return 0


def command_pointcloud_front_view(args: argparse.Namespace) -> int:
    output_path = args.output.resolve() if args.output else default_output_path(args.bin_file.resolve(), ".png")
    points = load_point_cloud(args.bin_file)
    image = render_point_cloud_front_view(
        points,
        width=args.width,
        height=args.height,
        hfov_deg=args.hfov,
        vfov_deg=args.vfov,
        max_range_m=args.max_range,
        color_by=args.color_by,
        point_size=args.point_size,
    )
    ensure_parent(output_path)
    image.save(output_path)
    print(f"Saved {output_path}")
    return 0


def command_overlay_image_bboxes(args: argparse.Namespace) -> int:
    camera_root = args.camera_root.resolve()
    bin_path = camera_root / "Bin_folder" / f"frame_{args.frame:06d}.bin"
    csv_path = camera_root / "BBoxes" / f"frame_{args.frame:06d}.csv"
    output_path = args.output.resolve() if args.output else (camera_root / "BBoxPreview" / f"frame_{args.frame:06d}.png")

    image = read_rgb_bin(bin_path, args.width, args.height)
    boxes = load_camera_boxes(csv_path)
    overlay = draw_image_boxes(image, boxes)
    ensure_parent(output_path)
    overlay.save(output_path)
    print(f"Saved {output_path} with {len(boxes)} boxes")
    return 0


def command_overlay_pointcloud_bboxes(args: argparse.Namespace) -> int:
    lidar_root = args.lidar_root.resolve()
    bin_path = lidar_root / "Bin_folder" / f"frame_{args.frame:06d}.bin"
    bbox_path = lidar_root / "BBoxes" / f"frame_{args.frame:06d}.txt"
    output_path = args.output.resolve() if args.output else (lidar_root / "BBoxPreview" / f"frame_{args.frame:06d}.png")

    points = load_point_cloud(bin_path)
    boxes = load_lidar_bboxes(bbox_path)
    base = render_point_cloud_front_view(
        points,
        width=args.width,
        height=args.height,
        hfov_deg=args.hfov,
        vfov_deg=args.vfov,
        max_range_m=args.max_range,
        color_by="class",
        point_size=args.point_size,
    )
    overlay = draw_lidar_boxes_on_front_view(
        base,
        boxes,
        width=args.width,
        height=args.height,
        hfov_deg=args.hfov,
        vfov_deg=args.vfov,
        max_range_m=args.max_range,
    )
    ensure_parent(output_path)
    overlay.save(output_path)
    print(f"Saved {output_path} with {len(boxes)} boxes")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "image-bin-to-png":
            return command_image_bin_to_png(args)
        if args.command == "pointcloud-bin-to-pcd":
            return command_pointcloud_bin_to_pcd(args)
        if args.command == "pointcloud-front-view":
            return command_pointcloud_front_view(args)
        if args.command == "overlay-image-bboxes":
            return command_overlay_image_bboxes(args)
        if args.command == "overlay-pointcloud-bboxes":
            return command_overlay_pointcloud_bboxes(args)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Unsupported command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
