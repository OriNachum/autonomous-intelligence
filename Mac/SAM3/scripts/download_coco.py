"""Download COCO val2017 images and annotations for accuracy evaluation."""

import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# Add project root so we can reuse ssl_setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ssl_setup import ensure_ssl_certs

ensure_ssl_certs()

COCO_ROOT = PROJECT_ROOT / "data" / "coco"
URLS = {
    "val2017": "http://images.cocodataset.org/zips/val2017.zip",
    "annotations": "http://images.cocodataset.org/annotations/annotations_trainval2017.zip",
}


def _progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\r  {mb:.0f}/{total_mb:.0f} MB ({pct}%)", end="", flush=True)


def download_and_extract(name: str, url: str, dest: Path):
    """Download a zip and extract, skipping if target already exists."""
    if name == "val2017" and (dest / "val2017").exists():
        print(f"  {name}: already exists, skipping")
        return
    if name == "annotations" and (dest / "annotations").exists():
        print(f"  {name}: already exists, skipping")
        return

    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / f"{name}.zip"

    print(f"  Downloading {name}...")
    urlretrieve(url, zip_path, reporthook=_progress)
    print()

    print(f"  Extracting {name}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)

    zip_path.unlink()
    print(f"  {name}: done")


def main():
    print(f"COCO val2017 download → {COCO_ROOT}")
    for name, url in URLS.items():
        download_and_extract(name, url, COCO_ROOT)
    print("\nDone. COCO val2017 ready at", COCO_ROOT)


if __name__ == "__main__":
    main()
