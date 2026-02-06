"""Tests for the TaskQueue system."""

import os
import pytest
from unittest.mock import MagicMock, patch

from qq.services.task_queue import TaskQueue, QueuedTask, TaskStatus, QueueFullError
from qq.services.child_process import ChildProcess, ChildResult


@pytest.fixture
def mock_child_process():
    """Create a mock ChildProcess that returns successful results."""
    cp = MagicMock(spec=ChildProcess)
    cp.max_queued = 10
    cp.max_parallel = 5
    cp.max_depth = 3
    cp._get_current_depth.return_value = 0

    def mock_spawn(task, agent="default", timeout=None, working_dir=None, initial_context=None):
        return ChildResult(
            success=True,
            output=f"Result for: {task}",
            error=None,
            exit_code=0,
            agent=agent,
            task=task,
            notes_id=None,
        )

    cp.spawn_agent.side_effect = mock_spawn
    return cp


@pytest.fixture
def task_queue(mock_child_process):
    """Create a TaskQueue with mock child process."""
    return TaskQueue(mock_child_process, max_queued=10, max_parallel=5)


class TestTaskQueueBasic:
    """Test basic queue operations."""

    def test_queue_single_task(self, task_queue):
        """Test queuing a single task."""
        task_id = task_queue.queue_task("test task")
        assert task_id.startswith("task_")
        assert task_queue.pending_count() == 1

    def test_queue_returns_unique_ids(self, task_queue):
        """Test that each queued task gets a unique ID."""
        id1 = task_queue.queue_task("task 1")
        id2 = task_queue.queue_task("task 2")
        id3 = task_queue.queue_task("task 3")

        assert len({id1, id2, id3}) == 3  # All unique
        assert task_queue.pending_count() == 3

    def test_queue_with_agent(self, task_queue):
        """Test queuing a task with a specific agent."""
        task_id = task_queue.queue_task("code review", agent="coder")
        assert task_queue.pending_count() == 1
        assert task_queue._results[task_id].agent == "coder"

    def test_queue_with_priority(self, task_queue):
        """Test queuing a task with priority."""
        task_id = task_queue.queue_task("urgent task", priority=10)
        assert task_queue._results[task_id].priority == 10

    def test_queue_with_metadata(self, task_queue):
        """Test queuing a task with metadata."""
        metadata = {"source": "test", "category": "unit"}
        task_id = task_queue.queue_task("task", metadata=metadata)
        assert task_queue._results[task_id].metadata == metadata


class TestQueueFullError:
    """Test queue capacity limits."""

    def test_queue_full_error(self, mock_child_process):
        """Test that QueueFullError is raised when queue is full."""
        queue = TaskQueue(mock_child_process, max_queued=2, max_parallel=1)

        queue.queue_task("task 1")
        queue.queue_task("task 2")

        with pytest.raises(QueueFullError) as exc_info:
            queue.queue_task("task 3")

        assert "full" in str(exc_info.value).lower()
        assert "2" in str(exc_info.value)  # max_queued value

    def test_queue_accepts_after_clear(self, mock_child_process):
        """Test that queue accepts tasks after being cleared."""
        queue = TaskQueue(mock_child_process, max_queued=2, max_parallel=1)

        queue.queue_task("task 1")
        queue.queue_task("task 2")
        queue.clear()

        # Should work now
        task_id = queue.queue_task("task 3")
        assert task_id is not None


class TestBatchQueue:
    """Test batch queueing."""

    def test_batch_queue(self, task_queue):
        """Test batch queueing multiple tasks."""
        task_ids = task_queue.queue_batch([
            {"task": "task1"},
            {"task": "task2", "agent": "coder"},
            {"task": "task3", "priority": 5},
        ])

        assert len(task_ids) == 3
        assert task_queue.pending_count() == 3

    def test_batch_queue_respects_limit(self, mock_child_process):
        """Test batch queueing respects max_queued."""
        queue = TaskQueue(mock_child_process, max_queued=2, max_parallel=1)

        with pytest.raises(QueueFullError):
            queue.queue_batch([
                {"task": "task1"},
                {"task": "task2"},
                {"task": "task3"},
            ])

        # First two should have been queued
        assert queue.pending_count() == 2


