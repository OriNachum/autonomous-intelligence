---
name: plan
description: Generates a detailed architectural or execution plan and saves it to docs/plan/. Use this ONLY when the user explicitly asks to "plan" or "create a plan".
---

# Plan Generator
This skill captures the user's intent, formulates a comprehensive step-by-step plan, and persists it to a markdown file for documentation and future reference.

## When to use this skill
- When the user says "I want to plan".
- When the user says "create a plan" or "draft a plan".
- When the user asks to "plan" a specific feature or refactor.

## Instructions
1.  **Analyze Context**: Review the conversation history and the user's specific request to understand the scope (e.g., new feature, refactor, bug fix).
2.  **Formulate Plan**: Create a structured plan including:
    -   **Objective**: High-level goal.
    -   **Context**: Why we are doing this.
    -   **Implementation Steps**: Detailed breakdown of tasks (files to create, code to modify, commands to run).
    -   **Verification**: How to test the plan.
3.  **Generate Filename**: Create a descriptive filename with a timestamp to prevent overwrites.
    -   Format: `docs/plan/YYYY-MM-DD-topic-name.md`
    -   *Example*: `docs/plan/2026-02-01-nova-sonic-integration.md`
4.  **Write File**: Save the formatted plan content to the generated path.
5.  **STOP**:
    -   **CRITICAL**: Do not execute the plan.
    -   Do not write code (other than the plan file).
    -   Confirm to the user: "Plan saved to [filename]." and terminate the turn.

## Constraints
-   **Output Location**: MUST be inside `docs/plan/`.
-   **Action Limit**: ONLY write the plan file. DO NOT implement the steps.
-   **Tone**: Technical, concise, and structured.

# Remember

The user request is the plan and save it to docs/plans/*.md
*.md is your definition of done and stop after that.