"""Timing, memory, and IoU metrics for benchmarking."""

import time
from dataclasses import dataclass

import numpy as np
import psutil
import torch

from .device import sync_device


@dataclass
class TimingResult:
    mean_ms: float
    median_ms: float
    std_ms: float
    min_ms: float
    max_ms: float


def measure_inference(
    fn: callable,
    iterations: int = 10,
    warmup: int = 3,
    device: torch.device | None = None,
) -> TimingResult:
    """Time a callable over multiple iterations with warmup."""
    if device is None:
        device = torch.device("cpu")

    # Warmup
    for _ in range(warmup):
        fn()
        sync_device(device)

    # Timed runs
    times = []
    for _ in range(iterations):
        sync_device(device)
        start = time.perf_counter()
        fn()
        sync_device(device)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)

    arr = np.array(times)
    return TimingResult(
        mean_ms=float(np.mean(arr)),
        median_ms=float(np.median(arr)),
        std_ms=float(np.std(arr)),
        min_ms=float(np.min(arr)),
        max_ms=float(np.max(arr)),
    )


def measure_memory(device: torch.device) -> float:
    """Return current memory usage in MB."""
    if device.type == "mps":
        try:
            return torch.mps.current_allocated_memory() / (1024 * 1024)
        except AttributeError:
            pass
    # Fallback to process RSS
    process = psutil.Process()
    return process.memory_info().rss / (1024 * 1024)


def compute_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Compute Intersection-over-Union between two binary masks."""
    mask_a = mask_a.astype(bool)
    mask_b = mask_b.astype(bool)
    intersection = np.logical_and(mask_a, mask_b).sum()
    union = np.logical_or(mask_a, mask_b).sum()
    if union == 0:
        return 0.0
    return float(intersection / union)
