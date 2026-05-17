# Production-Grade Kubernetes Platform — URL Shortener

A complete end-to-end DevOps/SRE capstone project demonstrating production-grade platform engineering practices using Kubernetes, Helm, Prometheus, Grafana, Redis, FastAPI, HPA, Network Policies, GitHub Actions, and operational automation.

---

# Architecture Overview

This project deploys a production-style URL shortener platform on Kubernetes.

It demonstrates:

* Kubernetes deployments and services
* Helm-based application packaging
* Prometheus metrics and alerting
* Grafana dashboards
* Structured JSON logging
* Health and readiness probes
* Redis integration
* Horizontal Pod Autoscaling (HPA)
* Network Policies
* CI/CD automation
* Smoke testing and operational scripts
* Production debugging workflows

---

# Technology Stack

| Component             | Purpose                       |
| --------------------- | ----------------------------- |
| FastAPI               | Backend application           |
| Redis                 | Data storage                  |
| Kubernetes            | Container orchestration       |
| Helm                  | Kubernetes package management |
| Prometheus            | Metrics collection            |
| Grafana               | Observability dashboards      |
| kube-prometheus-stack | Monitoring stack              |
| Docker                | Containerization              |
| Minikube              | Local Kubernetes cluster      |
| GitHub Actions        | CI/CD pipelines               |

---

# Project Structure

```bash
.
├── app/
│   ├── main.py
│   └── requirements.txt
│
├── helm/
│   └── url-shortener/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│
├── monitoring/
│   ├── grafana/
│   ├── loki/
│   └── prometheus/
│
├── scripts/
│   ├── deploy/
│   ├── ops/
│   └── test/
│
├── .github/
│   └── workflows/
│
├── Dockerfile
└── README.md
```

---

# Production Engineering Concepts Covered

## Kubernetes

This project demonstrates:

* Deployments
* Services
* ConfigMaps
* Secrets
* HPA
* Probes
* Resource limits
* Rolling updates
* Network Policies
* Pod metadata injection

---

## Observability

Implements the 4 Golden Signals:

| Signal     | Implementation                   |
| ---------- | -------------------------------- |
| Traffic    | Request counters                 |
| Errors     | HTTP error metrics               |
| Latency    | Prometheus histograms            |
| Saturation | Active requests + memory metrics |

---

## Security

* Non-root containers
* Network isolation using NetworkPolicies
* Secret management
* Least privilege design

---

## Reliability

* Readiness probes
* Liveness probes
* Graceful shutdown
* Rolling deployments
* HPA autoscaling
* Alerting rules

---

# Prerequisites

Install the following:

| Tool     | Version |
| -------- | ------- |
| Docker   | Latest  |
| kubectl  | v1.29+  |
| Minikube | Latest  |
| Helm     | v3+     |
| Python   | 3.11+   |
| Git      | Latest  |
|          |         |

---

# Recommended System Requirements

| Resource | Minimum |
| -------- | ------- |
| RAM      | 8 GB    |
| CPU      | 4 vCPU  |
| Disk     | 20 GB   |

This project runs:

* Kubernetes
* Prometheus
* Grafana
* Redis
* Monitoring stack
* Application workloads

Lower specs may cause instability.

---

# Step 1 — Clone Repository

```bash
git clone https://github.com/panche20/Day40-Final-Capstone-Complete-Production-Platform
cd day40-capstone
```

---

# Step 2 — Start Minikube

Start Minikube with production-style settings:

```bash
minikube start \
  --driver=docker \
  --memory=8192 \
  --cpus=4 \
  --disk-size=20GB \
  --kubernetes-version=v1.29.0 \
  --addons=metrics-server,ingress
```

Verify cluster:

```bash
kubectl get nodes
kubectl get pods -A
```

---

# Step 3 — Build Docker Images

IMPORTANT:

Minikube has its own Docker daemon.

Configure shell to use Minikube Docker:

```bash
eval $(minikube docker-env)
```

Build image:

```bash
docker build \
  --target production \
  --build-arg APP_VERSION=1.0.0 \
  --build-arg APP_COLOR=blue \
  -t url-shortener:v1.0.0 \
  -t url-shortener:latest \
  .
```

Verify image:

```bash
docker images | grep url-shortener
```

---

# Step 4 — Create Namespace

```bash
kubectl create namespace url-shortener
```

---

# Step 5 — Deploy Application Using Helm

Deploy application:

```bash
helm install url-shortener \
  ./helm/url-shortener \
  -n url-shortener
```

Verify deployment:

```bash
kubectl get all -n url-shortener
```

Expected:

* 2 application pods
* 1 Redis pod
* Services
* HPA
* NetworkPolicies

---

# Step 6 — Install Monitoring Stack

Add Helm repository:

```bash
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts

helm repo update
```

Create monitoring namespace:

```bash
kubectl create namespace monitoring
```

