#!/bin/bash
# Generate realistic traffic for observability demos
BASE_URL="${1:-http://localhost:30080}"
DURATION="${2:-60}"
RPS="${3:-5}"

echo "Load test: $BASE_URL | ${DURATION}s | ${RPS} RPS"
END=$(($(date +%s) + DURATION))
CODES=()
COUNT=0

while [ $(date +%s) -lt $END ]; do
  COUNT=$((COUNT+1))
  R=$(curl -sf -X POST "$BASE_URL/shorten" \
    -H "Content-Type: application/json" \
    -d "{\"url\":\"https://example-$RANDOM.com\"}" \
    --max-time 5 2>/dev/null)
  CODE=$(echo $R | python3 -c \
    "import sys,json
try: print(json.load(sys.stdin)['short_code'])
except: print('')" 2>/dev/null)
  [ -n "$CODE" ] && CODES+=($CODE)
  if [ ${#CODES[@]} -gt 0 ]; then
    RC=${CODES[$RANDOM % ${#CODES[@]}]}
    curl -sf -o /dev/null "$BASE_URL/r/$RC" 2>/dev/null &
  fi
  curl -sf -o /dev/null "$BASE_URL/health" 2>/dev/null &
  SLEEP=$(python3 -c "print(1/$RPS)" 2>/dev/null || echo 0.2)
  sleep $SLEEP
done
wait
echo "✅ Load test complete. Shortened $COUNT URLs."
