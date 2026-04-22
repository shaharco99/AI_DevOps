# Kubernetes Deployment

This directory contains Kubernetes manifests for deploying the AI DevOps Copilot to a Kubernetes cluster.

## Prerequisites

- Kubernetes cluster (v1.19+)
- kubectl configured to access the cluster
- Storage class for persistent volumes (optional, defaults will work with most clusters)

## Quick Start

1. Create the namespace:

```bash
kubectl apply -f namespace.yaml
```

2. Deploy the database:

```bash
kubectl apply -f postgres.yaml
```

3. Deploy Ollama (LLM service):

```bash
kubectl apply -f ollama.yaml
```

4. Deploy Chroma (vector database):

```bash
kubectl apply -f chroma.yaml
```

5. Deploy the main application:

```bash
kubectl apply -f deployment.yaml
```

6. Deploy monitoring:

```bash
kubectl apply -f prometheus.yaml
kubectl apply -f grafana.yaml
```

## Full Deployment

Deploy everything at once:

```bash
kubectl apply -f .
```

## Check Deployment Status

```bash
# Check pods
kubectl get pods -n ai-devops-copilot

# Check services
kubectl get services -n ai-devops-copilot

# Check persistent volumes
kubectl get pvc -n ai-devops-copilot
```

## Access the Application

### Via Port Forwarding

```bash
# Main application
kubectl port-forward -n ai-devops-copilot svc/ai-devops-copilot 8080:80

# Grafana
kubectl port-forward -n ai-devops-copilot svc/grafana 3000:3000

# Prometheus
kubectl port-forward -n ai-devops-copilot svc/prometheus 9090:9090
```

Then access:
- Application: http://localhost:8080
- API Docs: http://localhost:8080/docs
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

### Via Ingress

If you have an ingress controller, update the ingress host in `deployment.yaml` and access via the configured domain.

## Configuration

### Environment Variables

The deployment uses ConfigMaps and Secrets for configuration:

- `ai-devops-copilot-config`: Application configuration
- `ai-devops-copilot-secrets`: Sensitive data (database credentials, API keys)

### Database Initialization

After deploying PostgreSQL, you may need to run database migrations:

```bash
# Get a shell in the application pod
kubectl exec -n ai-devops-copilot -it deployment/ai-devops-copilot -- /bin/bash

# Run migrations
alembic upgrade head
```

### LLM Model Setup

Ollama will automatically pull the llama3 model on startup. If you need other models:

```bash
# Get a shell in the Ollama pod
kubectl exec -n ai-devops-copilot -it deployment/ollama -- /bin/bash

# Pull additional models
ollama pull mistral
```

## Scaling

### Horizontal Scaling

Scale the application deployment:

```bash
kubectl scale deployment ai-devops-copilot -n ai-devops-copilot --replicas=3
```

### Resource Management

Update resource requests/limits in the deployment manifests based on your cluster capacity.

## Monitoring

### Application Metrics

The application exposes Prometheus metrics at `/metrics`. Grafana dashboards are pre-configured.

### Logs

View application logs:

```bash
kubectl logs -n ai-devops-copilot -l app=ai-devops-copilot -f
```

## Troubleshooting

### Common Issues

1. **Pods not starting**: Check resource availability and storage
2. **Database connection errors**: Verify PostgreSQL pod is running and credentials are correct
3. **LLM not responding**: Check Ollama pod logs and model availability
4. **Vector database issues**: Check Chroma pod logs

### Debug Commands

```bash
# Check pod status
kubectl describe pod <pod-name> -n ai-devops-copilot

# Check logs
kubectl logs <pod-name> -n ai-devops-copilot

# Check events
kubectl get events -n ai-devops-copilot

# Check resource usage
kubectl top pods -n ai-devops-copilot
```

## Security Considerations

- Change default Grafana credentials
- Use Kubernetes secrets for sensitive data
- Configure network policies for pod-to-pod communication
- Enable RBAC and restrict service accounts
- Use TLS for ingress when deploying to production

## Production Deployment

For production:

1. Use external PostgreSQL database
2. Configure proper TLS certificates
3. Set up proper monitoring and alerting
4. Configure backup strategies
5. Use Kubernetes operators for better management
6. Implement proper CI/CD for deployments

## Cleanup

Remove all resources:

```bash
kubectl delete namespace ai-devops-copilot
```