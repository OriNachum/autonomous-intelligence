# Development Plans

This directory contains design documents and implementation plans for QQ features and architecture changes.

## Status Overview

| Plan | Status | Description |
|------|--------|-------------|
| [Agents Infrastructure](agents-infra.md) | ✅ Implemented | Infrastructure for agents, including folder structure and dynamic prompt loading. |
| [Graph Agent Refactoring](graph-plan.md) | ✅ Implemented | Decoupling Entity and Relationship extraction into separate agents. |
| [Strands Agent + OpenAI Model](strands-agent-openai-model.md) | ✅ Implemented | Migration to Strands Agent framework with OpenAI-compatible model. |
| [Strands Finish](strands-finish.md) | ✅ Implemented | Completion of Strands Agent integration. |
| [Files Suite](files_suite.md) | ✅ Implemented | File operations tools (read_file, list_files, set_directory). |
| [DOCX/PDF Support](docx-pdf-to-markdown-support.md) | ✅ Implemented | Document conversion for binary file formats. |
| [Read Sliding Window](read_sliding_window.md) | ✅ Implemented | Sliding window mechanism for reading large files. |
| [Parallel Work](parallel-work.md) | ✅ Implemented | Session-based isolation for parallel QQ execution. |
| [Recursive Calling](recursive-calling.md) | ✅ Implemented | Sub-agent system for task delegation and parallel execution. |
| [File Analyzer Agent](analyzer-agent.md) | ✅ Implemented | Deep file analysis tool that internalizes file contents into memory and knowledge graph. |

## Creating New Plans

1.  Create a new markdown file in this directory (e.g., `feature-name.md`).
2.  Follow the template:
    -   **Goal**: High-level objective.
    -   **Current State**: What exists now.
    -   **Proposed Changes**: Detailed technical design.
    -   **Verification**: How to test the changes.
3.  Add the new plan to the table above.
