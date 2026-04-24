#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_NAME="${1:-ai-devops-assistant}"
NAMESPACE="${2:-ai-devops-assistant}"
VALUES_FILE="${3:-values.yaml}"
CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

on_error() {
  echo "Helm deployment failed. Collecting diagnostics..."
  helm status "${RELEASE_NAME}" -n "${NAMESPACE}" || true
  kubectl get pods -n "${NAMESPACE}" || true
  kubectl get events -n "${NAMESPACE}" --sort-by='.lastTimestamp' | tail -n 30 || true
}
trap on_error ERR

echo "Linting chart..."
helm lint "${CHART_DIR}"

echo "Rendering chart (sanity check)..."
helm template "${RELEASE_NAME}" "${CHART_DIR}" -f "${CHART_DIR}/${VALUES_FILE}" >/dev/null

echo "Deploying with atomic rollback on failure..."
helm upgrade --install "${RELEASE_NAME}" "${CHART_DIR}" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --atomic \
  --wait \
  --timeout 10m \
  -f "${CHART_DIR}/${VALUES_FILE}"

echo "Deployment succeeded."
