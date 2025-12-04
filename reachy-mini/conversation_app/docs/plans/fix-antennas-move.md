# Investigation: TypeError in move_smoothly_to

## Problem Description
The application crashes with `TypeError: '<' not supported between instances of 'float' and 'str'` during `move_smoothly_to`.
The log indicates `yaw` is `45.0` (float), but `duration` is passed as `'instant'` (string).
The `ActionHandler` normalizes parameters but then uses the original raw `parameters` dict when calling `move_smoothly_to`.

## Hypothesis
1. `ActionHandler.execute` calls `self.gateway.move_smoothly_to(**parameters)` using raw parameters.
2. `ReachyController.move_smoothly_to` receives `duration='instant'`.
3. `move_smoothly_to` tries to compare `t - start_time < duration`, causing the TypeError.

## Proposed Changes

### conversation_app/action_handler.py
- Update `execute` method to use `normalized_params` when calling `self.gateway.move_smoothly_to`.

### conversation_app/reachy_controller.py
- Update `move_smoothly_to` to handle string `duration` inputs using `mappings.name_to_value`, ensuring robustness against non-normalized inputs.

## Verification Plan

### Automated Verification
- Run `reproduce_issue.py` (updated to assert success).
- Since `reproduce_issue.py` mocks dependencies, it verifies the logic in `ReachyController`.
- To verify `ActionHandler`, I would need a more complex test, but the code change is straightforward.

### Manual Verification
- The user can run the system and verify that `move_smoothly_to` with "instant" duration works.
