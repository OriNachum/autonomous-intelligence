# Tool Definition Schema

This document describes the schema for defining tools in the repository.

## Tool Definition JSON Structure

```json
{
  "name": "tool_name",
  "description": "Brief description of what the tool does",
  "parameters": {
    "required": [
      {
        "name": "param_name",
        "type": "string|number|boolean|array|object",
        "description": "Parameter description"
      }
    ],
    "optional": [
      {
        "name": "param_name",
        "type": "string|number|boolean|array|object",
        "default": "default_value",
        "description": "Parameter description"
      }
    ]
  },
  "execution": {
    "type": "script",
    "script_file": "path/to/script.py"
  }
}
```

## Execution Type

All tools use script files for execution:
- `type`: "script"
- `script_file`: Relative path to script file from tools_repository/scripts/
- The script should define an async `execute(make_request, create_head_pose, params)` function
- Returns Dict[str, Any]

## Examples

### Simple GET Request
```json
{
  "name": "get_robot_state",
  "description": "Get the current full state of the Reachy Mini robot",
  "parameters": {
    "required": [],
    "optional": []
  },
  "execution": {
    "type": "script",
    "script_file": "get_robot_state.py"
  }
}
```

### Complex Operation (Script)
```json
{
  "name": "express_emotion",
  "description": "Make the robot express an emotion using head and antenna movements",
  "parameters": {
    "required": [
      {
        "name": "emotion",
        "type": "string",
        "description": "One of: happy, sad, curious, surprised, confused, neutral"
      }
    ],
    "optional": []
  },
  "execution": {
    "type": "script",
    "script_file": "express_emotion.py"
  }
}
```

