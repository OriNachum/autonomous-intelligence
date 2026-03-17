"""Download SAM3 and SAM 2.1 models from HuggingFace."""

import sys
from pathlib import Path

# Add src to path for ssl_setup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ssl_setup import ensure_ssl_certs

ensure_ssl_certs()

from transformers import Sam2Model, Sam2Processor, Sam3Model, Sam3Processor

MODELS = {
    "sam2.1-tiny": {
        "id": "facebook/sam2.1-hiera-tiny",
        "model_cls": Sam2Model,
        "processor_cls": Sam2Processor,
    },
    "sam2.1-large": {
        "id": "facebook/sam2.1-hiera-large",
        "model_cls": Sam2Model,
        "processor_cls": Sam2Processor,
    },
    "sam3": {
        "id": "facebook/sam3",
        "model_cls": Sam3Model,
        "processor_cls": Sam3Processor,
    },
}


def download_all():
    for name, info in MODELS.items():
        model_id = info["id"]
        print(f"Downloading {name} ({model_id})...")
        try:
            info["processor_cls"].from_pretrained(model_id)
            info["model_cls"].from_pretrained(model_id)
            print(f"  + {name} downloaded successfully")
        except Exception as e:
            print(f"  x {name} failed: {e}")
            if "gated" in str(e).lower() or "401" in str(e):
                print(f"    -> Run: huggingface-cli login")


def download_image():
    """Download a sample COCO image for testing."""
    import urllib.request

    img_path = Path(__file__).resolve().parent.parent / "images" / "sample.jpg"
    if img_path.exists():
        print(f"Sample image already exists: {img_path}")
        return
    url = "http://images.cocodataset.org/val2017/000000039769.jpg"
    print(f"Downloading sample image from {url}...")
    urllib.request.urlretrieve(url, img_path)
    print(f"  + Saved to {img_path}")


if __name__ == "__main__":
    download_image()
    download_all()
