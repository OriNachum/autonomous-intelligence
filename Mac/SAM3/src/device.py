"""Device selection and dtype helpers for Apple Silicon benchmarking."""

import torch


def get_device() -> torch.device:
    """Return MPS device if available, otherwise CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def get_dtype(device: torch.device, prefer_half: bool = False) -> torch.dtype:
    """Return appropriate dtype for the device.

    MPS supports float16 but not bfloat16.
    CPU supports both but float32 is safest default.
    """
    if prefer_half:
        if device.type == "mps":
            return torch.float16
        return torch.bfloat16
    return torch.float32


def sync_device(device: torch.device) -> None:
    """Synchronize device for accurate timing."""
    if device.type == "mps":
        torch.mps.synchronize()
    elif device.type == "cuda":
        torch.cuda.synchronize()