class TestExecuteAll:
    """Test task execution."""

    def test_execute_all_empty_queue(self, task_queue):
        """Test executing an empty queue."""
        results = task_queue.execute_all()
        assert results == []

    def test_execute_all_single_task(self, task_queue, mock_child_process):
        """Test executing a single task."""
        task_queue.queue_task("test task")
        results = task_queue.execute_all()

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].task == "test task"
        mock_child_process.spawn_agent.assert_called_once()

    def test_execute_all_multiple_tasks(self, task_queue, mock_child_process):
        """Test executing multiple tasks."""
        task_queue.queue_task("task 1")
        task_queue.queue_task("task 2")
        task_queue.queue_task("task 3")

        results = task_queue.execute_all()

        assert len(results) == 3
        assert all(r.success for r in results)
        assert mock_child_process.spawn_agent.call_count == 3

    def test_execute_all_clears_queue(self, task_queue):
        """Test that execute_all clears the pending queue."""
        task_queue.queue_task("task 1")
        task_queue.queue_task("task 2")

        assert task_queue.pending_count() == 2
        task_queue.execute_all()
        assert task_queue.pending_count() == 0

    def test_execute_all_updates_status(self, task_queue):
        """Test that task status is updated after execution."""
        task_id = task_queue.queue_task("test task")

        assert task_queue.get_status(task_id) == TaskStatus.PENDING

        task_queue.execute_all()

        assert task_queue.get_status(task_id) == TaskStatus.COMPLETED


class TestPriorityOrdering:
    """Test priority-based execution order."""

    def test_priority_ordering(self, mock_child_process):
        """Test tasks execute in priority order (higher first)."""
        execution_order = []

        def mock_spawn(task, agent="default", timeout=None, working_dir=None, initial_context=None):
            execution_order.append(task)
            return ChildResult(
                success=True,
                output=f"Result for: {task}",
                error=None,
                exit_code=0,
                agent=agent,
                task=task,
                notes_id=None,
            )

        mock_child_process.spawn_agent.side_effect = mock_spawn

        # Use max_parallel=1 to ensure sequential execution for ordering test
        queue = TaskQueue(mock_child_process, max_queued=10, max_parallel=1)

        queue.queue_task("low", priority=0)
        queue.queue_task("high", priority=10)
        queue.queue_task("medium", priority=5)

        results = queue.execute_all()

        # Results should be in priority order
        assert results[0].task == "high"
        assert results[1].task == "medium"
        assert results[2].task == "low"


class TestErrorHandling:
    """Test error handling during execution."""

    def test_failed_task_status(self, mock_child_process):
        """Test that failed tasks are marked as FAILED."""

        def mock_spawn(task, agent="default", timeout=None, working_dir=None, initial_context=None):
            return ChildResult(
                success=False,
                output="",
                error="Task failed",
                exit_code=1,
                agent=agent,
                task=task,
                notes_id=None,
            )

        mock_child_process.spawn_agent.side_effect = mock_spawn
        queue = TaskQueue(mock_child_process, max_queued=10, max_parallel=5)

        task_id = queue.queue_task("failing task")
        queue.execute_all()

        assert queue.get_status(task_id) == TaskStatus.FAILED

    def test_exception_during_spawn(self, mock_child_process):
        """Test handling of exceptions during spawn."""
        mock_child_process.spawn_agent.side_effect = Exception("Spawn error")
        queue = TaskQueue(mock_child_process, max_queued=10, max_parallel=5)

        task_id = queue.queue_task("error task")
        results = queue.execute_all()

        assert len(results) == 1
        assert results[0].success is False
        assert "Spawn error" in results[0].error
        assert queue.get_status(task_id) == TaskStatus.FAILED


class TestGetStatusAndResult:
    """Test status and result retrieval."""

    def test_get_status_pending(self, task_queue):
        """Test getting status of pending task."""
        task_id = task_queue.queue_task("test")
        assert task_queue.get_status(task_id) == TaskStatus.PENDING

    def test_get_status_unknown(self, task_queue):
        """Test getting status of unknown task."""
        assert task_queue.get_status("unknown_task") is None

    def test_get_result_pending(self, task_queue):
        """Test getting result of pending task."""
        task_id = task_queue.queue_task("test")
        assert task_queue.get_result(task_id) is None

    def test_get_result_completed(self, task_queue):
        """Test getting result of completed task."""
        task_id = task_queue.queue_task("test")
        task_queue.execute_all()

        result = task_queue.get_result(task_id)
        assert result is not None
        assert result.success is True


