#!/usr/bin/env bash
# Deploy realtime-api container with verification
# Usage: ./scripts/deploy.sh [--no-restart-deps]
set -euo pipefail

cd "$(dirname "$0")/.."

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()    { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
fail()  { echo -e "${RED}[deploy]${NC} $*"; exit 1; }

# ── 1. Pre-flight: ensure key source files exist ──────────────────────
info "Pre-flight checks..."
for f in src/realtime_api/tts_client.py src/realtime_api/llm_client.py src/realtime_api/ws_handler.py Dockerfile docker-compose.yaml; do
    [ -f "$f" ] || fail "Missing required file: $f"
done
ok "Source files present"

# ── 2. Build the image (no cache to guarantee fresh copy) ─────────────
info "Building realtime-api image (--no-cache)..."
docker compose build --no-cache realtime-api
ok "Image built"

# ── 3. Restart only the realtime-api service ──────────────────────────
info "Restarting realtime-api container..."
docker compose up -d --no-deps realtime-api
ok "Container restarted"

# ── 4. Wait for container to be running ───────────────────────────────
info "Waiting for container to be healthy..."
for i in $(seq 1 15); do
    STATE=$(docker compose ps --format json realtime-api 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('State',''))" 2>/dev/null || echo "")
    if [ "$STATE" = "running" ]; then
        ok "Container is running"
        break
    fi
    sleep 1
done

# ── 5. Verify deployed code matches local source ─────────────────────
info "Verifying deployed code..."
CHECKS_PASSED=0
CHECKS_TOTAL=0

# Check 1: _split_for_tts exists in tts_client.py
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if docker compose exec -T realtime-api grep -q '_split_for_tts' /app/src/realtime_api/tts_client.py 2>/dev/null; then
    ok "  tts_client.py: _split_for_tts present"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  tts_client.py: _split_for_tts MISSING"
fi

# Check 2: _MAX_CLEAN_CHARS exists
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if docker compose exec -T realtime-api grep -q '_MAX_CLEAN_CHARS' /app/src/realtime_api/tts_client.py 2>/dev/null; then
    ok "  tts_client.py: _MAX_CLEAN_CHARS present"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  tts_client.py: _MAX_CLEAN_CHARS MISSING"
fi

# Check 3: _synthesize_single exists
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if docker compose exec -T realtime-api grep -q '_synthesize_single' /app/src/realtime_api/tts_client.py 2>/dev/null; then
    ok "  tts_client.py: _synthesize_single present"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  tts_client.py: _synthesize_single MISSING"
fi

# Check 4: _reset_client retry logic exists
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if docker compose exec -T realtime-api grep -q '_reset_client' /app/src/realtime_api/tts_client.py 2>/dev/null; then
    ok "  tts_client.py: _reset_client (retry logic) present"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  tts_client.py: _reset_client MISSING"
fi

# Check 5: dash-splitting regex in llm_client.py
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if docker compose exec -T realtime-api grep -q 'em-dash' /app/src/realtime_api/llm_client.py 2>/dev/null; then
    ok "  llm_client.py: dash-splitting regex present"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  llm_client.py: dash-splitting regex MISSING"
fi

# Check 6: Diff local vs deployed tts_client.py
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
LOCAL_HASH=$(md5sum src/realtime_api/tts_client.py | cut -d' ' -f1)
DEPLOY_HASH=$(docker compose exec -T realtime-api md5sum /app/src/realtime_api/tts_client.py 2>/dev/null | cut -d' ' -f1)
if [ "$LOCAL_HASH" = "$DEPLOY_HASH" ]; then
    ok "  tts_client.py: hash match ($LOCAL_HASH)"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  tts_client.py: hash MISMATCH (local=$LOCAL_HASH, deployed=$DEPLOY_HASH)"
fi

# Check 7: Diff local vs deployed llm_client.py
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
LOCAL_HASH=$(md5sum src/realtime_api/llm_client.py | cut -d' ' -f1)
DEPLOY_HASH=$(docker compose exec -T realtime-api md5sum /app/src/realtime_api/llm_client.py 2>/dev/null | cut -d' ' -f1)
if [ "$LOCAL_HASH" = "$DEPLOY_HASH" ]; then
    ok "  llm_client.py: hash match ($LOCAL_HASH)"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "  llm_client.py: hash MISMATCH (local=$LOCAL_HASH, deployed=$DEPLOY_HASH)"
fi

echo ""
if [ "$CHECKS_PASSED" -eq "$CHECKS_TOTAL" ]; then
    ok "All $CHECKS_TOTAL/$CHECKS_TOTAL verification checks passed"
else
    fail "$CHECKS_PASSED/$CHECKS_TOTAL checks passed — deploy may be incomplete!"
fi

# ── 6. Show recent logs ──────────────────────────────────────────────
echo ""
info "Recent container logs:"
docker compose logs --tail=10 realtime-api 2>/dev/null | tail -10

echo ""
ok "Deploy complete!"
