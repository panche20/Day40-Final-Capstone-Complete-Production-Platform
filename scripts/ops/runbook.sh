#!/bin/bash
# Automated runbook — diagnostics for common incidents
# Run when you get paged. Gets you answers in < 2 minutes.
NAMESPACE="${1:-url-shortener}"

echo "╔══════════════════════════════════════╗"
echo "║  Incident Runbook: $NAMESPACE"
echo "╚══════════════════════════════════════╝"
echo ""

echo "1. Pod Status"
kubectl get pods -n $NAMESPACE -o wide
echo ""

echo "2. Recent Events (last 10 minutes)"
kubectl get events -n $NAMESPACE \
  --sort-by='.lastTimestamp' \
  --field-selector type=Warning 2>/dev/null | tail -10
echo ""

echo "3. Recent Error Logs"
kubectl logs -l component=app \
  -n $NAMESPACE \
  --since=5m \
  --tail=20 2>/dev/null | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        if d.get('level') in ('ERROR','WARNING','CRITICAL'):
            print(f'[{d[\"level\"]}] {d[\"message\"]}')
    except:
        print(line.rstrip())
" 2>/dev/null || echo "No recent errors"
echo ""

echo "4. Resource Usage"
kubectl top pods -n $NAMESPACE 2>/dev/null || \
  echo "Metrics server not available"
echo ""

echo "5. HPA Status"
kubectl get hpa -n $NAMESPACE 2>/dev/null || \
  echo "No HPA configured"
echo ""

echo "6. Redis Connectivity"
kubectl exec \
  $(kubectl get pod -l component=redis \
    -n $NAMESPACE -o name | head -1) \
  -n $NAMESPACE \
  -- redis-cli ping 2>/dev/null || echo "Redis unreachable"
echo ""

echo "7. Recent Deployments"
kubectl rollout history deployment \
  -n $NAMESPACE 2>/dev/null | tail -10
echo ""

echo "Runbook complete. Check Grafana for metrics visualization."
