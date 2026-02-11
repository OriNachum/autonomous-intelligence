# Autonomous Coding Agents – Project Conventions
# This file documents conventions and workflows for agentic coding assistants
# (e.g., QQ, custom agents) that operate within this repository.
# It is intended to be used as a reference for building, linting, testing,
# and maintaining code quality. The file is deliberately verbose (~150 lines)
# to serve as a comprehensive guide for future agents.

## 1. Development Workflow
### Build / Install
- Use `pip install -e .[dev]` to install the package in editable mode with
  development dependencies (test, lint, type‑check tools).
- Keep a `requirements-dev.txt` that pins exact versions of linting and testing
  tools; regenerate with `pip freeze > requirements-dev.txt` when updating
  dependencies.
- For reproducible environments, a `Dockerfile` is provided; build with
  `docker build -t autonomous‑intelligence .`.

## Linting
- **ruff** is the primary linter/formatter.
  - Run `ruff check .` to perform static analysis and catch style violations.
  - Run `ruff format .` to auto‑format code; this command should be part of the
    pre‑commit hook.
- **black** is used for opinionated code formatting.
  - Run `black .` to reformat the entire codebase.
- **isort** orders imports; run `isort .` to enforce import ordering rules.
- Integrate both into the pre‑commit framework (see “Pre‑commit Hooks” below).

## Testing
- Primary test runner is **pytest**.
  - Execute `pytest` to discover and run all tests.
  - For CI pipelines, use `pytest --maxfail=1 --disable-warnings -q`.
- **Single‑test execution**:  
  - Syntax: `pytest <path/to/test_file.py>::<ClassOrFunction>::<method_name>`  
  - Example: `pytest tests/test_processing.py::ProcessTests::test_parsing`  
  - To run only the first failing test repeatedly:  
    ```bash
    while true; do
      pytest --maxfail=1 -x
      sleep 1
    done
    ```
- Use `--tb=short` to keep tracebacks concise; enable `--strict-metadata`
  to enforce type‑checking of test fixtures.

## Code Style Guidelines
### Imports
- Place standard‑library imports first, followed by third‑party, then internal
  imports.
- Use absolute imports; avoid wildcard (`*`) imports.
- Group imports by type and separate groups with a blank line.
- Prefer `import X` over `from X import *`.

### Formatting
- Max line length: **100 characters** (unless a clear reason exists).
- Trailing commas are required in multi‑line structures.
- End files with a single newline character.
- Use UTF‑8 encoding for all source files.

### File Structure
- Keep modules small and focused; each module should implement a single
  conceptual responsibility.
- Place tests in a parallel `tests/` directory; use descriptive file names.
- Keep configuration files (`pyproject.toml`, `.ruff.toml`, `.flake8`) at the
  repository root.

### Naming Conventions
- Functions, methods, and variables: `snake_case`.
- Classes: `PascalCase`.
- Constants: `ALL_CAPS`.
- Private helpers: prefix with `_`.
- Test classes/functions: prefix with `Test`/`test_`.

### Types & Annotations
- Add type hints to all public functions, methods, and class attributes.
- Use `typing.Union`, `typing.Optional`, and `typing.List` appropriately.
- For simple dicts, prefer `TypedDict`; for enums, use `Enum`.
- Avoid `Any`; if unavoidable, add a comment explaining why.

### Error Handling
- Define custom exception classes in a dedicated `exceptions.py` module.
- Raise specific exceptions rather than generic `Exception`.
- Do not use bare `except:`; always bind to a concrete exception type.
- Log errors with appropriate severity (`debug`, `info`, `warning`, `error`);
  avoid printing raw tracebacks to stdout.

### Logging
- Configure a module‑level logger: `logger = logging.getLogger(__name__)`.
- Use parameterized logging statements; include contextual data.
- In production, route logs to a structured log sink (e.g., JSON file);
  suppress `debug` level by default.

