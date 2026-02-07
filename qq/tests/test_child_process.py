"""Tests for the ChildProcess service module."""

import os
import pytest
from unittest.mock import patch, MagicMock

from qq.services.child_process import ChildProcess, ChildResult


class TestChildResult:
    """Tests for ChildResult dataclass."""

    def test_child_result_defaults(self):
        result = ChildResult(success=True, output="test output")
        assert result.success is True
        assert result.output == "test output"
        assert result.error is None
        assert result.exit_code == 0
        assert result.agent == "default"
        assert result.task == ""

    def test_child_result_with_error(self):
        result = ChildResult(
            success=False,
            output="",
            error="Something went wrong",
            exit_code=1,
            agent="coder",
            task="write code",
        )
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.exit_code == 1
        assert result.agent == "coder"


class TestChildProcess:
    """Tests for ChildProcess service."""

    def test_init_defaults(self):
        cp = ChildProcess()
        assert cp.default_timeout == 300
        assert cp.max_parallel == 5
        assert cp.max_depth == 3
        assert cp.max_output_size == 8000

    def test_init_custom_values(self):
        cp = ChildProcess(
            default_timeout=60,
            max_parallel=10,
            max_depth=5,
            max_output_size=10000,
        )
        assert cp.default_timeout == 60
        assert cp.max_parallel == 10
        assert cp.max_depth == 5
        assert cp.max_output_size == 10000

    def test_init_from_env(self):
        with patch.dict(os.environ, {
            "QQ_CHILD_TIMEOUT": "120",
            "QQ_MAX_PARALLEL": "8",
            "QQ_MAX_DEPTH": "4",
            "QQ_MAX_OUTPUT": "20000",
        }):
            cp = ChildProcess()
            assert cp.default_timeout == 120
            assert cp.max_parallel == 8
            assert cp.max_depth == 4
            assert cp.max_output_size == 20000

    def test_get_current_depth_default(self):
        cp = ChildProcess()
        # Ensure clean env
        os.environ.pop("QQ_RECURSION_DEPTH", None)
        assert cp._get_current_depth() == 0

    def test_get_current_depth_from_env(self):
        cp = ChildProcess()
        with patch.dict(os.environ, {"QQ_RECURSION_DEPTH": "2"}):
            assert cp._get_current_depth() == 2

    def test_spawn_agent_depth_exceeded(self):
        cp = ChildProcess(max_depth=2)
        with patch.dict(os.environ, {"QQ_RECURSION_DEPTH": "2"}):
            result = cp.spawn_agent("test task")
            assert result.success is False
            assert "depth" in result.error.lower()
            assert "exceeded" in result.error.lower()

    def test_build_command_simple(self):
        cp = ChildProcess(qq_executable="/usr/bin/qq")
        cmd = cp._build_command("test task", "default")
        assert cmd == ["/usr/bin/qq", "--agent", "default", "--new-session", "-m", "test task"]

    def test_build_command_module_exec(self):
        cp = ChildProcess(qq_executable="python -m qq")
        cmd = cp._build_command("test task", "coder")
        assert cmd == ["python", "-m", "qq", "--agent", "coder", "--new-session", "-m", "test task"]

    def test_child_env_increments_depth(self):
        cp = ChildProcess()
        os.environ.pop("QQ_RECURSION_DEPTH", None)
        env = cp._child_env()
        assert env["QQ_RECURSION_DEPTH"] == "1"

    def test_child_env_increments_existing_depth(self):
        cp = ChildProcess()
        with patch.dict(os.environ, {"QQ_RECURSION_DEPTH": "2"}):
            env = cp._child_env()
            assert env["QQ_RECURSION_DEPTH"] == "3"

    def test_child_env_removes_session_id(self):
        cp = ChildProcess()
        with patch.dict(os.environ, {"QQ_SESSION_ID": "test-session"}):
            env = cp._child_env()
            assert "QQ_SESSION_ID" not in env

    @patch("subprocess.run")
    def test_spawn_agent_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Hello from child",
            stderr="",
        )
        cp = ChildProcess(qq_executable="qq")
        result = cp.spawn_agent("Say hello", agent="default")

        assert result.success is True
        assert result.output == "Hello from child"
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_spawn_agent_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error occurred",
        )
        cp = ChildProcess(qq_executable="qq")
        result = cp.spawn_agent("Do something")

        assert result.success is False
        assert result.error == "Error occurred"
        assert result.exit_code == 1

    @patch("subprocess.run")
    def test_spawn_agent_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="qq", timeout=5)

        cp = ChildProcess(qq_executable="qq", default_timeout=5)
        result = cp.spawn_agent("Long task")

        assert result.success is False
        assert "timed out" in result.error.lower()
        assert result.exit_code == -1

    @patch("subprocess.run")
    def test_spawn_agent_output_truncation(self, mock_run):
        long_output = "x" * 100000
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=long_output,
            stderr="",
        )
        cp = ChildProcess(qq_executable="qq", max_output_size=1000)
        result = cp.spawn_agent("Generate lots of output")

        assert result.success is True
        assert len(result.output) < len(long_output)
        assert "truncated" in result.output.lower()

    @patch.object(ChildProcess, "spawn_agent")
    def test_run_parallel(self, mock_spawn):
        mock_spawn.side_effect = [
            ChildResult(success=True, output="Result 1", task="Task 1"),
            ChildResult(success=True, output="Result 2", task="Task 2"),
        ]

        cp = ChildProcess()
        tasks = [
            {"task": "Task 1"},
            {"task": "Task 2", "agent": "coder"},
        ]
        results = cp.run_parallel(tasks)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert mock_spawn.call_count == 2

    @patch.object(ChildProcess, "spawn_agent")
    def test_run_parallel_preserves_order(self, mock_spawn):
        # Simulate tasks completing in reverse order
        def delayed_spawn(task, agent="default", **kwargs):
            import time
            if "first" in task:
                time.sleep(0.1)  # First task takes longer
            return ChildResult(success=True, output=task, task=task)

        mock_spawn.side_effect = delayed_spawn

        cp = ChildProcess()
        tasks = [
            {"task": "first task"},
            {"task": "second task"},
        ]
        results = cp.run_parallel(tasks)

        # Results should be in input order, not completion order
        assert results[0].task == "first task"
        assert results[1].task == "second task"


