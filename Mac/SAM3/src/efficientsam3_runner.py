"""EfficientSAM3 inference runner wrapping the cloned repo."""

import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from .device import get_device, get_dtype
from .ssl_setup import ensure_ssl_certs

ensure_ssl_certs()

# Must set this before importing sam3 modules
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

EFFICIENTSAM3_ROOT = Path(__file__).resolve().parent.parent / "efficientsam3"

# Available variants: (backbone_type, model_name, description)
VARIANTS = {
    "efficientvit-b0": ("efficientvit", "b0", "EfficientViT-B0 (smallest)"),
    "efficientvit-b1": ("efficientvit", "b1", "EfficientViT-B1 (medium)"),
    "efficientvit-b2": ("efficientvit", "b2", "EfficientViT-B2 (large)"),
    "repvit-m0_9": ("repvit", "m0_9", "RepViT-M0.9 (small)"),
    "repvit-m1_1": ("repvit", "m1_1", "RepViT-M1.1 (medium)"),
    "repvit-m2_3": ("repvit", "m2_3", "RepViT-M2.3 (large)"),
    "tinyvit-5m": ("tinyvit", "5m", "TinyViT-5M (small)"),
    "tinyvit-11m": ("tinyvit", "11m", "TinyViT-11M (medium)"),
    "tinyvit-21m": ("tinyvit", "21m", "TinyViT-21M (large)"),
}


class EfficientSAM3Runner:
    """Wrapper for EfficientSAM3 distilled models."""

    def __init__(self, variant: str = "efficientvit-b0", prefer_half: bool = False):
        if variant not in VARIANTS:
            raise ValueError(f"Unknown variant: {variant}. Choose from: {list(VARIANTS.keys())}")
        self.variant = variant
        self.backbone_type, self.model_name, self.description = VARIANTS[variant]
        self.device = get_device()
        self.dtype = get_dtype(self.device, prefer_half=prefer_half)
        self.model = None
        self._processor = None
        self._name = f"efficientsam3-{variant}"

    @property
    def name(self) -> str:
        return self._name

    def load(self):
        # Add EfficientSAM3 repo to path
        repo_str = str(EFFICIENTSAM3_ROOT)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        from sam3.model.sam3_image_processor import Sam3Processor
        from sam3.model_builder import build_efficientsam3_image_model

        self.model = build_efficientsam3_image_model(
            backbone_type=self.backbone_type,
            model_name=self.model_name,
            load_from_HF=True,
            enable_inst_interactivity=True,
            device=self.device,
        )
        self._processor = Sam3Processor(self.model)

    def predict(self, image: Image.Image, input_points: list[list[list[list[float]]]]) -> np.ndarray:
        """Run inference with point prompts (same interface as SAM2.1 runners).

        Args:
            image: PIL image
            input_points: 4D nested list [batch, point_sets, points, coords]
                e.g. [[[[320, 240]]]] for a single center point

        Returns:
            Predicted masks as numpy array
        """
        inference_state = self._processor.set_image(image)

        # Extract point coords from the 4D structure: take first batch, first set
        points = np.array(input_points[0][0])  # shape: (N, 2)
        labels = np.ones(len(points), dtype=np.int32)  # all positive

        masks, scores, logits = self.model.predict_inst(
            inference_state,
            point_coords=points,
            point_labels=labels,
            multimask_output=True,
        )
        return masks

    def unload(self):
        del self.model
        del self._processor
        self.model = None
        self._processor = None
        if self.device.type == "mps":
            torch.mps.empty_cache()
