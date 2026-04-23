# Secrets Management Best Practices

This document outlines the recommended approaches for managing sensitive credentials in the AI DevOps Assistant application.

## ⚠️ Security Principles

1. **Never commit secrets to version control** - Even in private repositories
2. **Use environment-specific secret management** - Different approaches for dev, staging, and production
3. **Rotate secrets regularly** - Implement a rotation policy
4. **Audit access** - Log who accesses secrets and when
5. **Use principle of least privilege** - Grant only necessary permissions

## Sensitive Credentials Requiring Protection

The following must be stored securely:

- `SECRET_KEY` - Application secret for session/token signing
- `DATABASE_URL` - Database connection string with credentials
- `AZURE_DEVOPS_PAT` - Azure DevOps Personal Access Token
- `JENKINS_API_TOKEN` - Jenkins API authentication token
- `GITHUB_TOKEN` - GitHub Personal Access Token

## Local Development Setup

### Option 1: `.env.local` File (Recommended for Local Development)

1. Create `.env.local` in the project root (automatically ignored by `.gitignore`):

```bash
# .env.local - DO NOT COMMIT THIS FILE
SECRET_KEY=your-local-development-secret-key-only-for-local-use
DATABASE_URL=postgresql+asyncpg://devops_user:devops_password@localhost:5432/devops
AZURE_DEVOPS_ORG=your-org
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_PAT=your-pat-token
JENKINS_USER=your-jenkins-user
JENKINS_API_TOKEN=your-jenkins-token
GITHUB_OWNER=your-github-user
GITHUB_REPO=your-repo
GITHUB_TOKEN=your-github-token
```

2. The application reads from `.env.local` automatically (via Pydantic settings)

3. Generate a strong SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Production Deployment Strategies

### Strategy 1: External Secrets Operator (ESO) - Recommended for Kubernetes

Best for cloud-native deployments with multiple secret sources.

#### Setup with AWS Secrets Manager

1. Install External Secrets Operator:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets \
  external-secrets/external-secrets \
  -n external-secrets-system \
  --create-namespace
```

2. Create AWS credentials for ESO:

```bash
kubectl create secret generic awssm-secret \
  --from-literal=access-key=$AWS_ACCESS_KEY_ID \
  --from-literal=secret-access-key=$AWS_SECRET_ACCESS_KEY \
  -n ai-devops-assistant
```

3. Create SecretStore:

```yaml
# infra/kubernetes/secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-store
  namespace: ai-devops-assistant
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        secretRef:
          accessKeyID:
            name: awssm-secret
            key: access-key
          secretAccessKey:
            name: awssm-secret
            key: secret-access-key
```

4. Create ExternalSecret:

```yaml
# infra/kubernetes/external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ai-devops-external-secret
  namespace: ai-devops-assistant
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-store
    kind: SecretStore
  target:
    name: ai-devops-secrets
    creationPolicy: Owner
  data:
    - secretKey: SECRET_KEY
      remoteRef:
        key: ai-devops/secret-key
    - secretKey: DATABASE_URL
      remoteRef:
        key: ai-devops/database-url
    - secretKey: AZURE_DEVOPS_PAT
      remoteRef:
        key: ai-devops/azure-devops-pat
    - secretKey: JENKINS_API_TOKEN
      remoteRef:
        key: ai-devops/jenkins-api-token
    - secretKey: GITHUB_TOKEN
      remoteRef:
        key: ai-devops/github-token
```

Apply with:

```bash
kubectl apply -f infra/kubernetes/secret-store.yaml
kubectl apply -f infra/kubernetes/external-secret.yaml
```

### Strategy 2: Sealed Secrets

For GitOps workflows with encrypted secrets in git.

1. Install Sealed Secrets controller:

```bash
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml
```

2. Install kubeseal CLI:

```bash
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/kubeseal-0.18.0-linux-amd64.tar.gz
tar xfz kubeseal-0.18.0-linux-amd64.tar.gz
sudo install -m 755 kubeseal /usr/local/bin/kubeseal
```

3. Create a secret YAML:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ai-devops-secrets
  namespace: ai-devops-assistant
type: Opaque
stringData:
  SECRET_KEY: "your-actual-secret-key"
  DATABASE_URL: "your-database-url"
  AZURE_DEVOPS_PAT: "your-pat"
  JENKINS_API_TOKEN: "your-token"
  GITHUB_TOKEN: "your-token"
```

4. Seal the secret:

```bash
kubeseal -f secret.yaml -w sealed-secret.yaml
```

5. Commit only `sealed-secret.yaml` to git:

```bash
git add infra/kubernetes/sealed-secret.yaml
git rm infra/kubernetes/secret.yaml
```

### Strategy 3: HashiCorp Vault

For complex secret management with advanced features.

1. Deploy Vault:

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault \
  -n vault \
  --create-namespace \
  -f vault-values.yaml
```

2. Initialize and unseal Vault (follow Vault documentation)

3. Store secrets:

```bash
vault write secret/ai-devops \
  SECRET_KEY="your-secret-key" \
  DATABASE_URL="your-db-url" \
  AZURE_DEVOPS_PAT="your-pat" \
  JENKINS_API_TOKEN="your-token" \
  GITHUB_TOKEN="your-token"
