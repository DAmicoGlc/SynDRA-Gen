#!/usr/bin/env python3
from __future__ import annotations

import argparse
import colorsys
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import open3d as o3d
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "This script requires Open3D. Install it with: pip install open3d numpy"
    ) from exc


POINT_STRIDE_FLOATS = 6
POINT_DTYPE = np.dtype("<f4")
BOX_EDGES = np.array(
    [
        [0, 1],
        [0, 2],
        [0, 4],
        [1, 3],
        [1, 5],
        [2, 3],
        [2, 6],
        [3, 7],
        [4, 5],
        [4, 6],
        [5, 7],
        [6, 7],
    ],
    dtype=np.int32,
)


@dataclass
class LidarBBox:
    timestamp: float
    label_id: int | None
    label_name: str
    corners: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize SimulatrixMV lidar point clouds and lidar bboxes in Open3D."
    )
    parser.add_argument(
        "lidar_root",
        type=Path,
        help="Path to one lidar folder, e.g. Saved/CameraCheck/.../BeamsStackLidar_Check",
    )
    parser.add_argument(
        "--frame",
        type=int,
        default=0,
        help="Frame index to visualize, e.g. 0 for frame_000000.bin",
    )
    parser.add_argument(
        "--bbox-file",
        type=Path,
        default=None,
        help=(
            "Path to the lidar bbox text file. "
            "Defaults to Content/Dataset/LidarBBoxes<lidar_name>.txt relative to the repo root."
        ),
    )
    parser.add_argument(
        "--bbox-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing lidar bbox text files. "
            "The script will look for LidarBBoxes<lidar_name>.txt inside it."
        ),
    )
    parser.add_argument(
        "--time-tol",
        type=float,
        default=1e-4,
        help="Timestamp tolerance when matching a frame to bbox records.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=0,
        help="Randomly keep at most this many points. Use 0 to keep all points.",
    )
    parser.add_argument(
        "--point-size",
        type=float,
        default=2.0,
        help="Open3D render point size.",
    )
    parser.add_argument(
        "--uniform-color",
        action="store_true",
        help="Draw the whole point cloud in a single color instead of class colors.",
    )
    return parser.parse_args()


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def default_bbox_file(lidar_root: Path) -> Path:
    return repo_root_from_script() / "Content" / "Dataset" / f"LidarBBoxes{lidar_root.name}.txt"


def resolve_bbox_file(lidar_root: Path, bbox_file: Path | None, bbox_dir: Path | None) -> Path:
    if bbox_file is not None:
        return bbox_file.resolve()
    if bbox_dir is not None:
        return bbox_dir.resolve()

    per_run_bbox_dir = lidar_root / "BBoxes"
    if per_run_bbox_dir.exists():
        return per_run_bbox_dir

    return default_bbox_file(lidar_root)


def load_times(times_path: Path) -> list[float]:
    if not times_path.exists():
        raise FileNotFoundError(f"Missing times file: {times_path}")

    timestamps: list[float] = []
    for line in times_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        timestamps.append(float(stripped))
    return timestamps


def load_point_cloud(bin_path: Path) -> np.ndarray:
    if not bin_path.exists():
        raise FileNotFoundError(f"Missing point cloud file: {bin_path}")

    raw = np.fromfile(bin_path, dtype=POINT_DTYPE)
    if raw.size == 0:
        return np.empty((0, POINT_STRIDE_FLOATS), dtype=np.float32)
    if raw.size % POINT_STRIDE_FLOATS != 0:
        raise ValueError(
            f"{bin_path} does not contain a whole number of points: "
            f"{raw.size} float32 values found."
        )
    return raw.reshape((-1, POINT_STRIDE_FLOATS))


def try_parse_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def load_lidar_bboxes(bbox_path: Path, frame_index: int | None = None) -> list[LidarBBox]:
    if bbox_path.is_dir():
        if frame_index is None:
            return []
        bbox_path = bbox_path / f"frame_{frame_index:06d}.txt"

    if not bbox_path.exists():
        return []

    boxes: list[LidarBBox] = []
    with bbox_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, skipinitialspace=True)
        for row in reader:
            if not row:
                continue

            row = [item.strip() for item in row]
            corners: np.ndarray | None = None
            timestamp = float(row[0])

            if len(row) == 11:
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
                if len(row) == 27:
                    label_id = try_parse_int(row[1])
                    label_name = row[2]
                    coord_start = 3
                else:
                    label_id = None
                    label_name = row[1]
                    coord_start = 2

                coords = np.array([float(value) for value in row[coord_start:coord_start + 24]], dtype=np.float32)
                if coords.size == 24:
                    corners = coords.reshape((8, 3))
            else:
                continue

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