class TestClear:
    """Test queue clearing."""

    def test_clear_pending_tasks(self, task_queue):
        """Test clearing pending tasks."""
        task_queue.queue_task("task 1")
        task_queue.queue_task("task 2")
        task_queue.queue_task("task 3")

        cleared = task_queue.clear()

        assert cleared == 3
        assert task_queue.pending_count() == 0

    def test_clear_marks_cancelled(self, task_queue):
        """Test that cleared tasks are marked as cancelled."""
        task_id = task_queue.queue_task("task")
        task_queue.clear()

        assert task_queue.get_status(task_id) == TaskStatus.CANCELLED

    def test_clear_empty_queue(self, task_queue):
        """Test clearing an empty queue."""
        cleared = task_queue.clear()
        assert cleared == 0


class TestChildProcessIntegration:
    """Test integration with ChildProcess."""

    def test_child_process_queue_task(self):
        """Test ChildProcess.queue_task method."""
        with patch.object(ChildProcess, '_find_qq_executable', return_value='qq'):
            cp = ChildProcess(max_queued=5)

            task_id = cp.queue_task("test task", agent="default", priority=5)

            assert task_id.startswith("task_")
            assert cp.task_queue.pending_count() == 1

    def test_child_process_queue_batch(self):
        """Test ChildProcess.queue_batch method."""
        with patch.object(ChildProcess, '_find_qq_executable', return_value='qq'):
            cp = ChildProcess(max_queued=5)

            task_ids = cp.queue_batch([
                {"task": "task1"},
                {"task": "task2"},
            ])

            assert len(task_ids) == 2
            assert cp.task_queue.pending_count() == 2

    def test_child_process_lazy_queue_init(self):
        """Test that task queue is lazily initialized."""
        with patch.object(ChildProcess, '_find_qq_executable', return_value='qq'):
            cp = ChildProcess()

            # Queue should not be initialized yet
            assert cp._task_queue is None

            # Accessing task_queue property should initialize it
            _ = cp.task_queue
            assert cp._task_queue is not None

    def test_max_queued_from_env(self):
        """Test QQ_MAX_QUEUED environment variable."""
        with patch.dict(os.environ, {"QQ_MAX_QUEUED": "15"}):
            with patch.object(ChildProcess, '_find_qq_executable', return_value='qq'):
                cp = ChildProcess()
                assert cp.max_queued == 15


class TestThreadSafety:
    """Test thread safety of queue operations."""

    def test_concurrent_queue_operations(self, mock_child_process):
        """Test that queue operations are thread-safe."""
        import threading

        queue = TaskQueue(mock_child_process, max_queued=100, max_parallel=10)
        errors = []

        def queue_tasks():
            try:
                for i in range(10):
                    queue.queue_task(f"task_{threading.current_thread().name}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=queue_tasks) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert queue.pending_count() == 50  # 5 threads * 10 tasks


class TestAgentParameterValidation:
    """Test agent parameter validation in queue_task."""

    def test_queue_task_with_agent_object(self, mock_child_process):
        """Test that passing an Agent object instead of string is handled gracefully."""
        queue = TaskQueue(mock_child_process, max_queued=10)

        # Create a mock Agent object (like strands.agent.agent.Agent)
        mock_agent = MagicMock()
        mock_agent.name = "coder"

        # Should extract agent.name and use it
        task_id = queue.queue_task("test task", agent=mock_agent)

        assert task_id.startswith("task_")
        # Verify the stored agent is the string, not the object
        status = queue._results[task_id]
        assert status.agent == "coder"

    def test_queue_task_with_object_no_name(self, mock_child_process):
        """Test that passing an object without .name falls back to 'default'."""
        queue = TaskQueue(mock_child_process, max_queued=10)

        # Object without .name attribute
        mock_agent = MagicMock(spec=[])

        task_id = queue.queue_task("test task", agent=mock_agent)

        # Should fall back to 'default'
        status = queue._results[task_id]
        assert status.agent == "default"
