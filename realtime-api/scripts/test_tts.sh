#!/usr/bin/env bash
# Run TTS round-trip tests against the deployed containers
# Usage: ./scripts/test_tts.sh [--logic-only]
set -euo pipefail

cd "$(dirname "$0")/.."

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[test]${NC} $*"; }
ok()    { echo -e "${GREEN}[test]${NC} $*"; }
fail()  { echo -e "${RED}[test]${NC} $*"; exit 1; }

TTS_URL="${TTS_URL:-http://localhost:9000}"
STT_URL="${STT_URL:-http://localhost:9002}"

# ── Pure-logic tests (no network) ────────────────────────────────────
info "Running pure-logic tests..."
.venv/bin/python -c "
import sys, os
sys.path.insert(0, 'src')
from realtime_api.llm_client import _split_buffer
from realtime_api.tts_client import _split_for_tts, _MAX_CLEAN_CHARS

# Test 1: Dash splitting
segments = [
    'The system processes incoming data streams efficiently',
    'transforms them through multiple neural network layers',
    'applies attention mechanisms across all token positions',
    'and finally produces coherent output sequences',
    'which are then validated against quality thresholds',
]
text = ' \u2014 '.join(segments)
assert len(text) > 200, f'Test text too short: {len(text)}'
parts, remainder = _split_buffer(text, loose=True)
all_parts = parts + ([remainder] if remainder.strip() else [])
assert len(all_parts) >= 2, f'Dash split: expected >= 2 parts, got {len(all_parts)}'
print(f'  PASS: dash splitting ({len(all_parts)} parts from {len(text)} chars)')

# Test 2: TTS chunking
phrases = [f'phrase number {i} with some filler text to make it longer' for i in range(25)]
text = ', '.join(phrases)
assert len(text) > 1000
chunks = _split_for_tts(text)
assert len(chunks) >= 2, f'Chunking: expected >= 2, got {len(chunks)}'
for c in chunks:
    assert len(c) <= _MAX_CLEAN_CHARS, f'Chunk too long: {len(c)}'
print(f'  PASS: TTS chunking ({len(chunks)} chunks from {len(text)} chars, max={max(len(c) for c in chunks)})')

# Test 3: Short text not split
short = 'Hello world.'
assert _split_for_tts(short) == [short]
print(f'  PASS: short text not split')

print('All pure-logic tests passed!')
"
ok "Pure-logic tests passed"

if [ "${1:-}" = "--logic-only" ]; then
    ok "Skipping integration tests (--logic-only)"
    exit 0
fi

# ── Integration tests (require TTS + STT containers) ─────────────────
info "Checking TTS service at $TTS_URL..."
if ! curl -sf "$TTS_URL/v1/health/ready" > /dev/null 2>&1; then
    fail "TTS service not ready at $TTS_URL"
fi
ok "TTS service ready"

info "Checking STT service at $STT_URL..."
if ! curl -sf "$STT_URL/v1/health/ready" > /dev/null 2>&1; then
    fail "STT service not ready at $STT_URL"
fi
ok "STT service ready"

info "Running full TTS round-trip test..."
TTS_URL="$TTS_URL" STT_URL="$STT_URL" .venv/bin/python tests/test_tts_roundtrip.py
ok "All tests passed!"
