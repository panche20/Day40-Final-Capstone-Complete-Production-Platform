#!/bin/bash

set -e

# ─────────────────────────────────────────────
# Reliable access for Minikube-on-EC2
# NodePort is unreliable with Docker driver
# Use kubectl port-forward instead
# ─────────────────────────────────────────────

echo "Starting port-forward..."

kubectl port-forward \
  svc/url-shortener-app \
  -n url-shortener \
  8080:80 >/tmp/url-shortener-pf.log 2>&1 &

PF_PID=$!

# Cleanup on exit
cleanup() {
  echo ""
  echo "Stopping port-forward..."
  kill $PF_PID >/dev/null 2>&1 || true
}

trap cleanup EXIT

# Give port-forward time to establish
sleep 5

BASE_URL="http://localhost:8080"
MINIKUBE_IP=$(minikube ip)

echo "╔══════════════════════════════════════════╗"
echo "║  Day 40 Final Verification               ║"
echo "╚══════════════════════════════════════════╝"

PASS=0
FAIL=0

check() {
  local name=$1
  local result=$2

  if [ "$result" = "pass" ]; then
    echo "  ✅ $name"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "═══ Infrastructure ═══"

NODES=$(kubectl get nodes --no-headers | wc -l)

check "Kubernetes cluster running ($NODES nodes)" \
  "$([ $NODES -ge 1 ] && echo pass || echo fail)"

HELM_RELEASE=$(helm list -n url-shortener --no-headers | wc -l)

check "Helm release deployed" \
  "$([ $HELM_RELEASE -ge 1 ] && echo pass || echo fail)"

echo ""
echo "═══ Application Pods ═══"

APP_PODS=$(kubectl get pods \
  -l component=app \
  -n url-shortener \
  --field-selector=status.phase=Running \
  --no-headers | wc -l)

check "App pods running ($APP_PODS pods)" \
  "$([ $APP_PODS -ge 1 ] && echo pass || echo fail)"

REDIS_PODS=$(kubectl get pods \
  -l component=redis \
  -n url-shortener \
  --field-selector=status.phase=Running \
  --no-headers | wc -l)

check "Redis running" \
  "$([ $REDIS_PODS -ge 1 ] && echo pass || echo fail)"

echo ""
echo "═══ Application Endpoints ═══"

HEALTH=$(curl -sf --max-time 10 \
  "$BASE_URL/health" 2>/dev/null || echo "{}")

check "Health endpoint: healthy" \
  "$(echo "$HEALTH" | grep -q healthy && echo pass || echo fail)"

check "Health endpoint: Redis connected" \
  "$(echo "$HEALTH" | grep -q connected && echo pass || echo fail)"

VERSION=$(curl -sf --max-time 10 \
  "$BASE_URL/version" 2>/dev/null || echo "{}")

check "Version endpoint responds" \
  "$(echo "$VERSION" | grep -q version && echo pass || echo fail)"

METRICS=$(curl -sf --max-time 10 \
  "$BASE_URL/metrics" 2>/dev/null || echo "")

check "Prometheus metrics exposed" \
  "$(echo "$METRICS" | grep -q http_requests_total && echo pass || echo fail)"

check "Business metrics (urls_shortened_total)" \
  "$(echo "$METRICS" | grep -q urls_shortened_total && echo pass || echo fail)"

FLAGS=$(curl -sf --max-time 10 \
  "$BASE_URL/flags" 2>/dev/null || echo "{}")

check "Feature flags endpoint" \
  "$(echo "$FLAGS" | grep -q flags && echo pass || echo fail)"

echo ""
echo "═══ End-to-End Flow ═══"

SHORTEN=$(curl -sf \
  -X POST "$BASE_URL/shorten" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://kubernetes.io"}' \
  2>/dev/null || echo "{}")

CODE=$(echo "$SHORTEN" | python3 -c \
  "import sys,json; print(json.load(sys.stdin).get('short_code',''))" \
  2>/dev/null)

check "URL shortening works" \
  "$([ -n "$CODE" ] && echo pass || echo fail)"

if [ -n "$CODE" ]; then

  REDIR=$(curl -sf \
    -o /dev/null \
    -w "%{http_code}" \
    "$BASE_URL/r/$CODE" \
    2>/dev/null || echo "000")

  check "Redirect works (HTTP $REDIR)" \
    "$(echo "$REDIR" | grep -q '^3' && echo pass || echo fail)"

  STATS=$(curl -sf \
    "$BASE_URL/stats/$CODE" \
    2>/dev/null || echo "{}")

  check "Stats endpoint works" \
    "$(echo "$STATS" | grep -q clicks && echo pass || echo fail)"
fi

echo ""
echo "═══ Security ═══"

NONROOT=$(kubectl get pod \
  -l component=app \
  -n url-shortener \
  -o name | head -1 | xargs -I{} \
  kubectl exec {} -n url-shortener -- whoami \
  2>/dev/null || echo "root")

check "Non-root user ($NONROOT)" \
  "$([ "$NONROOT" != "root" ] && echo pass || echo fail)"

NETPOL=$(kubectl get networkpolicy \
  -n url-shortener \
  --no-headers 2>/dev/null | wc -l)

check "Network policies exist ($NETPOL)" \
  "$([ $NETPOL -ge 1 ] && echo pass || echo fail)"

echo ""
echo "═══ Monitoring ═══"

PROM=$(kubectl get pods -n monitoring \
  -l app.kubernetes.io/name=prometheus \
  --field-selector=status.phase=Running \
  --no-headers 2>/dev/null | wc -l)

check "Prometheus running" \
  "$([ $PROM -ge 1 ] && echo pass || echo fail)"

GRAFANA=$(kubectl get pods -n monitoring \
  -l app.kubernetes.io/name=grafana \
  --field-selector=status.phase=Running \
  --no-headers 2>/dev/null | wc -l)

check "Grafana running" \
  "$([ $GRAFANA -ge 1 ] && echo pass || echo fail)"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "  Results: $PASS passed | $FAIL failed"
echo "╚══════════════════════════════════════════╝"

echo ""
echo "Access Points:"
echo "  App:        $BASE_URL"
echo "  Grafana:    http://$MINIKUBE_IP:30030"
echo ""
