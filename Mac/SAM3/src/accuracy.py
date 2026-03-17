"""COCO mIoU accuracy evaluation for all SAM model runners."""

import gc
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from pycocotools.coco import COCO
from tqdm import tqdm

from .metrics import compute_iou

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COCO_ROOT = PROJECT_ROOT / "data" / "coco"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "accuracy.csv"


def evaluate_model(runner, coco: COCO, img_ids: list[int], img_dir: Path) -> tuple[float, int]:
    """Evaluate a single model on COCO images using box prompts.

    Returns:
        (mean_iou, num_annotations_evaluated)
    """
    ious = []
    for img_id in tqdm(img_ids, desc=f"  {runner.name}", leave=False):
        img_info = coco.loadImgs(img_id)[0]
        image = Image.open(img_dir / img_info["file_name"]).convert("RGB")

        ann_ids = coco.getAnnIds(imgIds=img_id, iscrowd=False)
        anns = coco.loadAnns(ann_ids)

        for ann in anns:
            # Skip annotations with no segmentation or tiny area
            if ann.get("area", 0) < 1:
                continue

            # COCO bbox: [x, y, w, h] -> [x1, y1, x2, y2]
            x, y, w, h = ann["bbox"]
            box_xyxy = np.array([x, y, x + w, y + h], dtype=np.float32)

            # Get ground truth mask
            gt_mask = coco.annToMask(ann)

            # Predict
            try:
                pred_mask = runner.predict_box(image, box_xyxy)
            except Exception as e:
                print(f"    Warning: predict_box failed for {runner.name} on img {img_id}: {e}")
                continue

            # Resize pred_mask if needed to match GT
            if pred_mask.shape != gt_mask.shape:
                from scipy.ndimage import zoom
                zoom_factors = (gt_mask.shape[0] / pred_mask.shape[0],
                                gt_mask.shape[1] / pred_mask.shape[1])
                pred_mask = (zoom(pred_mask.astype(float), zoom_factors, order=0) > 0.5).astype(np.uint8)

            iou = compute_iou(pred_mask, gt_mask)
            ious.append(iou)

    miou = float(np.mean(ious)) if ious else 0.0
    return miou, len(ious)


def run_accuracy(
    models: str = "all",
    num_images: int = 100,
    coco_root: Path = DEFAULT_COCO_ROOT,
    output_path: Path = DEFAULT_OUTPUT,
    prefer_half: bool = False,
):
    """Run COCO mIoU evaluation for selected models."""
    from .benchmark import build_runners

    ann_file = coco_root / "annotations" / "instances_val2017.json"
    img_dir = coco_root / "val2017"

    if not ann_file.exists():
        raise FileNotFoundError(
            f"COCO annotations not found at {ann_file}. "
            "Run: python scripts/download_coco.py"
        )

    print("Loading COCO annotations...")
    coco = COCO(str(ann_file))

    # Deterministic subset
    img_ids = sorted(coco.getImgIds())[:num_images]
    print(f"Evaluating on {len(img_ids)} images")

    runners = build_runners(models, prefer_half)
    results = []

    for runner in tqdm(runners, desc="Accuracy evaluation"):
        print(f"\n{'='*60}")
        print(f"Model: {runner.name}")
        print(f"{'='*60}")

        try:
            runner.load()
        except Exception as e:
            print(f"  SKIP: Failed to load: {e}")
            results.append({
                "model_name": runner.name,
                "miou": -1,
                "num_annotations": 0,
                "num_images": num_images,
                "eval_time_s": -1,
                "error": str(e),
            })
            continue

        start = time.perf_counter()
        miou, num_anns = evaluate_model(runner, coco, img_ids, img_dir)
        eval_time = time.perf_counter() - start

        results.append({
            "model_name": runner.name,
            "miou": round(miou, 4),
            "num_annotations": num_anns,
            "num_images": len(img_ids),
            "eval_time_s": round(eval_time, 1),
        })
        print(f"  mIoU: {miou:.4f} | Annotations: {num_anns} | Time: {eval_time:.1f}s")

        # Cleanup
        runner.unload()
        gc.collect()
        if runner.device.type == "mps":
            torch.mps.empty_cache()

    # Save results
    df = pd.DataFrame(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nResults saved to {output_path}")
    print(df.to_string(index=False))
    return df
