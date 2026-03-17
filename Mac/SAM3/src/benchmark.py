"""Main benchmark orchestrator. Runs all models and outputs CSV."""

from .ssl_setup import ensure_ssl_certs

ensure_ssl_certs()

import argparse
import gc
from pathlib import Path

import pandas as pd
import torch
from PIL import Image
from tqdm import tqdm

from .device import get_device, get_dtype
from .metrics import TimingResult, measure_inference, measure_memory

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = PROJECT_ROOT / "images" / "sample.jpg"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "benchmark.csv"


def count_parameters(model: torch.nn.Module) -> float:
    """Count model parameters in millions."""
    return sum(p.numel() for p in model.parameters()) / 1e6


def build_runners(model_filter: str, prefer_half: bool):
    """Build list of (runner, category) tuples based on filter."""
    runners = []

    if model_filter in ("all", "sam21"):
        from .sam21_runner import SAM21Runner

        runners.append(SAM21Runner("facebook/sam2.1-hiera-tiny", prefer_half=prefer_half))
        runners.append(SAM21Runner("facebook/sam2.1-hiera-large", prefer_half=prefer_half))

    if model_filter in ("all", "sam3"):
        from .sam3_runner import SAM3Runner

        runners.append(SAM3Runner("facebook/sam3", prefer_half=prefer_half))

    if model_filter in ("all", "efficientsam3"):
        from .efficientsam3_runner import EfficientSAM3Runner

        # One small variant from each backbone family
        for variant in ("efficientvit-b0", "repvit-m0_9", "tinyvit-5m"):
            runners.append(EfficientSAM3Runner(variant, prefer_half=prefer_half))

    return runners


def run_benchmark(
    models: str = "all",
    iterations: int = 10,
    warmup: int = 3,
    image_path: Path = DEFAULT_IMAGE,
    output_path: Path = DEFAULT_OUTPUT,
    prefer_half: bool = False,
):
    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    # 4D: [batch, point_sets, points, coords]
    center_point = [[[[w / 2, h / 2]]]]

    runners = build_runners(models, prefer_half)
    results = []

    for runner in tqdm(runners, desc="Benchmarking"):
        print(f"\n{'='*60}")
        print(f"Model: {runner.name}")
        print(f"{'='*60}")

        try:
            runner.load()
        except Exception as e:
            print(f"  SKIP: Failed to load: {e}")
            results.append({
                "model_name": runner.name,
                "params_millions": -1,
                "device": str(runner.device),
                "dtype": str(runner.dtype),
                "mean_ms": -1, "median_ms": -1, "std_ms": -1,
                "min_ms": -1, "max_ms": -1, "memory_mb": -1,
                "error": str(e),
            })
            continue

        params = count_parameters(runner.model) if runner.model is not None else -1
        device = runner.device
        dtype = runner.dtype

        # Measure memory after loading
        mem_mb = measure_memory(device)

        # Benchmark inference — SAM3 uses text prompts, others use point prompts
        from .sam3_runner import SAM3Runner

        _runner = runner  # capture for closure
        if isinstance(_runner, SAM3Runner):
            # COCO image 39769 has cats
            def inference_fn():
                _runner.predict(image, text_prompt="cat")
        else:
            def inference_fn():
                _runner.predict(image, center_point)

        try:
            timing: TimingResult = measure_inference(
                inference_fn, iterations=iterations, warmup=warmup, device=device,
            )
            results.append({
                "model_name": runner.name,
                "params_millions": round(params, 2),
                "device": str(device),
                "dtype": str(dtype),
                "mean_ms": round(timing.mean_ms, 2),
                "median_ms": round(timing.median_ms, 2),
                "std_ms": round(timing.std_ms, 2),
                "min_ms": round(timing.min_ms, 2),
                "max_ms": round(timing.max_ms, 2),
                "memory_mb": round(mem_mb, 2),
            })
            print(f"  Mean: {timing.mean_ms:.1f}ms | Memory: {mem_mb:.0f}MB | Params: {params:.1f}M")
        except Exception as e:
            print(f"  FAIL: Inference error: {e}")
            results.append({
                "model_name": runner.name,
                "params_millions": round(params, 2),
                "device": str(device),
                "dtype": str(dtype),
                "mean_ms": -1, "median_ms": -1, "std_ms": -1,
                "min_ms": -1, "max_ms": -1, "memory_mb": round(mem_mb, 2),
                "error": str(e),
            })

        # Cleanup
        runner.unload()
        gc.collect()
        if device.type == "mps":
            torch.mps.empty_cache()

    # Save results
    df = pd.DataFrame(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nResults saved to {output_path}")
    print(df.to_string(index=False))
    return df


def main():
    parser = argparse.ArgumentParser(description="SAM3 Benchmark Suite")
    parser.add_argument("--models", default="all", choices=["all", "sam21", "sam3", "efficientsam3"])
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dtype", choices=["float32", "half"], default="float32")
    args = parser.parse_args()

    run_benchmark(
        models=args.models,
        iterations=args.iterations,
        warmup=args.warmup,
        image_path=args.image,
        output_path=args.output,
        prefer_half=(args.dtype == "half"),
    )


if __name__ == "__main__":
    main()
