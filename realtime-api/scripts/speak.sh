#!/usr/bin/env bash
# Speak text aloud via the Magpie TTS container in the realtime-api stack.
# Usage: ./scripts/speak.sh "Hello world"
#        ./scripts/speak.sh -v Mia.Happy -s 140 "Great news!"
set -euo pipefail

VOICE="Mia.Calm"
SPEED=125
TTS_URL="${MAGPIE_TTS_URL:-http://localhost:9000}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--voice)  VOICE="$2"; shift 2 ;;
        -s|--speed)  SPEED="$2"; shift 2 ;;
        -u|--url)    TTS_URL="$2"; shift 2 ;;
        -*)          echo "Unknown flag: $1" >&2; exit 1 ;;
        *)           break ;;
    esac
done

MESSAGE="${1:?Usage: speak.sh [-v VOICE] [-s SPEED] \"text to speak\"}"

# Wrap in SSML prosody if speed != 100
if [ "$SPEED" -ne 100 ]; then
    TEXT="<speak><prosody rate=\"${SPEED}%\">${MESSAGE}</prosody></speak>"
else
    TEXT="$MESSAGE"
fi

FULL_VOICE="Magpie-Multilingual.EN-US.${VOICE}"
TMPFILE=$(mktemp /tmp/speak_XXXXXX.wav)
trap 'rm -f "$TMPFILE"' EXIT

HTTP_CODE=$(curl -s -o "$TMPFILE" -w "%{http_code}" \
    "${TTS_URL}/v1/audio/synthesize" \
    -d "language=en-US" \
    -d "voice=${FULL_VOICE}" \
    --data-urlencode "text=${TEXT}")

if [ "$HTTP_CODE" != "200" ]; then
    echo "TTS error: HTTP $HTTP_CODE" >&2
    exit 1
fi

aplay "$TMPFILE" 2>/dev/null
