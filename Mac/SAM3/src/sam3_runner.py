"""SAM3 inference runner using transformers.

SAM3 is text-conditioned: it takes an image + text prompt (e.g. "cat")
and produces segmentation masks. Optionally accepts bounding boxes.
"""

from .ssl_setup import ensure_ssl_certs

ensure_ssl_certs()

import numpy as np
import torch
from PIL import Image
from transformers import Sam3Model, Sam3Processor

from .device import get_device, get_dtype


class SAM3Runner:
    """Wrapper for SAM3 via HuggingFace transformers."""

    def __init__(self, model_id: str = "facebook/sam3", prefer_half: bool = False):
        self.model_id = model_id
        self.device = get_device()
        self.dtype = get_dtype(self.device, prefer_half=prefer_half)
        self.processor = None
        self.model = None
        self._fallback_cpu = False

    @property
    def name(self) -> str:
        return self.model_id.split("/")[-1]

    def load(self):
        self.processor = Sam3Processor.from_pretrained(self.model_id)
        try:
            self.model = Sam3Model.from_pretrained(
                self.model_id,
                torch_dtype=self.dtype,
                low_cpu_mem_usage=True,
            ).to(self.device)
        except Exception as e:
            print(f"Warning: Failed to load SAM3 on {self.device}, falling back to CPU: {e}")
            self._fallback_cpu = True
            self.device = torch.device("cpu")
            self.dtype = torch.float32
            self.model = Sam3Model.from_pretrained(
                self.model_id,
                torch_dtype=self.dtype,
                low_cpu_mem_usage=True,
            ).to(self.device)
        self.model.eval()

    def predict(self, image: Image.Image, text_prompt: str = "object") -> torch.Tensor:
        """Run inference with a text prompt.

        Args:
            image: PIL image
            text_prompt: Text describing the object to segment (e.g. "cat")

        Returns:
            Predicted masks tensor
        """
        inputs = self.processor(
            images=image,
            text=text_prompt,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            try:
                outputs = self.model(**inputs)
            except Exception as e:
                if not self._fallback_cpu and self.device.type == "mps":
                    print(f"MPS inference failed, retrying on CPU: {e}")
                    self._fallback_cpu = True
                    self.device = torch.device("cpu")
                    self.model = self.model.to(self.device)
                    inputs = {k: v.to(self.device) if hasattr(v, "to") else v for k, v in inputs.items()}
                    outputs = self.model(**inputs)
                else:
                    raise

        return outputs.pred_masks

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
            input_boxes=[[[box_xyxy.tolist()]]],
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            try:
                outputs = self.model(**inputs)
            except Exception as e:
                if not self._fallback_cpu and self.device.type == "mps":
                    print(f"MPS inference failed, retrying on CPU: {e}")
                    self._fallback_cpu = True
                    self.device = torch.device("cpu")
                    self.model = self.model.to(self.device)
                    inputs = {k: v.to(self.device) if hasattr(v, "to") else v for k, v in inputs.items()}
                    outputs = self.model(**inputs)
                else:
                    raise

        masks = outputs.pred_masks.cpu()
        # Take best mask (highest score or first)
        mask = masks[0, 0, 0]  # batch, num_masks, channels -> first mask
        return (mask.numpy() > 0).astype(np.uint8)

    def unload(self):
        del self.model
        del self.processor
        self.model = None
        self.processor = None
        if self.device.type == "mps":
            torch.mps.empty_cache()