def filter_boxes_for_timestamp(
    boxes: list[LidarBBox],
    timestamp: float,
    tolerance: float,
) -> list[LidarBBox]:
    return [box for box in boxes if math.isclose(box.timestamp, timestamp, abs_tol=tolerance)]


def class_id_to_color(class_id: int) -> np.ndarray:
    hue = ((class_id * 0.6180339887498949) % 1.0)
    saturation = 0.65
    value = 0.95
    rgb = colorsys.hsv_to_rgb(hue, saturation, value)
    return np.array(rgb, dtype=np.float64)


def build_point_cloud(points: np.ndarray, uniform_color: bool, max_points: int) -> o3d.geometry.PointCloud:
    valid_mask = np.isfinite(points).all(axis=1)
    valid_mask &= points[:, 3] >= 0
    xyz = points[valid_mask, :3]
    class_ids = points[valid_mask, 3].astype(np.int32, copy=False)

    if max_points > 0 and xyz.shape[0] > max_points:
        rng = np.random.default_rng(42)
        keep = np.sort(rng.choice(xyz.shape[0], size=max_points, replace=False))
        xyz = xyz[keep]
        class_ids = class_ids[keep]

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64, copy=False))

    if xyz.shape[0] == 0:
        return pcd

    if uniform_color:
        colors = np.tile(np.array([[0.85, 0.85, 0.85]], dtype=np.float64), (xyz.shape[0], 1))
    else:
        unique_ids = np.unique(class_ids)
        color_map = {class_id: class_id_to_color(int(class_id)) for class_id in unique_ids}
        colors = np.vstack([color_map[int(class_id)] for class_id in class_ids])

    pcd.colors = o3d.utility.Vector3dVector(colors)
    return pcd


def build_bbox_linesets(boxes: list[LidarBBox]) -> list[o3d.geometry.LineSet]:
    line_sets: list[o3d.geometry.LineSet] = []
    for box in boxes:
        line_set = o3d.geometry.LineSet()
        line_set.points = o3d.utility.Vector3dVector(box.corners.astype(np.float64, copy=False))
        line_set.lines = o3d.utility.Vector2iVector(BOX_EDGES)
        color = class_id_to_color(box.label_id if box.label_id is not None else abs(hash(box.label_name)) % 256)
        line_set.colors = o3d.utility.Vector3dVector(np.tile(color, (BOX_EDGES.shape[0], 1)))
        line_sets.append(line_set)
    return line_sets


def print_summary(
    frame_index: int,
    timestamp: float,
    points: np.ndarray,
    boxes: list[LidarBBox],
) -> None:
    valid_points = int(np.count_nonzero(np.isfinite(points).all(axis=1) & (points[:, 3] >= 0)))
    print(f"Frame: {frame_index:06d}")
    print(f"Timestamp: {timestamp:.6f}")
    print(f"Valid points: {valid_points}")
    print(f"BBoxes: {len(boxes)}")
    for box in boxes:
        label_id = "None" if box.label_id is None else str(box.label_id)
        print(f"  label_id={label_id:>4}  label={box.label_name}")


def main() -> int:
    args = parse_args()
    lidar_root = args.lidar_root.resolve()
    bin_path = lidar_root / "Bin_folder" / f"frame_{args.frame:06d}.bin"
    times_path = lidar_root / "Times" / "times.txt"
    bbox_path = resolve_bbox_file(lidar_root, args.bbox_file, args.bbox_dir)

    timestamps = load_times(times_path)
    if args.frame < 0 or args.frame >= len(timestamps):
        print(
            f"Frame {args.frame} is out of range for {times_path} "
            f"which contains {len(timestamps)} timestamps.",
            file=sys.stderr,
        )
        return 1

    timestamp = timestamps[args.frame]
    points = load_point_cloud(bin_path)
    boxes = load_lidar_bboxes(bbox_path, args.frame)
    if bbox_path.is_file() and bbox_path.name.startswith("LidarBBoxes"):
        boxes = filter_boxes_for_timestamp(boxes, timestamp, args.time_tol)

    print_summary(args.frame, timestamp, points, boxes)
    if not bbox_path.exists():
        print(f"BBox file not found, only the point cloud will be shown: {bbox_path}")

    pcd = build_point_cloud(points, args.uniform_color, args.max_points)
    geometries: list[o3d.geometry.Geometry] = [pcd]
    geometries.extend(build_bbox_linesets(boxes))
    geometries.append(o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0))

    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name=f"{lidar_root.name} frame {args.frame:06d}")
    render_option = vis.get_render_option()
    render_option.point_size = float(args.point_size)
    render_option.background_color = np.array([0.05, 0.05, 0.05], dtype=np.float64)

    for geometry in geometries:
        vis.add_geometry(geometry)

    vis.run()
    vis.destroy_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
