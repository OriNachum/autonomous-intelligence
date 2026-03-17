"""EfficientSAM3 inference runner wrapping the cloned repo."""

import sys
from pathlib import Path

import torch
from PIL import Image

from .device import get_device, get_dtype

# Path to the cloned EfficientSAM3 repo
EFFICIENTSAM3_ROOT = Path(__file__).resolve().parent.parent / "efficientsam3"

# Checkpoint URLs from the EfficientSAM3 repo
CHECKPOINTS = {
    "repvit-m0.5": "efficientsam3/checkpoints/repvit_m0_5.pt",
    "repvit-m0.7": "efficientsam3/checkpoints/repvit_m0_7.pt",
    "repvit-m2.3": "efficientsam3/checkpoints/repvit_m2_3.pt",
}


class EfficientSAM3Runner:
    """Wrapper for EfficientSAM3 distilled models."""

    def __init__(self, variant: str = "repvit-m0.5", prefer_half: bool = False):
        self.variant = variant
        self.device = get_device()
        self.dtype = get_dtype(self.device, prefer_half=prefer_half)
        self.model = None
        self._name = f"efficientsam3-{variant}"

    @property
    def name(self) -> str:
        return self._name

    def load(self):
        # Add EfficientSAM3 repo to path so we can import its modules
        repo_str = str(EFFICIENTSAM3_ROOT)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        try:
            from efficient_sam3.build_efficient_sam3 import build_efficient_sam3

            checkpoint_path = EFFICIENTSAM3_ROOT / "checkpoints" / f"repvit_{self.variant.replace('repvit-', '').replace('.', '_').replace('-', '_')}.pt"

            self.model = build_efficient_sam3(
                encoder_type=self.variant.replace("repvit-", "repvit_"),
                checkpoint_path=str(checkpoint_path) if checkpoint_path.exists() else None,
            )
            self.model = self.model.to(device=self.device, dtype=self.dtype)
            self.model.eval()
        except ImportError as e:
            raise RuntimeError(
                f"EfficientSAM3 not installed. Run: bash scripts/setup_efficientsam3.sh\n{e}"
            ) from e

    def predict(self, image: Image.Image, input_points: list[list[list[float]]]) -> torch.Tensor:
        """Run inference. Returns predicted masks or encoder features if full pipeline unavailable."""
        import numpy as np

        img_array = np.array(image)
        img_tensor = torch.from_numpy(img_array).permute(2, 0, 1).unsqueeze(0).float()
        img_tensor = img_tensor.to(device=self.device, dtype=self.dtype) / 255.0

        with torch.no_grad():
            # Try full pipeline first, fall back to encoder-only
            try:
                point_tensor = torch.tensor(input_points, dtype=self.dtype, device=self.device)
                point_labels = torch.ones(
                    point_tensor.shape[:-1], dtype=torch.long, device=self.device
                )
                output = self.model(img_tensor, point_tensor, point_labels)
                if isinstance(output, tuple):
                    return output[0]  # masks
                return output
            except (TypeError, AttributeError):
                # Stage 1 only: encoder features
                features = self.model.image_encoder(img_tensor)
                if isinstance(features, (list, tuple)):
                    return features[0]
                return features

    def unload(self):
        del self.model
        self.model = None
        if self.device.type == "mps":
            torch.mps.empty_cache()
