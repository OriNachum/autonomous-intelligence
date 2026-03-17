# SAM3 Benchmark Suite

Benchmarks SAM3, SAM 2.1, and EfficientSAM3 on Apple Silicon (MPS) for
inference speed, memory usage, and segmentation accuracy (COCO mIoU).

## Models (12 total)

| Family         | Models                                    |
| -------------- | ----------------------------------------- |
| SAM3           | `facebook/sam3`                           |
| SAM 2.1        | `sam2.1-hiera-tiny`, `sam2.1-hiera-large` |
| EfficientSAM3  | 9 variants across EfficientViT, RepViT,   |
|                | and TinyViT backbones (see CLI)           |

## Setup

```bash
# Install dependencies
uv sync

# Clone and install EfficientSAM3
bash scripts/setup_efficientsam3.sh

# Download HuggingFace models + sample image
python scripts/download_models.py

# Download COCO val2017 for accuracy evaluation (~1GB images + 241MB annotations)
python scripts/download_coco.py
```

## Usage

### Timing benchmark

Measures inference latency and memory for each model:

```bash
# All 12 models, 10 iterations each (default)
uv run python -m src.benchmark --mode timing --models all --iterations 10

# Single family
uv run python -m src.benchmark --mode timing --models efficientsam3

# Custom image and output
uv run python -m src.benchmark --mode timing \
  --image path/to/image.jpg --output results/custom.csv
```

### Accuracy benchmark (COCO mIoU)

Evaluates segmentation quality using COCO val2017 ground-truth bounding boxes:

```bash
# Quick test — 10 images, single model
uv run python -m src.benchmark --mode accuracy --models sam3 --num-images 10

# Full evaluation — 100 images, all models
uv run python -m src.benchmark --mode accuracy --models all --num-images 100

# Custom COCO path
uv run python -m src.benchmark --mode accuracy --coco-root /path/to/coco
```

### CLI reference

```text
usage: benchmark.py [-h] [--mode {timing,accuracy}]
                    [--models {all,sam21,sam3,efficientsam3}]
                    [--iterations N] [--warmup N] [--image PATH]
                    [--output PATH] [--dtype {float32,half}]
                    [--num-images N] [--coco-root PATH]

--mode          timing (default) or accuracy
--models        all (default), sam21, sam3, or efficientsam3
--iterations    Timing iterations per model (default: 10)
--warmup        Warmup iterations before timing (default: 3)
--image         Input image for timing benchmark
--output        Output CSV path
--dtype         float32 (default) or half
--num-images    Number of COCO images for accuracy eval (default: 100)
--coco-root     COCO dataset root (default: data/coco)
```

## Output

- `results/benchmark.csv` — timing results
  (model, latency stats, memory, params)
- `results/accuracy.csv` — accuracy results
  (model, mIoU, annotation count, eval time)

## Project structure

```text
Mac/SAM3/
├── scripts/
│   ├── download_coco.py        # Download COCO val2017
│   ├── download_models.py      # Download HF models
│   └── setup_efficientsam3.sh  # Clone + install EfficientSAM3
├── src/
│   ├── accuracy.py             # COCO mIoU evaluation
│   ├── benchmark.py            # CLI entry point + timing benchmark
│   ├── device.py               # MPS/CPU device helpers
│   ├── efficientsam3_runner.py # EfficientSAM3 runner (9 variants)
│   ├── metrics.py              # Timing, memory, IoU utilities
│   ├── sam21_runner.py         # SAM 2.1 runner
│   ├── sam3_runner.py          # SAM3 runner
│   └── ssl_setup.py            # Corporate proxy SSL fix
├── images/                     # Sample images
├── results/                    # Output CSVs (gitignored)
├── data/                       # COCO dataset (gitignored)
└── efficientsam3/              # Cloned repo (gitignored)
```