### Testing & Coverage
- Aim for **≥80 %** test coverage on newly modified modules.
- Use `pytest-cov` to generate coverage reports: `pytest --cov=.
- Enforce a minimum coverage threshold in CI (`--cov-fail-under=80`).
- Structure tests using fixtures and `@pytest.mark.parametrize` for reuse.

## 3. Dependency Management
- Use `pip-tools` to manage pinned dependencies in `requirements.in`.
- Run `pip-compile` to generate `requirements.txt`.
- Run `pip-sync` to ensure the environment matches `requirements.txt`.
- Keep `requirements-dev.in` for development‑only dependencies.

## 4. Pre‑commit Hooks
- Install with `pre-commit install`.
- Hooks include: `ruff`, `ruff-format`, `black`, `isort`, `mypy`, `bandit`,
  `pylint`.
- Run `pre-commit run --all-files` locally before committing.
- CI enforces that all hooks pass before merging.

## 5. Version Control & Collaboration
- Commit messages follow **Conventional Commits** (`feat:`, `fix:`, `docs:`…).
- Use feature branches; prefix branch names with `feature/`, `bugfix/`, or
  `refactor/`.
- Pull requests require at least **one** approving review; automated checks
  (lint, test, type) must pass.
- Keep CHANGELOG.md updated; use `towncrier` for version bumping.

## 6. CI / Continuous Integration
- GitHub Actions runs on every push and PR:
  - `lint` job runs ruff & black.
  - `type-check` job runs mypy.
  - `test` job runs pytest with coverage.
  - `build` job verifies packaging and dependency installation.
- Secrets (API keys, passwords) are stored in GitHub Secrets and never
  hard‑coded.

## 7. Cursor & Copilot Integration
- No `.cursor*` or `.copilot*` configuration files are present in the repo.
- When using external AI assistants (e.g., QQ, Cursor), respect the
  repository‑level style and naming conventions.
- If a rule or restriction is discovered later, update this file accordingly.

## 8. Common Agent Commands
- **Start a new session**: `qq` (default agent) or specify `--agent <name>`.
- **Resume a saved session**: `qq --session <session_id>`.
- **Interrupt & restart**: `qq --clear-history` then re‑issue the prompt.
- **Inspect memory**: `qq --memory-inspect` or `memory-read <key>`.
- **Read a file**: `read /path/to/file.py` (internal command) or `cat` via shell.
- **Write/overwrite a file**: `write <content> /path/to/file.py`.
- **Delete a file**: `delete /path/to/file.py`.
- **Run a shell command**: `bash -c "<command>"` or `!<command>` in the REPL.
- **Read file length**: `wc -l /path/to/file.py`.
- **Create new dataset files**: `qq -m "Prompt for JSONL"`; the assistant
  will generate JSONL lines automatically.

## 9. Example: Single‑Test Execution
- Command to run a single unit test:  
  `pytest path/to/file.py::Class::test_method --no-header --tb=no -q`
- To repeatedly retry until passage:  
  ```bash
  while ! pytest path/to/file.py::Class::test_method --no-header -q; do
    echo "Test failed; retrying..."
    sleep 1
  done
  ```
- Useful for rapid iteration when debugging a specific assertion failure.

## 10. Documentation Conventions
- Docstrings follow the **Google** style:
  - `Args:`
  - `Returns:`
  - `Raises:`
- Include type information in the docstring when the function signature
  does not make it obvious.
- Link to relevant types or modules using backticks (`` `module.function` ``).

## 11. Security & Safety
- Sanitize all external inputs before parsing or executing.
- Avoid `eval`, `exec`, or similar dangerous functions; use safe parsers instead.
- Sensitive data (API keys, credentials) must never be hard‑coded; retrieve
  from environment variables or secret management services.
- Ensure any code that writes to the filesystem respects permissions;
  prefer `os.makedirs(..., exist_ok=True)` and `open(..., "a")` with proper
  mode flags.
- Validate file paths with `os.path.abspath` and compare against an
  allowed‑paths whitelist before accessing.

## 12. Performance Considerations
- Prefer **vectorized** operations or list comprehensions over explicit loops
  where possible.
- Cache expensive computations with `functools.lru_cache(maxsize=128)`.
- When scaling out, partition work across multiple agents using the
  `delegate_task` mechanism; ensure each agent receives a unique `resource_range`.
- Monitor GPU memory usage (`nvidia‑smi`) during heavy training or fine‑tuning;
  set `CUDA_VISIBLE_DEVICES` appropriately.

## 13. Debugging & Inspection
- Use `breakpoint()` or `pdb.set_trace()` sparingly; prefer logging at
  appropriate levels for production‑safe debugging.
- For large data structures, `pprint` or `rich.pprint` can provide readable dumps.
- When debugging agent state, query memory via `memory-get <key>` or use
  `read /path/to/file.jsonl | tail -n 20`.

## 13. Documentation Review Process
- All new public APIs must include updated docstrings and be referenced in
  the project's `README.md`.
- Documentation PRs are reviewed with the same rigor as code changes;
  they must pass a `docsstyle` lint check.

## 14. Updating this File
- Any change to conventions, commands, or guidelines must be accompanied
  by a short rationale in the commit message.
- When adding new commands or deprecating old ones, update this file
  promptly to avoid confusion for future agents.

-- End of AGENTS.md --