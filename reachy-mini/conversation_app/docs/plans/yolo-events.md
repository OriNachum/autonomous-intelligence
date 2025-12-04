# YOLO Object Tracking Events Plan

## Goal
Enable the system to track objects and emit specific events when objects enter or leave the field of view. Fix the missing `ultralytics` dependency to ensure YOLO processor works.

## User Review Required
> [!IMPORTANT]
> This plan requires installing `ultralytics` which is a new dependency.

## Proposed Changes

### Dependencies
#### [MODIFY] [requirements.txt](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/requirements.txt)
- Add `ultralytics` to requirements.

### Logic Changes
#### [MODIFY] [manager.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/processors/manager.py)
- Update `ResultFilter.add_result` to return `(stable_set, entered, left)` instead of just `stable_set`.
- Calculate `entered` as `current_stable - last_stable`.
- Calculate `left` as `last_stable - current_stable`.
- Update `ProcessorManager._process_with_processor` to handle the new return signature and add `entered` and `left` lists to the event payload.
- Add specific logging for objects entering and leaving.

## Verification Plan

### Automated Tests
I will create a reproduction script `tests/test_result_filter.py` to verify the `ResultFilter` logic without needing the full video stack.

```python
import unittest
from collections import deque
from conversation_app.processors.manager import ResultFilter

class TestResultFilter(unittest.TestCase):
    def test_entering_leaving(self):
        # Initialize filter
        f = ResultFilter(window_duration=1.0, threshold=0.5)
        
        # 1. Simulate empty state
        # ...
        
        # 2. Simulate object appearing (person)
        # Feed 'person' for > 0.5s
        # Verify 'entered' = {'person'}
        
        # 3. Simulate object disappearing
        # Feed empty for > 0.5s
        # Verify 'left' = {'person'}
```

### Manual Verification
1.  Install dependencies: `pip install -r conversation_app/requirements.txt`
2.  Run the test script: `python3 tests/test_result_filter.py`
3.  (Optional) Run the full gateway and show objects to the camera, verifying logs show "Entered: ..." and "Left: ...".
