# Global Movement Loop Integration Plan

## Goal
Integrate `reachy_controller.py` and `movement_manager.py` into a unified system where a single constant movement loop handles all robot actuation. This allows for merging different movement sets (e.g., base poses, idle animations, gestures) seamlessly.

## Current State Analysis
- **`ReachyController`**: Directly controls `ReachyMini`. Contains blocking methods like `move_smoothly_to` that run their own loops, preventing other movements (like idle animations) from running concurrently.
- **`MovementManager`**: Runs a background thread `_loop` that currently only handles antenna movements in `WAITING` mode.
- **Conflict**: The two systems fight for control. `move_smoothly_to` blocks the main thread and overrides the background loop. Callbacks (`lock_head_pose`) are used to patch the state synchronization.

## Proposed Architecture

### 1. Unified Movement Loop (`MovementManager`)
The `MovementManager` will own the single "heartbeat" loop of the robot (running at ~50Hz).
It will manage a stack of **Movement Layers**.

In each tick of the loop:
1.  Start with a base robot state (neutral or last known).
2.  Iterate through active **Movement Layers**.
3.  Each layer calculates its contribution (absolute pose or additive delta) based on the current time/state.
4.  Combine the results to form the final target pose.
5.  Send the final target to `ReachyMini`.

### 2. Movement Layers
We will introduce a `MovementLayer` abstract base class (or protocol).

**Types of Layers:**
-   **`BasePoseLayer`**: Maintains the primary target position (head direction, body yaw). Handles smooth interpolation (easing) when the target changes.
-   **`IdleLayer`**: Adds continuous background movements (e.g., breathing, antenna wiggling) when active.
-   **`GestureLayer`**: Plays specific one-off trajectories (e.g., "nod", "shake", "look_surprised") and then deactivates or fades out.

### 3. Updated `ReachyController`
`ReachyController` will no longer run movement loops. Instead, it will act as the high-level API to manipulate the `MovementManager`'s layers.

-   `move_smoothly_to(...)` -> Updates the target of the `BasePoseLayer`. Returns immediately (non-blocking).
-   `set_mode(...)` -> Enables/Disables the `IdleLayer`.
-   `perform_gesture(...)` -> Adds a `GestureLayer` to the stack.

## Detailed Implementation Steps

### Step 1: Define Movement Data Structures
Create simple data structures to represent the robot's state:
```python
@dataclass
class RobotPose:
    roll: float
    pitch: float
    yaw: float
    antennas: Tuple[float, float]
    body_yaw: float
    # ... helper methods for addition/blending
```

### Step 2: Refactor `MovementManager`
-   Update `MovementManager` to initialize `ReachyMini` (or take ownership of the control loop).
-   Implement the `_loop` to handle the full `RobotPose`.
-   Implement the Layer composition logic.

```python
class MovementManager:
    def _loop(self):
        while self.running:
            # 1. Base Pose
            final_pose = self.base_layer.get_pose(time.time())
            
            # 2. Apply Overlays
            for layer in self.overlay_layers:
                if layer.is_active():
                    final_pose = layer.apply(final_pose, time.time())
            
            # 3. Send to Robot
            self.mini.set_target(...)
            time.sleep(self.period)
```

### Step 3: Implement Layers
-   **`BaseLayer`**: Needs logic to interpolate from `current_pose` to `target_pose` over `duration`.
-   **`OscillationLayer`** (for antennas): Port the existing `WAITING` mode logic here.

### Step 4: Update `ReachyController`
-   Remove `move_smoothly_to` loop.
-   Replace it with calls to `movement_manager.set_target(...)`.
-   Remove `post_movement_callbacks` (no longer needed as state is continuous).

## Migration Strategy

1.  **Modify `MovementManager` first**: Add the layer infrastructure but keep it compatible with existing `reachy_controller` usage if possible, or do a hard switch.
2.  **Update `ReachyController`**: Strip out the blocking loops and connect to `MovementManager`.
3.  **Update `app.py`**: Ensure `MovementManager` is started and `ReachyController` is correctly linked.

## Benefits
-   **Non-blocking**: The main application thread is free to process events while the robot moves.
-   **Composition**: Can nod the head while tracking a face and wiggling antennas simultaneously.
-   **Smoothness**: A constant control loop ensures smoother transitions and avoids "fighting" between different control sources.
