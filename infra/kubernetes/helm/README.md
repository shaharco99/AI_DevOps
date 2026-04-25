# AI DevOps Assistant Helm Chart

This Helm chart deploys the complete AI DevOps Assistant platform with all its dependencies, monitoring, and observability components.

## What is Helm?

Helm is a package manager for Kubernetes that simplifies the deployment and management of complex applications. It uses "charts" (packages) that contain all the Kubernetes manifests needed to deploy an application, along with templating and configuration management.

### Key Benefits of Helm:
- **Templating**: Parameterize your Kubernetes manifests
- **Dependency Management**: Manage complex applications with multiple components
- **Version Control**: Version your deployments and roll back easily
- **Reusability**: Share and reuse charts across environments
- **Atomic Operations**: Deploy or rollback entire applications as a unit

## Helm vs kubectl

| Feature | kubectl | Helm |
|---------|---------|------|
| **Deployment Method** | Apply individual YAML files | Use packaged charts with templating |
| **Dependency Management** | Manual ordering and management | Automatic dependency resolution |
| **Configuration** | Edit YAML files directly | Values files with inheritance |
| **Versioning** | Manual version tracking | Built-in chart versioning |
| **Rollback** | Manual manifest reversion | Single command rollback |
| **Sharing** | Copy YAML files | Publish to chart repositories |
| **Complexity** | Simple for single resources | Better for complex applications |

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- kubectl configured to access your cluster

## Installation

### Quick Start

```bash
# Add required repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add otwld https://otwld.github.io/ollama-helm/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install the chart
helm install ai-devops-assistant ./helm \
  --namespace ai-devops-assistant \
  --create-namespace
```

### Using the Deploy Script

The included `deploy.sh` script provides a comprehensive deployment experience:

```bash
# Deploy with default settings
./helm/deploy.sh

# Deploy to custom namespace
./helm/deploy.sh my-release my-namespace

# Deploy with production values
./helm/deploy.sh my-release my-namespace values-production.yaml

# Dry run to see what would be deployed
DRY_RUN=true ./helm/deploy.sh
```

## Configuration

### Values Files

- `values.yaml`: Default configuration for development/testing
- `values-production.yaml`: Production-ready configuration with security hardening

### Key Configuration Options

#### Global Settings
```yaml
global:
  imageRegistry: "ghcr.io"
  storageClass: "fast-ssd"
```

#### Application Configuration
```yaml
replicaCount: 3
image:
  tag: "v1.0.0"
env:
  LOG_LEVEL: "WARNING"
  LLM_PROVIDER: "ollama"
```

#### Database Configuration
```yaml
postgresql:
  enabled: true
  auth:
    existingSecret: "postgres-secret"
```

#### External Secrets (Production)
```yaml
externalSecrets:
  enabled: true
  secretStore:
    name: "vault-backend"
```

#### Security
```yaml
podSecurityContext:
  runAsNonRoot: true
securityContext:
  readOnlyRootFilesystem: true
```

#### Monitoring
```yaml
prometheus:
  enabled: true
grafana:
  enabled: true
serviceMonitor:
  enabled: true
```

## Components Deployed

This chart deploys the following components:

1. **AI DevOps Assistant**: Main application
2. **PostgreSQL**: Database for metadata
3. **Ollama**: Local LLM inference service
4. **Chroma**: Vector database for RAG
5. **Prometheus**: Metrics collection
6. **Grafana**: Dashboard and visualization
7. **Ingress**: External access (optional)
8. **Network Policies**: Security policies (optional)

## Upgrading

```bash
# Upgrade to new version
helm upgrade ai-devops-assistant ./helm

# Upgrade with new values
helm upgrade ai-devops-assistant ./helm -f new-values.yaml
```

## Rollback

```bash
# See revision history
helm history ai-devops-assistant

# Rollback to previous version
helm rollback ai-devops-assistant 1
```

## Troubleshooting

### Check Deployment Status
```bash
helm status ai-devops-assistant
kubectl get pods -n ai-devops-assistant
```

### View Logs
```bash
kubectl logs -n ai-devops-assistant deployment/ai-devops-assistant
```

### Debug Template Rendering
```bash
helm template ai-devops-assistant ./helm --debug
```

### Common Issues

1. **PVC Pending**: Check storage class availability
   ```bash
   kubectl get storageclass
   ```

2. **Image Pull Errors**: Check image registry access
   ```bash
   kubectl describe pod <pod-name>
   ```

3. **Service Unavailable**: Check service and ingress configuration
   ```bash
   kubectl get services,ingress -n ai-devops-assistant
   ```

## Security Considerations

### Production Deployment
- Use `values-production.yaml` for hardened security
- Enable external secrets management
- Configure network policies
- Use TLS/SSL for ingress
- Implement proper RBAC

### Secrets Management
The chart supports multiple secrets management approaches:

1. **Built-in Secrets**: Store secrets in `values.yaml` (not recommended for production)
2. **External Secrets Operator**: Use Vault, AWS Secrets Manager, etc.
3. **Existing Kubernetes Secrets**: Reference pre-created secrets

## Monitoring and Observability

When enabled, the chart deploys:
- **Prometheus**: Scrapes metrics from all components
- **Grafana**: Provides dashboards for visualization
- **ServiceMonitors**: Automatic service discovery

Access Grafana at: `http://<ingress-host>/grafana`

## Backup and Recovery

### Database Backup
```bash
# Backup PostgreSQL
kubectl exec -n ai-devops-assistant deployment/postgresql -- pg_dumpall -U postgres > backup.sql
```

### Application Data
```bash
# Backup PVC data
kubectl cp ai-devops-assistant/<pod-name>:/app/data ./backup-data
```

## Uninstalling

```bash
# Uninstall the release
helm uninstall ai-devops-assistant

# Remove PVCs (WARNING: This deletes data)
kubectl delete pvc -l app.kubernetes.io/instance=ai-devops-assistant

# Remove namespace
kubectl delete namespace ai-devops-assistant
```

## Development

### Local Development
```bash
# Use minikube or kind for local testing
helm install ai-devops-assistant ./helm --set postgresql.persistence.enabled=false
```

### Chart Development
```bash
# Lint the chart
helm lint ./helm

# Test template rendering
helm template test-release ./helm

# Validate dependencies
helm dependency update ./helm
```

## Migration from kubectl

If you're currently using kubectl manifests, you can migrate to Helm:

1. **Backup your current deployment**
2. **Identify your configuration values**
3. **Install the Helm chart with equivalent values**
4. **Verify the deployment**
5. **Remove old kubectl resources**

The Helm chart maintains backward compatibility with the existing kubectl manifests while providing additional features and easier management.
