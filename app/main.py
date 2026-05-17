"""
URL Shortener — Production-Grade
Day 40 Final Capstone

This application demonstrates ALL production engineering concepts:
- Structured JSON logging (queryable in Loki)
- Prometheus metrics (Golden Signals)
- Health and readiness probes
- Feature flags
- Graceful shutdown
- Version/color endpoints for deployment verification
- Proper error handling with appropriate HTTP status codes
"""

import os
import sys
import time
import signal
import hashlib
import socket
import json
import logging
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import RedirectResponse, Response, JSONResponse
from pydantic import BaseModel
import redis
from prometheus_client import (
    Counter, Histogram, Gauge,
    generate_latest, CONTENT_TYPE_LATEST, REGISTRY
)

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# All configuration comes from environment variables.
# Why? Same Docker image runs in dev, staging, prod.
# Only the env vars change between environments.
# Never hardcode environment-specific values in code.
# ─────────────────────────────────────────────────────────────
APP_VERSION      = os.getenv("APP_VERSION", "1.0.0")
APP_COLOR        = os.getenv("APP_COLOR", "blue")
POD_NAME         = os.getenv("POD_NAME", socket.gethostname())
POD_NAMESPACE    = os.getenv("POD_NAMESPACE", "url-shortener")
NODE_NAME        = os.getenv("NODE_NAME", "unknown")
LOG_LEVEL        = os.getenv("LOG_LEVEL", "INFO").upper()
REDIS_HOST       = os.getenv("REDIS_HOST", "redis")
REDIS_PORT       = int(os.getenv("REDIS_PORT", 6379))

