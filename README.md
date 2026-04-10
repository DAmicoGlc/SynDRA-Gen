# SimulatrixMV

SimulatrixMV is an Unreal Engine 5.4 project for building railway capture runs and generating synthetic RGB, LiDAR, and pedestrian-bounding-box data from a configurable in-game menu.

## Overview

The current workflow is driven by `ASimpleCameraCaptureManager` and its runtime `Acquisition Setup` menu.

From that menu, the user can:

- Toggle fog and night modes
- Configure RGB camera rig type, count, FOV, resolution, and mounting offsets
- Choose forest mesh family and randomization seeds
- Set a pedestrian seed
- Choose ballast mesh, terrain mesh, and ballast rotation seed
- Select the active rail and train speed
- Enable either flash LiDAR, beams LiDAR, or no LiDAR
- Adjust LiDAR mount offsets and presets
- Apply the configuration before starting capture
- Start the run only after configuration is ready

The manager also exposes Blueprint hooks so level-specific setup can happen during configuration and right when the run starts.

## Current Menu Parameters

The runtime menu is divided into the following sections.

### Weather

Available controls:

- `Fog`: `On` or `Off`
- `Night`: `On` or `Off`

Behavior notes:

- Fog and night can both be switched on or off from the runtime menu
- If `Fog` is set to `On`, the `Night` toggle is ignored
- In the current menu behavior, enabling `Fog` disables `Night`

### Cameras

Available controls:

- `Camera Rig`: `Mono` or `Stereo`
- `Mono Camera Count`: `1` or `2` when `Mono` is selected
- `Camera Resolution`: `1K` or `2K`
- `Camera FOV`: `30`, `90`, or `120`
- `Single Camera Y Offset`
- `Left Camera Y Offset`
- `Right Camera Y Offset`
- `Camera Z Offset`
- `Camera Pitch`
- `Left Camera Yaw`
- `Right Camera Yaw`

Behavior notes:

- `Mono` with count `1` creates one RGB camera
- `Mono` with count `2` creates two RGB cameras
- `Stereo` creates left and right RGB cameras
- Offset and yaw rows are shown or hidden automatically based on the selected rig

### Forest

Available controls:

- `Forest Mesh Group`: `0`, `1`, `2`
- `Forest Tree Seed`
- `Forest Lower Tree Seed`
- `Forest Grass Seed`

Mesh group mapping:

- `0`: Black Alder
- `1`: European Hornbeam
- `2`: European Beech

These values are applied during configuration. The manager currently logs them and is ready to forward them into the forest PCG or Blueprint setup.

### Pedestrian

Available controls:

- `Pedestrian Seed`

Current behavior:

- The seed is stored in the manager and included in the applied configuration
- The manager currently logs this value and is ready to forward it into a pedestrian spawn system or Blueprint hook

### Railway Surface

Available controls:

- `Ballast Mesh`: `0` to `5`
- `Terrain Mesh`: `0` to `5`
- `Ballast Rotation Seed`

These values are applied during configuration and are intended to drive ballast and surrounding-terrain scene setup.

### Train Dynamics

Available controls:

- `Travel Rail`: index of the selected spline in `TravelRails`
- `Train Speed`: `5`, `10`, `20`, `30`

Additional train settings currently remain in the manager Details panel rather than the runtime menu:

- `TrainApproachDurationSeconds`
- `TrainStopOffsetCm`
- `TrainBrakingDecelerationCmPerSecondSq`
- `TravelRails`

### Lidar

Available controls:

- `Lidar Type`: `None`, `Flash`, `Beams`
- `Beam Count`: `16`, `32`, `64` when `Beams` is selected
- `Flash Preset`: `ifm O3D-like`, `SICK Visionary-T Mini-like`, `Basler blaze-101-like` when `Flash` is selected
- `Lidar Y Offset`
- `Lidar Z Offset`
- `Lidar Pitch`

Behavior notes:

- LiDAR mount rows are hidden when `Lidar Type` is `None`
- Only the controls relevant to the selected LiDAR type are shown

## Required Level Setup

Before pressing Play, the level still needs a few scene references prepared in the editor.

### SimpleCameraCaptureManager

Place one `SimpleCameraCaptureManager` actor in the level.

Its placed transform matters:

- The manager transform is the train's fixed pre-start location
- When the run begins, the train first moves from that placed transform to the start of the active rail

