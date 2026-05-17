#!/bin/bash
# Smoke test suite — runs after every deployment
# 7 test categories covering all critical paths
set -e

BASE_URL="${1:-http://localhost:30080}"
EXPECTED_VERSION="${2:-}"
EXPECTED_COLOR="${3:-}"

PASS=0; FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -q "$expected" 2>/dev/null; then
    echo "  ✅ $name"; PASS=$((PASS+1))
  else
    echo "  ❌ $name (expected '$expected', got '${actual:0:80}')"; FAIL=$((FAIL+1))
  fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Smoke Tests → $BASE_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "1. Health & Readiness"
HEALTH=$(curl -sf --max-time 10 "$BASE_URL/health" 2>/dev/null || echo '{"status":"error"}')
check "Health: status=healthy"    "healthy"   "$HEALTH"
check "Health: redis=connected"   "connected" "$HEALTH"
READY=$(curl -sf --max-time 10  "$BASE_URL/ready"  2>/dev/null || echo '{"status":"error"}')
check "Ready endpoint responds"   "ready"     "$READY"

echo ""
echo "2. Version Verification"
VER=$(curl -sf --max-time 10 "$BASE_URL/version" 2>/dev/null || echo '{}')
check "Version endpoint responds" "version" "$VER"
[ -n "$EXPECTED_VERSION" ] && check "Correct version: $EXPECTED_VERSION" "$EXPECTED_VERSION" "$VER"
[ -n "$EXPECTED_COLOR"   ] && check "Correct color: $EXPECTED_COLOR"     "$EXPECTED_COLOR"   "$VER"

echo ""
echo "3. URL Shortening"
SHORTEN=$(curl -sf --max-time 10 -X POST "$BASE_URL/shorten" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://kubernetes.io"}' 2>/dev/null || echo '{}')
check "Shorten returns short_code" "short_code" "$SHORTEN"
CODE=$(echo "$SHORTEN" | python3 -c \
  "import sys,json; print(json.load(sys.stdin).get('short_code',''))" 2>/dev/null)

echo ""
echo "4. Redirect"
if [ -n "$CODE" ]; then
  REDIR=$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" \
    "$BASE_URL/r/$CODE" 2>/dev/null || echo "000")
  check "Redirect returns 3xx" "3" "$REDIR"
fi

echo ""
echo "5. Stats"
if [ -n "$CODE" ]; then
  STATS=$(curl -sf --max-time 10 "$BASE_URL/stats/$CODE" 2>/dev/null || echo '{}')
  check "Stats returns clicks" "clicks" "$STATS"
fi

echo ""
echo "6. Error Handling"
NF=$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" \
  "$BASE_URL/r/notexist" 2>/dev/null || echo "000")
check "404 for non-existent code" "404" "$NF"

echo ""
echo "7. Feature Flags"
FLAGS=$(curl -sf --max-time 10 "$BASE_URL/flags" 2>/dev/null || echo '{}')
check "Flags endpoint responds" "flags" "$FLAGS"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $PASS passed | $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[ $FAIL -eq 0 ] && exit 0 || exit 1
