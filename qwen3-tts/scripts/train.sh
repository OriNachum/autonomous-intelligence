#!/usr/bin/env bash
# Fine-tune Qwen3-TTS on prepared data.
#
# Usage: bash scripts/train.sh <prepared.jsonl> <speaker_name> [epochs] [base_model]
#
# Prerequisites: run prepare_data.sh first to encode audio.
# Output: checkpoints in output/checkpoint-epoch-{N}

set -euo pipefail

TRAIN_JSONL="${1:?Usage: train.sh <prepared.jsonl> <speaker_name> [epochs] [base_model]}"
SPEAKER="${2:?Usage: train.sh <prepared.jsonl> <speaker_name> [epochs] [base_model]}"
EPOCHS="${3:-10}"
BASE_MODEL="${4:-Qwen/Qwen3-TTS-12Hz-0.6B-Base}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/output"

echo "==> Fine-tuning Qwen3-TTS"
echo "    Data: $TRAIN_JSONL"
echo "    Speaker: $SPEAKER"
echo "    Epochs: $EPOCHS"
echo "    Base model: $BASE_MODEL"
echo "    Output: $OUTPUT_DIR"

# Find the sft script from the qwen-tts package
SFT_SCRIPT="$(uv run --project "$PROJECT_DIR" python3 -c "
import importlib.util, os
spec = importlib.util.find_spec('qwen_tts')
pkg_dir = os.path.dirname(spec.origin)
# The finetuning scripts are in the repo, not the package.
# We'll inline the training logic.
print(pkg_dir)
")"

echo "    qwen_tts package: $SFT_SCRIPT"

# The official sft_12hz.py requires being run from the finetuning/ dir with dataset.py.
# We invoke it via the installed package's entry points if available,
# otherwise we clone the needed files.

FINETUNE_DIR="$PROJECT_DIR/.finetuning_cache"

if [ ! -f "$FINETUNE_DIR/sft_12hz.py" ]; then
    echo "==> Downloading finetuning scripts from Qwen3-TTS repo..."
    mkdir -p "$FINETUNE_DIR"
    for f in sft_12hz.py dataset.py; do
        curl -sL -o "$FINETUNE_DIR/$f" \
            "https://raw.githubusercontent.com/QwenLM/Qwen3-TTS/main/finetuning/$f"
    done
fi

cd "$FINETUNE_DIR"

uv run --project "$PROJECT_DIR" python3 sft_12hz.py \
    --init_model_path "$BASE_MODEL" \
    --output_model_path "$OUTPUT_DIR" \
    --train_jsonl "$TRAIN_JSONL" \
    --speaker_name "$SPEAKER" \
    --num_epochs "$EPOCHS" \
    --batch_size 2 \
    --lr 2e-5