```

4. Configure Kubernetes auth and secret injection (see Vault Kubernetes integration docs)

### Strategy 4: Cloud Provider Native Solutions

**AWS Secrets Manager:**

```bash
aws secretsmanager create-secret \
  --name ai-devops-secrets \
  --secret-string '{
    "SECRET_KEY": "value",
    "DATABASE_URL": "value",
    "AZURE_DEVOPS_PAT": "value",
    "JENKINS_API_TOKEN": "value",
    "GITHUB_TOKEN": "value"
  }'
```

**Azure Key Vault:**

```bash
az keyvault secret set --vault-name MyKeyVault --name SECRET_KEY --value "value"
az keyvault secret set --vault-name MyKeyVault --name DATABASE_URL --value "value"
# ... etc
```

**Google Cloud Secret Manager:**

```bash
echo -n "your-secret-value" | gcloud secrets create SECRET_KEY --data-file=-
echo -n "your-db-url" | gcloud secrets create DATABASE_URL --data-file=-
# ... etc
```

## Docker Compose Development

For local Docker Compose development:

1. Create a `.secrets` directory (not committed):

```bash
mkdir .secrets
echo "your-secret-key" > .secrets/secret_key
echo "your-db-url" > .secrets/database_url
# ... etc
```

2. Update `docker-compose.yml`:

```yaml
services:
  api:
    environment:
      SECRET_KEY_FILE: /run/secrets/secret_key
      DATABASE_URL_FILE: /run/secrets/database_url
    secrets:
      - secret_key
      - database_url

secrets:
  secret_key:
    file: ./.secrets/secret_key
  database_url:
    file: ./.secrets/database_url
```

3. Ensure `.secrets/` is in `.gitignore` ✓ (already configured)

## Rotation Strategy

Implement secret rotation to minimize breach impact:

1. **Scheduled Rotation** - Rotate every 30-90 days
2. **Event-Driven Rotation** - After employee departure or suspected compromise
3. **Dual-Running** - Support old and new secrets during rotation period
4. **Automated Monitoring** - Alert on rotation failures

Example for scheduled rotation with AWS:

```bash
# Rotation Lambda function
aws secretsmanager rotate-secret \
  --secret-id ai-devops-secrets \
  --rotation-rules AutomaticallyAfterDays=30
```

## Audit & Access Control

1. **Enable audit logging** for all secret access
2. **Use RBAC** to limit who can access secrets
3. **Monitor access patterns** for anomalies
4. **Document access** to secrets

Example Kubernetes RBAC:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: secret-reader
  namespace: ai-devops-assistant
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get"]
  resourceNames: ["ai-devops-secrets"]
```

## Environment Variables at Runtime

The application supports reading secrets from environment variables:

```python
# ai_devops_assistant/config/settings.py
SECRET_KEY: str = os.getenv("SECRET_KEY", "default-insecure-key")
DATABASE_URL: str = os.getenv("DATABASE_URL", "...")
AZURE_DEVOPS_PAT: Optional[str] = os.getenv("AZURE_DEVOPS_PAT")
```

## GitHub Actions Secrets

For CI/CD pipelines, use GitHub Secrets:

```bash
# Via GitHub CLI
gh secret set SECRET_KEY --body "your-secret-key"
gh secret set AZURE_DEVOPS_PAT --body "your-pat"
```

Usage in workflows:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        env:
          SECRET_KEY: ${{ secrets.SECRET_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: pytest
```

## Compliance Considerations

- **SOC 2** - Implement encryption and audit trails
- **HIPAA** - If handling healthcare data, ensure HIPAA-compliant secret management
- **PCI-DSS** - For payment data, use PCI-compliant solutions
- **GDPR** - Document data processing and retention policies

## Quick Reference

| Environment | Recommended | Setup Effort |
|-------------|-------------|--------------|
| Local Dev   | `.env.local` | ⭐ Low       |
| Docker Dev  | `.secrets/`  | ⭐ Low       |
| Staging     | Sealed Secrets or ESO | ⭐⭐ Medium |
| Production  | External Secrets Operator or Vault | ⭐⭐⭐ High |
| CI/CD       | Platform Secrets (GitHub/GitLab) | ⭐ Low |

## Implementation Checklist

- [ ] Remove all plaintext secrets from version control
- [ ] Set up `.env.local` for local development
- [ ] Configure `.gitignore` properly
- [ ] Document secret structure in `.env.example`
- [ ] Choose production secret management strategy
- [ ] Implement encryption for sensitive data in transit
- [ ] Set up audit logging for secret access
- [ ] Establish secret rotation policy
- [ ] Test secret injection in all environments
- [ ] Document backup and disaster recovery procedures

## References

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [CIS Kubernetes Benchmark](https://www.cisecurity.org/cis-benchmarks/)
- [Kubernetes Secret Best Practices](https://kubernetes.io/docs/concepts/configuration/secret/)
- [External Secrets Operator Documentation](https://external-secrets.io/)
- [Sealed Secrets Documentation](https://sealed-secrets.netlify.app/)