# ─────────────────────────────────────────────────────────────
# STRUCTURED LOGGING
# JSON format makes every field queryable in Loki/Splunk/ELK.
# With plain text logs: you need regex to extract fields.
# With JSON logs: query by any field directly.
#
# Example Loki query: {namespace="url-shortener"} | json | level="ERROR"
# This works because every field is a first-class citizen.
# ─────────────────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            # Standard fields present in EVERY log line
            # These are the labels/dimensions you filter by in Grafana
            "timestamp":  self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level":      record.levelname,
            "message":    record.getMessage(),
            "logger":     record.name,

            # Service identification
            # Lets you find all logs from this specific service
            "service":    "url-shortener",
            "version":    APP_VERSION,
            "color":      APP_COLOR,

            # Kubernetes context
            # Lets you find logs from a specific pod or node
            "pod":        POD_NAME,
            "namespace":  POD_NAMESPACE,
            "node":       NODE_NAME,
        }

        # Merge any extra fields passed to the logger
        # logger.info("msg", extra={"request_id": "abc", "user_id": "123"})
        for key, value in record.__dict__.items():
            if key not in (
                "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "funcName", "created", "msecs",
                "relativeCreated", "thread", "threadName", "processName",
                "process", "name", "exc_info", "exc_text", "stack_info",
                "message"
            ) and not key.startswith("_"):
                log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging():
    """Configure application logging"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    return logging.getLogger("url-shortener")


logger = setup_logging()

# ─────────────────────────────────────────────────────────────
# PROMETHEUS METRICS
# These are the Golden Signals plus business metrics.
#
# COUNTER: only goes up. Use rate() in PromQL.
#   http_requests_total — total requests received
#   urls_shortened_total — business KPI
#   redis_errors_total — infrastructure health
#
# HISTOGRAM: distribution of values. Use histogram_quantile().
#   http_request_duration_seconds — latency distribution
#   Enables p50, p95, p99 latency queries
#
# GAUGE: current value, can go up or down.
#   http_active_requests — real-time concurrency
#   redis_connected — binary health indicator
#
# Why measure business metrics (urls_shortened)?
# Infrastructure metrics (CPU, memory) tell you if the system
# is healthy. Business metrics tell you if it's WORKING.
# An app can be healthy but serving no useful traffic.
# ─────────────────────────────────────────────────────────────

# Golden Signal 1: Traffic
REQUEST_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

# Golden Signal 2: Errors (derived from REQUEST_TOTAL with status_code filter)

# Golden Signal 3: Latency
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    # Buckets cover range from fast (5ms) to very slow (10s)
    # Chose these to match realistic web app response times
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Golden Signal 4: Saturation
ACTIVE_REQUESTS = Gauge(
    "http_active_requests",
    "Currently in-flight HTTP requests"
)

# Business metrics
URLS_SHORTENED = Counter(
    "urls_shortened_total",
    "Total URLs shortened — primary business KPI"
)

REDIRECTS_SERVED = Counter(
    "redirects_served_total",
    "Total redirects served",
    ["short_code"]
)

# Infrastructure health
REDIS_CONNECTED = Gauge(
    "redis_connected",
    "Redis connection status: 1=connected, 0=disconnected"
)

REDIS_ERRORS = Counter(
    "redis_errors_total",
    "Redis operation errors",
    ["operation"]
)

# ─────────────────────────────────────────────────────────────
# REDIS CONNECTION
# ─────────────────────────────────────────────────────────────
def make_redis() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )


r = make_redis()

# ─────────────────────────────────────────────────────────────
# FEATURE FLAGS
# Stored in Redis so they update instantly without redeployment.
# This is the "feature flag" pattern:
# Deploy code → feature is disabled by default
# Enable flag → feature is live for target users
# Disable flag → instant rollback, no code change needed
# ─────────────────────────────────────────────────────────────
class FeatureFlags:
    DEFAULTS = {
        "analytics_enabled":    False,
        "custom_slugs_enabled": False,
        "rate_limit_enabled":   True,
        "v2_api_enabled":       False,
    }

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    def is_enabled(self, name: str, user_id: str = None) -> bool:
        try:
            raw = self._redis.get(f"ff:{name}")
            if raw is None:
                return self.DEFAULTS.get(name, False)

            val = json.loads(raw)

            if isinstance(val, bool):
                return val

            if isinstance(val, dict):
                if "percentage" in val and user_id:
                    bucket = int(hashlib.md5(
                        f"{name}:{user_id}".encode()
                    ).hexdigest(), 16) % 100
                    return bucket < val["percentage"]

                if "users" in val and user_id:
                    return user_id in val["users"]

                return val.get("enabled", False)

            return bool(val)

        except Exception:
            return self.DEFAULTS.get(name, False)

    def set(self, name: str, value) -> None:
        self._redis.set(f"ff:{name}", json.dumps(value))

    def get_all(self) -> dict:
        return {name: self.is_enabled(name) for name in self.DEFAULTS}


flags = FeatureFlags(r)

# ─────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="URL Shortener",
    description="Production-grade URL shortening service",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─────────────────────────────────────────────────────────────
# GRACEFUL SHUTDOWN
# When Kubernetes sends SIGTERM (pod deletion or rolling update),
# we need to:
# 1. Stop accepting NEW requests
# 2. Finish IN-FLIGHT requests
# 3. Close connections cleanly
#
# Without graceful shutdown: in-flight requests get 502 errors
# during every deployment. This causes visible errors in metrics.
#
# Kubernetes sequence:
# 1. Pod removed from Service endpoints (stops new traffic)
# 2. SIGTERM sent to pod (start shutdown)
# 3. Pod has terminationGracePeriodSeconds to finish
# 4. If not done: SIGKILL (force kill)
# ─────────────────────────────────────────────────────────────
shutdown_requested = False

def handle_sigterm(signum, frame):
    global shutdown_requested
    shutdown_requested = True
    logger.info("SIGTERM received — graceful shutdown initiated",
                extra={"event": "shutdown_start"})

signal.signal(signal.SIGTERM, handle_sigterm)

# ─────────────────────────────────────────────────────────────
# MIDDLEWARE — Request Instrumentation
# Runs for EVERY request, before and after the handler.
# This is where we add observability to all endpoints
# without touching each handler individually.
# ─────────────────────────────────────────────────────────────
@app.middleware("http")
async def instrument_requests(request: Request, call_next):
    """
    Middleware that adds to every request:
    1. Unique request ID (for log correlation across services)
    2. Prometheus metrics (latency, count, errors)
    3. Structured access log
    """
    # Reject new requests during shutdown
    if shutdown_requested:
        return JSONResponse(
            status_code=503,
            content={"error": "Service shutting down"}
        )

    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    status_code = 500

    # Normalize path to prevent high-cardinality metrics
    # /r/abc123, /r/def456 → /r/{code} (ONE time series)
    # Without this: N unique codes = N time series = OOM in Prometheus
    import re
    raw_path = request.url.path
    norm_path = re.sub(r'/r/[a-f0-9]{6}$', '/r/{code}', raw_path)
    norm_path = re.sub(r'/stats/[a-f0-9]{6}$', '/stats/{code}', norm_path)

    ACTIVE_REQUESTS.inc()

    try:
        request.state.request_id = request_id
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        logger.error(
            "Unhandled exception",
            extra={
                "event":      "unhandled_exception",
                "request_id": request_id,
                "error":      str(exc),
                "path":       raw_path,
            },
            exc_info=True
        )
        raise
    finally:
        duration = time.time() - start_time

        # Record metrics
        REQUEST_TOTAL.labels(
            method=request.method,
            endpoint=norm_path,
            status_code=str(status_code)
        ).inc()

        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=norm_path
        ).observe(duration)

        ACTIVE_REQUESTS.dec()

        # Structured access log
        log_method = (
            logger.warning if status_code >= 400
            else logger.info
        )
        log_method(
            f"{request.method} {raw_path} {status_code}",
            extra={
                "event":       "http_request",
                "request_id":  request_id,
                "method":      request.method,
                "path":        raw_path,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2),
            }
        )


# ─────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────
class ShortenRequest(BaseModel):
    url: str
    custom_slug: Optional[str] = None

class FlagRequest(BaseModel):
    value: object

# ─────────────────────────────────────────────────────────────
# OBSERVABILITY ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus scrape endpoint — called every 15s by Prometheus"""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/health")
def health():
    """
    Liveness probe — is the process alive?
    Kubernetes: if this fails 3 times → restart the pod.
    Returns 503 if Redis is unreachable (can't serve any requests).
    """
    try:
        r.ping()
        REDIS_CONNECTED.set(1)
        return {
            "status":  "healthy",
            "version": APP_VERSION,
            "color":   APP_COLOR,
            "pod":     POD_NAME,
            "redis":   "connected",
        }
    except redis.RedisError as e:
        REDIS_CONNECTED.set(0)
        REDIS_ERRORS.labels(operation="ping").inc()
        logger.error("Health check: Redis unreachable",
                     extra={"event": "redis_down", "error": str(e)})
        raise HTTPException(status_code=503, detail="Redis unavailable")

