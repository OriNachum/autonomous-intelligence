---
name: implement
description: Reads a specific plan from docs/plan/ and executes the code changes described within it. Use this when the user says "implement the plan" or "execute the plan".
---

# Plan Executor
This skill acts as the builder. It takes the architectural blueprint (the plan file) and strictly converts it into code changes.

## When to use this skill
- When the user says "implement the plan".
- When the user says "execute [filename]".
- When the user wants to apply the changes defined in a recently generated plan.

## Instructions
1.  **Locate Plan**:
    -   If the user provided a filename, read `docs/plan/[filename]`.
    -   If NO filename is provided, find the **most recent** file in `docs/plan/` and confirm with the user: "Found latest plan: [filename]. Proceed with implementation?"
2.  **Ingest Context**: Read the entire content of the plan file. Treat the "Implementation Steps" section as your primary instruction set.
3.  **Execute Steps**:
    -   Go through the plan item by item.
    -   **Create/Modify Files**: Apply the code changes described.
    -   **Run Commands**: Execute necessary shell commands (e.g., `pip install`, `npm run build`) if explicitly listed.
4.  **Verification**:
    -   After applying changes, check against the "Verification" section of the plan.
    -   Ensure no syntax errors were introduced.
5.  **Update Plan**:
    -   (Optional) Append a "Status: Implemented on [Date]" note to the bottom of the plan file.

## Constraints
-   **Scope**: Do NOT deviate from the plan. If you encounter a logical error in the plan, STOP and report it to the user.
-   **Safety**: If the plan involves deleting files, ask for explicit confirmation before that specific step.