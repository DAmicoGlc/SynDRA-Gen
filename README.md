# SynDRA-Gen

SynDRA-Gen is an Unreal Engine 5.4 application for generating synthetic railway-scene data, including RGB images, depth maps, semantic segmentation masks, LiDAR point clouds, and pedestrian bounding-box annotations.

## Download

The packaged application content is large, so the distributable `Content` bundle is hosted separately.

- Application package and large content download from MEGA: [https://mega.nz/folder/RXkB2JQL#s_Z2oO9QKNU-y2Wf2EaiCA]

When the MEGA package is available, place the downloaded SimulatrixMV folder in the packaged-application location before running SynDRA-Gen.

## Overview

The current runtime workflow is driven by `ASimpleCameraCaptureManager` and its in-game `Acquisition Setup` menu. The application lets the user configure the scene before capture starts, apply the configuration, and then launch a deterministic acquisition run.

At the moment, the implemented runtime configuration covers:

- Weather and lighting toggles
- RGB camera rig selection and placement
- Optional depth-image generation
- Optional semantic-segmentation generation
- Forest mesh family and random seeds
- Pedestrian seed
- Railway surface mesh choices and ballast seed
- Train rail selection and train speed
- Optional flash or beams LiDAR
- LiDAR mounting offsets and presets
- Bounding-box generation

## Customization

SynDRA-Gen is designed around a small set of scenario-customization groups.

### Currently available in the runtime menu

- `Weather and lighting`: fog and night toggles
- `Cameras`: mono or stereo setup, camera count, resolution preset, FOV, and mounting offsets
- `Outputs`: depth-image generation, semantic-segmentation generation, and bounding-box generation
- `Forest`: mesh family plus tree, lower-tree, and grass seeds
- `Pedestrians`: pedestrian seed
- `Railway`: ballast mesh, paired terrain mesh, and ballast rotation seed
- `Train dynamics`: travel rail and train speed
- `LiDAR`: none, flash, or beams; beams count; flash preset; mount offsets

## Runtime workflow

For the end user, SynDRA-Gen is intended to work as an application loop:

1. Open the application.
2. Configure the scene and sensor setup in the `Acquisition Setup` menu.
3. Press `Apply Configuration`.
4. Wait until the configuration status reports ready.
5. Press `Start Acquisition`.
6. Let the run finish and save the generated data.
7. Return to the configuration menu, change the scenario settings, and start a new acquisition run again.

During a run (not during configuration) it is possible to press ESC to close the application or return to the configuration menu.

## Railway surface pairing

Ballast and surrounding-terrain meshes are intended to be used as predefined pairs.

- The runtime menu uses the ballast index as the driving selection.
- The terrain index is assigned automatically as `(ballast index + 1) % number_of_meshes`.

This constraint is intentional because unrelated ballast and terrain meshes can create geometric overlap and visual intersection issues around the railway surface.

## Current outputs

Captured data is written under:

- `Saved/DataAcquired/<timestamp>/`

Typical per-sensor folders are:

- `RGBCamera_Check`, `RGBCamera_Left`, `RGBCamera_Right`
- `DepthCamera_Check`, `DepthCamera_Left`, `DepthCamera_Right`
- `SSCamera_Check`, `SSCamera_Left`, `SSCamera_Right`
- `FlashLidar_Check`
- `BeamsStackLidar_Check`

### Camera folder structure

Each camera folder can contain:

- `Bin_folder`
- `Poses`
- `Times`
- `BBoxes`

### LiDAR folder structure

Each LiDAR folder can contain:

- `Bin_folder`
- `Poses`
- `Times`
- `BBoxes`

## Binary export formats

The helper script in `Helper/syndra_dataset_tools.py` is based on the actual writer implementation in this project.

### RGB images

- File location: `<camera>/Bin_folder/frame_XXXXXX.bin`
- Format: `width * height * 3` bytes
- Channel order: `B`, `G`, `R`

### Depth images

- File location: `<depth-camera>/Bin_folder/frame_XXXXXX.bin`
- Format: `width * height * 2` bytes
- Stored from Unreal render channels as `G`, `R`
- The helper script reconstructs these as a 16-bit grayscale PNG

### Semantic segmentation images

- File location: `<ss-camera>/Bin_folder/frame_XXXXXX.bin`
- Format: `width * height` bytes
- One label byte per pixel

### LiDAR point clouds

- File location: `<lidar>/Bin_folder/frame_XXXXXX.bin`
- Format: one point every 6 `float32` values
- Stored fields: `x`, `y`, `z`, `class_id`, `channel`, `timestamp`
- Coordinates are exported in meters

### Camera bounding boxes

- File location: `<camera>/BBoxes/frame_XXXXXX.csv`
- Contains 2D image coordinates plus 3D box metadata

Current CSV header:

- `label,label_id,actor,min_x,min_y,max_x,max_y,touches_boundary,center_x_m,center_y_m,center_z_m,extent_x_m,extent_y_m,extent_z_m,rot_pitch_deg,rot_yaw_deg,rot_roll_deg,timestamp_s`

### LiDAR bounding boxes

- File location: `<lidar>/BBoxes/frame_XXXXXX.txt`
- Each row stores timestamp, label id, actor name, and the 8 box corners in LiDAR sensor coordinates

## Python post-processing

Use [Helper/syndra_dataset_tools.py](/c:/Users/g.damico/Documents/UnrealProjects/SimulatrixMV/Helper/syndra_dataset_tools.py) to convert and visualize exported data.

Supported tasks:

- Convert RGB, depth, or segmentation `.bin` images to `.png`
- Convert LiDAR `.bin` point clouds to `.pcd`
- Render a front-view image from a LiDAR `.bin` point cloud
- Overlay camera bounding boxes on camera images
- Overlay LiDAR 3D bounding boxes on a point-cloud front-view image

### Requirements

- Python 3
- `numpy`
- `Pillow`

Example install:

```bash
pip install numpy pillow
```

### Example commands

Convert one depth frame to PNG:

```bash
python Helper/syndra_dataset_tools.py image-bin-to-png Saved/DataAcquired/<timestamp>/DepthCamera_Check/Bin_folder/frame_000000.bin --image-type depth --width 1280 --height 960
```

Convert one segmentation frame to PNG:

```bash
python Helper/syndra_dataset_tools.py image-bin-to-png Saved/DataAcquired/<timestamp>/SSCamera_Check/Bin_folder/frame_000000.bin --image-type segmentation --width 1280 --height 960
```

Convert one LiDAR frame to PCD:

```bash
python Helper/syndra_dataset_tools.py pointcloud-bin-to-pcd Saved/DataAcquired/<timestamp>/BeamsStackLidar_Check/Bin_folder/frame_000000.bin
```

Create a front-view image from a LiDAR frame:

```bash
python Helper/syndra_dataset_tools.py pointcloud-front-view Saved/DataAcquired/<timestamp>/BeamsStackLidar_Check/Bin_folder/frame_000000.bin
```

Overlay camera bounding boxes:

```bash
python Helper/syndra_dataset_tools.py overlay-image-bboxes Saved/DataAcquired/<timestamp>/RGBCamera_Check --width 1280 --height 960 --frame 0
```

Overlay LiDAR bounding boxes on the point-cloud front view:

```bash
python Helper/syndra_dataset_tools.py overlay-pointcloud-bboxes Saved/DataAcquired/<timestamp>/BeamsStackLidar_Check --frame 0
```

## Tech stack

- Unreal Engine `5.4`
- C++
- Blueprint
- PCG

## Reference Machine

- Windows 11 operating system and Unreal Engine 5.4
- CPU: 13th Gen Intel(R) Core(TM) i9-13900K CPU (3.00 GHz)
- GPU: NVIDIA GeForce RTX 5080 GPU with 16 GB of dedicated memory
- RAM: 64 GB

## License

Following the existing SynDRA and SynDRA-BBox project licensse, the dataset outputs distributed with SynDRA-Gen are intended to use:

- `Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)`

License reference:
- https://creativecommons.org/licenses/by-nc/4.0/
