#!/usr/bin/env bash
set -Eeuo pipefail

# Default values
RELEASE_NAME="${1:-ai-devops-assistant}"
NAMESPACE="${2:-ai-devops-assistant}"
VALUES_FILE="${3:-values.yaml}"
CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMEOUT="${TIMEOUT:-3m}"
DRY_RUN="${DRY_RUN:-false}"
DEBUG="${DEBUG:-false}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

on_error() {
  log_error "Helm deployment failed. Collecting diagnostics..."
  echo

  log_info "Checking release status..."
  helm status "${RELEASE_NAME}" -n "${NAMESPACE}" 2>/dev/null || log_warn "Release not found"

  echo
  log_info "Checking pods..."
  kubectl get pods -n "${NAMESPACE}" --sort-by='.status.startTime' || log_warn "Failed to get pods"

  echo
  log_info "Checking recent events..."
  kubectl get events -n "${NAMESPACE}" --sort-by='.lastTimestamp' | tail -n 20 || log_warn "Failed to get events"

  echo
  log_info "Checking helm history..."
  helm history "${RELEASE_NAME}" -n "${NAMESPACE}" 2>/dev/null || log_warn "No history available"

  exit 1
}
trap on_error ERR

# Validate prerequisites
command -v helm >/dev/null 2>&1 || { log_error "Helm is required but not installed. Aborting."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { log_error "kubectl is required but not installed. Aborting."; exit 1; }

log_info "Starting deployment of ${RELEASE_NAME} to namespace ${NAMESPACE}"
log_info "Using values file: ${VALUES_FILE}"
echo

# Check if namespace exists, create if not
if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  log_info "Creating namespace ${NAMESPACE}..."
  kubectl create namespace "${NAMESPACE}"
fi

# Add required Helm repositories
log_info "Ensuring required Helm repositories are available..."

# Bitnami repo for PostgreSQL
if ! helm repo list | grep -q "bitnami"; then
  log_info "Adding Bitnami Helm repository..."
  helm repo add bitnami https://charts.bitnami.com/bitnami
fi

# Ollama Helm repo
if ! helm repo list | grep -q "otwld"; then
  log_info "Adding Ollama Helm repository..."
  helm repo add otwld https://otwld.github.io/ollama-helm/
fi

# Prometheus community repo (for kube-prometheus-stack)
if ! helm repo list | grep -q "prometheus-community"; then
  log_info "Adding Prometheus Community Helm repository..."
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
fi

# Grafana repo
if ! helm repo list | grep -q "grafana"; then
  log_info "Adding Grafana Helm repository..."
  helm repo add grafana https://grafana.github.io/helm-charts
fi

# Chroma repo (if available)
if ! helm repo list | grep -q "chroma"; then
  log_info "Adding Chroma Helm repository..."
  helm repo add chroma https://charts.chroma.dev || log_warn "Chroma Helm repo not available, will use built-in template"
fi

log_info "Updating Helm repositories..."
helm repo update

# If Minikube is available, load the local app image so the cluster can use it directly.
if command -v minikube >/dev/null 2>&1 && minikube status >/dev/null 2>&1; then
  if docker image inspect ai-devops-backend:latest >/dev/null 2>&1; then
    log_info "Loading local image ai-devops-backend:latest into Minikube..."
    minikube image load ai-devops-backend:latest || log_warn "Failed to load local image into Minikube"
  fi
fi

echo
log_info "Linting chart..."
helm lint "${CHART_DIR}"

echo
log_info "Validating chart dependencies..."
helm dependency update "${CHART_DIR}" || log_warn "Some dependencies may not be available"

echo
if [[ "${DRY_RUN}" == "true" ]]; then
  log_info "Performing dry-run deployment..."
  helm template "${RELEASE_NAME}" "${CHART_DIR}" \
    --namespace "${NAMESPACE}" \
    --values "${CHART_DIR}/${VALUES_FILE}" \
    --debug="${DEBUG}"
else
  log_info "Rendering chart (sanity check)..."
  helm template "${RELEASE_NAME}" "${CHART_DIR}" \
    --namespace "${NAMESPACE}" \
    --values "${CHART_DIR}/${VALUES_FILE}" >/dev/null

  echo
  log_info "Deploying with rollback-on-failure..."
  helm upgrade --install "${RELEASE_NAME}" "${CHART_DIR}" \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --rollback-on-failure \
    --wait \
    --timeout "${TIMEOUT}" \
    --values "${CHART_DIR}/${VALUES_FILE}" \
    --debug="${DEBUG}"

  echo
  log_success "Deployment succeeded!"

  echo
  log_info "Post-deployment status:"
  helm status "${RELEASE_NAME}" -n "${NAMESPACE}"

  echo
  log_info "Pod status:"
  kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE_NAME}"

  echo
  log_info "Service status:"
  kubectl get services -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE_NAME}"

  # Check if ingress is enabled and show URL
  if helm get values "${RELEASE_NAME}" -n "${NAMESPACE}" | grep -q "ingress.*enabled.*true"; then
    echo
    log_info "Ingress status:"
    kubectl get ingress -n "${NAMESPACE}" -l "app.kubernetes.io/instance=${RELEASE_NAME}"
  fi

  echo
  log_success "🎉 Deployment completed successfully!"
  log_info "You can access the application using the service information above."
fi
