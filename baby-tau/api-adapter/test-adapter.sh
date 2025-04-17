#!/bin/bash

# Test script for the API adapter

ADAPTER_URL="${ADAPTER_URL:-http://localhost:8080}"
MODEL="${MODEL:-mistral}"

echo "Testing API adapter at $ADAPTER_URL using model $MODEL"
echo "========================================================"

echo -e "\n1. Testing Chat Completions API..."
curl -s "$ADAPTER_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Respond with 'Hello from the Chat Completions API!'\"}]
  }" | jq .

echo -e "\n2. Testing Responses API..."
curl -s "$ADAPTER_URL/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"input\": \"Respond with 'Hello from the Responses API!'\"
  }" | jq .

echo -e "\n3. Testing cross-conversion (Responses format → Chat Completions endpoint)..."
curl -s "$ADAPTER_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"input\": \"Respond with 'Testing cross-conversion!'\"
  }" | jq .

echo -e "\nTests completed!"
echo "For more detailed tests or to test with Codex, see the README.md file."