Install kube-prometheus-stack:

```bash
helm install prometheus \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values monitoring/prometheus/values.yaml \
  --wait \
  --timeout 15m
```

Verify:

```bash
kubectl get pods -n monitoring
```

---

# Step 7 — Deploy Alert Rules

```bash
kubectl apply -f monitoring/prometheus/alert-rules.yaml
```

Verify:

```bash
kubectl get prometheusrule -n monitoring
```

---

# Step 8 — Deploy Grafana Dashboard

```bash
kubectl apply -f monitoring/grafana/dashboard-configmap.yaml
```

---

# Step 9 — Access Application

IMPORTANT:

When running Minikube inside EC2 using Docker driver, NodePort networking may not work correctly.

Use port-forward instead.

Start port-forward:

```bash
kubectl port-forward \
  svc/url-shortener-app \
  -n url-shortener \
  8080:80
```

Access application:

```bash
http://localhost:8080
```

Health endpoint:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{
  "status": "healthy",
  "redis": "connected"
}
```

---

# Step 10 — Access Grafana

Port-forward Grafana:

```bash
kubectl port-forward \
  svc/prometheus-grafana \
  -n monitoring \
  3000:80
```

Open:

```bash
http://localhost:3000
```

Credentials:

```text
Username: admin
Password: admin123
```

---

# Step 11 — Access Prometheus

```bash
kubectl port-forward \
  svc/prometheus-kube-prometheus-prometheus \
  -n monitoring \
  9090:9090
```

Open:

```bash
http://localhost:9090
```

---

# Smoke Testing

Run smoke tests:

```bash
bash scripts/test/smoke-test.sh \
  http://localhost:8080 \
  1.0.0 \
  blue
```

The script validates:

* Health endpoints
* Metrics
* URL shortening
* Redirects
* Stats endpoints
* Feature flags
* Error handling

---

# Verification Script

Run:

```bash
bash scripts/test/final-verification.sh
```

This validates:

* Infrastructure
* Pods
* Monitoring
* Security
* Metrics
* CI/CD files
* End-to-end traffic flow

---

# Important Debugging Lessons

## 1. Services Healthy ≠ External Reachability

A Kubernetes service can be fully healthy internally while external traffic still fails.

Always debug layer-by-layer:

```text
Pod → Service → Ingress → External Client
```

---

## 2. Minikube Docker Driver Caveat

When using:

* Minikube
* Docker driver
* inside EC2

NodePort traffic may fail because:

```text
EC2 VM
  └── Docker container (Minikube node)
         └── Kubernetes NodePort
```

The NodePort exists inside Docker bridge networking.

Solution:

Use:

```bash
kubectl port-forward
```

instead of direct NodePort access.

---

# Common Troubleshooting Commands

## Check Pods

```bash
kubectl get pods -A
```

---

## Check Services

```bash
kubectl get svc -A
```

---

## Check Endpoints

```bash
kubectl get endpoints -A
```

---

## Check Logs

```bash
kubectl logs -l component=app -n url-shortener
```

---

## Describe Pod

```bash
kubectl describe pod <pod-name> -n url-shortener
```

---

## Helm Release Status

```bash
helm list -n url-shortener
helm status url-shortener -n url-shortener
```

---

# Interview Questions This Project Helps Answer

## Kubernetes

* Difference between liveness and readiness probes
* Rolling updates
* HPA internals
* NetworkPolicy behavior
* ConfigMaps vs Secrets
* Service discovery

---

## Observability

* Golden Signals
* Prometheus histograms
* Alerting strategies
* Recording rules
* Dashboard design

---

## DevOps/SRE

* Production debugging
* Reliability engineering
* Incident response
* Scaling workloads
* Platform architecture

---

# Production Improvements

Future enhancements:

* GitOps with ArgoCD
* External Secrets Operator
* Loki log aggregation
* Distributed tracing
* TLS everywhere
* Service mesh
* Multi-environment deployments
* Blue-green deployments
* Canary rollouts
* Redis HA
* Persistent storage

---

# Cleanup

Delete application:

```bash
helm uninstall url-shortener -n url-shortener
```

Delete monitoring stack:

```bash
helm uninstall prometheus -n monitoring
```

Delete namespaces:

```bash
kubectl delete namespace url-shortener
kubectl delete namespace monitoring
```

Stop Minikube:

```bash
minikube stop
```

Delete Minikube cluster:

```bash
minikube delete
```

---

# Key Engineering Takeaways

This project demonstrates that production engineering is not only about deploying applications.

It includes:

* observability
* security
* reliability
* scalability
* automation
* debugging
* operational excellence

The most valuable skill demonstrated here is systematic troubleshooting.

Real-world platform engineering is primarily:

```text
Observe → Isolate → Verify → Fix → Automate
```

---

# Author

Built as a production-grade DevOps/SRE capstone project.
