"""SAM 2.1 inference runner using transformers."""

from .ssl_setup import ensure_ssl_certs

ensure_ssl_certs()

import numpy as np
import torch
from PIL import Image
from transformers import Sam2Model, Sam2Processor

from .device import get_device, get_dtype


class SAM21Runner:
    """Wrapper for SAM 2.1 models via HuggingFace transformers."""

    def __init__(self, model_id: str = "facebook/sam2.1-hiera-tiny", prefer_half: bool = False):
        self.model_id = model_id
        self.device = get_device()
        self.dtype = get_dtype(self.device, prefer_half=prefer_half)
        self.processor = None
        self.model = None

    @property
    def name(self) -> str:
        return self.model_id.split("/")[-1]

    def load(self):
        self.processor = Sam2Processor.from_pretrained(self.model_id)
        self.model = Sam2Model.from_pretrained(
            self.model_id,
            torch_dtype=self.dtype,
            low_cpu_mem_usage=True,
        ).to(self.device)
        self.model.eval()

    def predict(self, image: Image.Image, input_points: list[list[list[list[float]]]]) -> torch.Tensor:
        """Run inference with point prompts.

        Args:
            image: PIL image
            input_points: 4D nested list [batch, point_sets, points, coords]
                e.g. [[[[320, 240]]]] for a single center point

        Returns:
            Predicted masks tensor
        """
        inputs = self.processor(
            images=image,
            input_points=input_points,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        masks = self.processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
        )
        return masks[0]

    def predict_box(self, image: Image.Image, box_xyxy: np.ndarray) -> np.ndarray:
        """Run inference with a bounding box prompt.

        Args:
            image: PIL image
            box_xyxy: 1-D array [x1, y1, x2, y2]

        Returns:
            Binary mask as numpy array (H, W)
        """
        inputs = self.processor(
            images=image,
            input_boxes=[[box_xyxy.tolist()]],
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        masks = self.processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
        )
        # Take best mask from first batch element
        mask = masks[0][0, 0]  # num_masks, channels -> first mask
        return (mask.numpy() > 0).astype(np.uint8)

    def unload(self):
        del self.model
        del self.processor
        self.model = None
        self.processor = None
        if self.device.type == "mps":
            torch.mps.empty_cache()
