#!/usr/bin/env bash
# Prepare training data by encoding audio into discrete codes.
#
# Usage: bash scripts/prepare_data.sh <input.jsonl> <output.jsonl> [device]
#
# Input JSONL format (one per line):
#   {"audio": "path/to/clip.wav", "text": "Transcript.", "ref_audio": "path/to/ref.wav"}
#
# The ref_audio should be the same file for all entries (speaker reference).

set -euo pipefail

INPUT_JSONL="${1:?Usage: prepare_data.sh <input.jsonl> <output.jsonl> [device]}"
OUTPUT_JSONL="${2:?Usage: prepare_data.sh <input.jsonl> <output.jsonl> [device]}"
DEVICE="${3:-cuda:0}"
TOKENIZER="Qwen/Qwen3-TTS-Tokenizer-12Hz"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Preparing data: $INPUT_JSONL -> $OUTPUT_JSONL"
echo "    Device: $DEVICE | Tokenizer: $TOKENIZER"

uv run --project "$PROJECT_DIR" python3 -c "
import json
from qwen_tts import Qwen3TTSTokenizer

BATCH_SIZE = 32

tokenizer = Qwen3TTSTokenizer.from_pretrained('$TOKENIZER', device_map='$DEVICE')

with open('$INPUT_JSONL') as f:
    lines = [json.loads(line.strip()) for line in f if line.strip()]

results = []
batch_lines, batch_audios = [], []

for line in lines:
    batch_lines.append(line)
    batch_audios.append(line['audio'])
    if len(batch_lines) >= BATCH_SIZE:
        enc = tokenizer.encode(batch_audios)
        for code, bl in zip(enc.audio_codes, batch_lines):
            bl['audio_codes'] = code.cpu().tolist()
            results.append(bl)
        batch_lines.clear()
        batch_audios.clear()

if batch_audios:
    enc = tokenizer.encode(batch_audios)
    for code, bl in zip(enc.audio_codes, batch_lines):
        bl['audio_codes'] = code.cpu().tolist()
        results.append(bl)

with open('$OUTPUT_JSONL', 'w') as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

print(f'Done: {len(results)} samples written to $OUTPUT_JSONL')
"