@app.get("/ready")
def ready():
    """
    Readiness probe — is the process ready for traffic?
    Kubernetes: if this fails → remove from load balancer (no restart).
    Use: pod is starting up, or temporarily overloaded.
    """
    try:
        r.ping()
        return {"status": "ready", "version": APP_VERSION}
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Not ready")

@app.get("/version")
def version():
    """
    Deployment verification endpoint.
    After blue-green switch: confirm correct version is serving.
    After canary: spot-check which version a request hit.
    """
    return {
        "version":    APP_VERSION,
        "color":      APP_COLOR,
        "pod":        POD_NAME,
        "namespace":  POD_NAMESPACE,
        "git_commit": os.getenv("GIT_COMMIT", "unknown"),
        "build_time": os.getenv("BUILD_TIME", "unknown"),
    }

# ─────────────────────────────────────────────────────────────
# FEATURE FLAG ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/flags")
def get_flags():
    """List all feature flags and their current values"""
    return {
        "flags":   flags.get_all(),
        "version": APP_VERSION,
    }

@app.post("/flags/{name}")
def set_flag(name: str, req: FlagRequest):
    """
    Set a feature flag value.
    Changes take effect immediately for all new requests.
    No deployment needed.
    """
    flags.set(name, req.value)
    logger.info(f"Feature flag updated",
                extra={"event": "flag_updated",
                       "flag": name, "value": str(req.value)})
    return {"flag": name, "value": req.value, "status": "updated"}

# ─────────────────────────────────────────────────────────────
# BUSINESS ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.post("/shorten")
def shorten(
    req: ShortenRequest,
    request: Request,
    x_user_id: Optional[str] = Header(None)
):
    """Shorten a URL"""
    user_id = x_user_id or "anonymous"
    request_id = getattr(request.state, "request_id", "unknown")

    # Custom slugs are feature-flagged
    if req.custom_slug:
        if not flags.is_enabled("custom_slugs_enabled", user_id):
            raise HTTPException(
                status_code=403,
                detail="Custom slugs not available for your account"
            )
        code = req.custom_slug
    else:
        code = hashlib.md5(
            f"{req.url}{time.time()}".encode()
        ).hexdigest()[:6]

    try:
        r.hset(f"url:{code}", mapping={
            "url":        req.url,
            "clicks":     0,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "version":    APP_VERSION,
        })

        URLS_SHORTENED.inc()

        logger.info(
            "URL shortened",
            extra={
                "event":      "url_shortened",
                "request_id": request_id,
                "code":       code,
                "user_id":    user_id,
            }
        )

        return {
            "short_code": code,
            "short_url":  f"/r/{code}",
        }

    except redis.RedisError as e:
        REDIS_ERRORS.labels(operation="hset").inc()
        logger.error(
            "Failed to store URL",
            extra={
                "event":      "shorten_failed",
                "request_id": request_id,
                "error":      str(e),
            }
        )
        raise HTTPException(status_code=503, detail="Storage unavailable")

@app.get("/r/{code}")
def redirect_url(code: str, request: Request):
    """Follow a short URL"""
    request_id = getattr(request.state, "request_id", "unknown")

    try:
        data = r.hgetall(f"url:{code}")
        if not data:
            raise HTTPException(status_code=404, detail="Short URL not found")

        r.hincrby(f"url:{code}", "clicks", 1)
        REDIRECTS_SERVED.labels(short_code=code).inc()

        logger.info(
            "Redirect served",
            extra={
                "event":      "redirect_served",
                "request_id": request_id,
                "code":       code,
            }
        )

        return RedirectResponse(url=data["url"])

    except redis.RedisError as e:
        REDIS_ERRORS.labels(operation="redirect").inc()
        raise HTTPException(status_code=503, detail="Storage unavailable")

@app.get("/stats/{code}")
def stats(code: str):
    """Get click statistics for a short URL"""
    try:
        data = r.hgetall(f"url:{code}")
        if not data:
            raise HTTPException(status_code=404, detail="Not found")
        return {
            "short_code": code,
            "url":        data["url"],
            "clicks":     int(data.get("clicks", 0)),
            "created_at": data.get("created_at", "unknown"),
            "version":    data.get("version", "unknown"),
        }
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Storage unavailable")

@app.get("/")
def root():
    return {
        "service":  "URL Shortener",
        "version":  APP_VERSION,
        "color":    APP_COLOR,
        "pod":      POD_NAME,
        "docs":     "/docs",
        "health":   "/health",
        "metrics":  "/metrics",
        "flags":    "/flags",
    }