class TestAgentParameterValidation:
    """Tests for agent parameter validation (fixes Agent object passing bug)."""

    @patch("subprocess.run")
    def test_spawn_agent_with_agent_object(self, mock_run):
        """Test that passing an Agent object instead of string is handled gracefully."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )

        # Create a mock Agent object (like strands.agent.agent.Agent)
        mock_agent = MagicMock()
        mock_agent.name = "coder"

        cp = ChildProcess(qq_executable="qq")
        result = cp.spawn_agent("test task", agent=mock_agent)

        # Should succeed by extracting agent.name
        assert result.success is True
        # Verify the command used the string name, not the object
        call_args = mock_run.call_args
        cmd = call_args[0][0]  # First positional arg is the command list
        assert "coder" in cmd

    @patch("subprocess.run")
    def test_spawn_agent_with_object_no_name(self, mock_run):
        """Test that passing an object without .name falls back to 'default'."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )

        # Object without .name attribute
        mock_agent = MagicMock(spec=[])

        cp = ChildProcess(qq_executable="qq")
        result = cp.spawn_agent("test task", agent=mock_agent)

        # Should succeed using default agent
        assert result.success is True
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "default" in cmd

    def test_spawn_agent_with_invalid_task_type(self):
        """Test that passing non-string task returns error."""
        cp = ChildProcess(qq_executable="qq")

        # Pass a dict instead of string for task
        result = cp.spawn_agent(task={"invalid": "task"}, agent="default")

        assert result.success is False
        assert "must be a string" in result.error


class TestFindQQExecutable:
    """Tests for executable discovery."""

    def test_find_qq_executable_fallback(self):
        # When no qq is found, should fallback to module execution
        with patch("shutil.which", return_value=None):
            with patch("pathlib.Path.exists", return_value=False):
                cp = ChildProcess()
                assert "-m qq" in cp.qq_executable or "qq" in cp.qq_executable