### Travel Rails

The runtime menu selects a rail by index, but the spline references must already be assigned in the actor Details panel.

Current workflow:

1. Place the spline Blueprint actors in the level.
2. Select the placed `SimpleCameraCaptureManager`.
3. In the Details panel, populate `TravelRails`.
4. For each entry, assign the actual `SplineComponent` from a spline actor placed in the current map.
5. Use the menu's `Travel Rail` value to choose which assigned spline is used for the run.

Important notes:

- Rail splines are not auto-discovered from the level
- `TravelRails` must reference placed spline components, not Blueprint class assets
- If `TravelRails` is empty or the selected index is invalid, train setup is skipped

## Runtime Workflow

Recommended end-to-end workflow:

1. Open the target level.
2. Place and configure the `SimpleCameraCaptureManager`.
3. Assign `TravelRails` in the manager Details panel.
4. Set any non-menu manager properties you need, such as `TrainApproachDurationSeconds`.
5. Press `Play` in Unreal.
6. In the `Acquisition Setup` menu, adjust the parameters for cameras, forest, pedestrian, railway surface, train dynamics, and LiDAR.
7. Press `Apply Configuration`.
8. Wait until the status reports that the configuration is ready.
9. Press `Start Acquisition`.

## Runtime Sequence

After the user presses `Start Acquisition`, the system currently behaves as follows:

1. The manager starts the configured acquisition.
2. The Blueprint event `OnRunPlayPressed` is fired immediately after the menu start action.
3. Input returns to game mode and the configuration widget closes.
4. The train moves from the manager's placed transform to distance `0` of the selected rail.
5. Warmup runs for the configured `WarmupFrames` and `WarmupSeconds`.
6. The first saved frame is captured at rail distance `0`.
7. The train advances along the rail at the configured speed until the stop point is reached.

This `OnRunPlayPressed` event is the intended hook for starting pedestrian movement only when the actual run begins.

## Blueprint Hooks

`ASimpleCameraCaptureManager` currently exposes two Blueprint events for integration:

- `OnBlueprintSceneSetupRequested`
  Use this when `bUseBlueprintSceneSetupHook` is enabled and you want Blueprint logic to apply scene changes during the configuration phase.

- `OnRunPlayPressed`
  Use this to trigger run-start logic exactly when the player presses `Start Acquisition`, for example starting pedestrian movement.

## Current Outputs

The manager currently creates output under `Saved/CameraCheck/<timestamp>/`.

Current capture outputs include:

- RGB camera folders for the active camera setup
- LiDAR folders for the active LiDAR setup
- Per-camera pedestrian bounding box CSV files in each camera's `BBoxes` folder

Current camera folder structure:

- `Bin_folder`
- `Poses`
- `Times`
- `BBoxes`

Current LiDAR folder structure:

- `Bin_folder`
- `Poses`
- `Times`

## Current Limitations

The README now reflects the features implemented in code today. A few older design ideas are not yet exposed in the menu or fully wired.

Notable current limitations:

- Pedestrian configuration in the menu currently includes only `Pedestrian Seed`
- Vehicle configuration is not currently exposed in the runtime menu
- Label configuration is not currently exposed in the runtime menu
- Forest, pedestrian, ballast, and terrain settings are currently logged and prepared for Blueprint or PCG integration rather than being fully driven by built-in runtime systems
- `TrainApproachDurationSeconds`, `TrainStopOffsetCm`, and `TrainBrakingDecelerationCmPerSecondSq` are not yet exposed in the runtime menu
- The README does not cover installation or packaging yet

## Troubleshooting

- `Start Acquisition` appears disabled or does nothing
  Press `Apply Configuration` first and wait for the menu to report that the configuration is ready.

- The train does not move
  Check that `TravelRails` contains valid spline component references from actors placed in the current level, and verify that the selected `Travel Rail` index is valid.

- The train starts in the wrong location before approaching the rail
  Move the placed `SimpleCameraCaptureManager` actor to the desired pre-start position in the level.

- Pedestrians start moving too early
  Trigger pedestrian movement from the manager Blueprint event `OnRunPlayPressed` rather than from configuration-apply logic.

## Tech Stack

- Unreal Engine `5.4`
- C++
- Blueprint
- PCG

## License

License information has not been added yet.
