# Quick Reference: Managing Secrets

## TL;DR - Quick Start

### Local Development (Recommended)

```bash
# 1. Copy the example file
cp .env.local.example .env.local

# 2. Edit with your secrets (NEVER commit this file)
nano .env.local

# 3. Run with docker-compose or locally
docker compose up -d
# or
source venv/bin/activate
python -m ai_devops_assistant.main
```

**Important**: `.env.local` is in `.gitignore` - it will NOT be committed to git.

---

## Local Development Setup

### Option A: Environment File (.env.local) - ✅ Easiest

**Best for**: Local development, testing

```bash
# Setup
cp .env.local.example .env.local
# Edit .env.local with your credentials
```

**Credentials needed:**
- `SECRET_KEY` - Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `DATABASE_URL` - Your database connection string
- `AZURE_DEVOPS_PAT` - From https://dev.azure.com/_usersSettings/tokens
- `JENKINS_API_TOKEN` - From Jenkins User Configure
- `GITHUB_TOKEN` - From https://github.com/settings/tokens

### Option B: Secrets Files (.secrets/)

**Best for**: Docker Compose local development

```bash
# Setup
mkdir .secrets
echo "your-secret-key" > .secrets/secret_key
echo "your-db-url" > .secrets/database_url
echo "your-pat" > .secrets/azure_devops_pat
echo "your-jenkins-token" > .secrets/jenkins_api_token
echo "your-github-token" > .secrets/github_token

# Run with docker-compose
docker compose up -d
```

**Note**: `.secrets/` is in `.gitignore` - it won't be committed.

---

## Production Deployment

### Kubernetes (Recommended)

```bash
# Use the setup script
./infra/kubernetes/setup-secrets.sh

# Or manually create secrets:
kubectl create secret generic ai-devops-secrets \
  --from-literal=SECRET_KEY="your-key" \
  --from-literal=AZURE_DEVOPS_PAT="your-pat" \
  # ... other secrets

# Verify
kubectl get secret ai-devops-secrets -n ai-devops-assistant
```

### External Secrets Operator (ESO) - Best Practice

For automated secret management from AWS Secrets Manager, Azure Key Vault, or HashiCorp Vault:

```bash
# See infra/kubernetes/external-secrets-config.yaml for examples
# Requirements:
# 1. ESO installed
# 2. Cloud provider credentials configured
# 3. Secrets created in your secret manager

kubectl apply -f infra/kubernetes/external-secrets-config.yaml
```

---

## Rotation & Security

### Generate New Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Create Personal Access Tokens

**Azure DevOps:**
1. Go to https://dev.azure.com/_usersSettings/tokens
2. Create new token with "Code (read & write)" scope
3. Copy and save (shown only once!)

**Jenkins:**
1. Go to Jenkins > User > Configure
2. Click "Add new Token"
3. Copy API token

**GitHub:**
1. Go to https://github.com/settings/tokens
2. Create new token (classic) with `repo` and `workflow` scopes
3. Copy token

---

## Emergency: I Committed a Secret! 🚨

```bash
# 1. Stop using that secret immediately
# 2. Rotate the credential in the source system
# 3. Remove from git history:
git filter-branch --tree-filter 'rm -f .env.local' HEAD
# 4. Or use git-secret or BFG Repo-Cleaner
```

---

## Verify Secrets Are Loaded

```bash
# Check environment variables are set
python -c "import os; print(os.getenv('SECRET_KEY') and '✓' or '✗ NOT SET')"

# Check Kubernetes secret exists
kubectl get secret ai-devops-secrets -n ai-devops-assistant

# View secret keys (not values)
kubectl describe secret ai-devops-secrets -n ai-devops-assistant
```

---

## File Structure for Reference

```
ai-devops-assistant/
├── .env                       # ❌ NEVER commit (in .gitignore)
├── .env.local                 # ❌ NEVER commit (in .gitignore)
├── .env.example               # ✅ Safe to commit (no secrets)
├── .env.local.example         # ✅ Safe to commit (template)
├── .secrets/                  # ❌ NEVER commit (in .gitignore)
│   ├── secret_key
│   ├── azure_devops_pat
│   └── github_token
├── SECRETS_MANAGEMENT.md      # ✅ Safe (documentation)
├── infra/
│   └── kubernetes/
│       ├── secret.yaml        # ⚠️ Template only (no real values)
│       ├── external-secrets-config.yaml  # ✅ Safe (ESO config)
│       └── setup-secrets.sh   # ✅ Safe (helper script)
└── docker-compose.yml         # ✅ Safe (uses .env.local)
```

---

## Common Issues

### ❌ Secret not loading

```bash
# Check if .env.local exists
ls -la .env.local

# Check syntax
cat .env.local | grep -E "^[A-Z_]+=" # Should see key=value pairs

# Check in application
python -c "from ai_devops_assistant.config.settings import Settings; print(Settings().SECRET_KEY)"
```

### ❌ Docker can't find secrets

```bash
# Verify .env.local is in the working directory
pwd
ls -la .env.local

# Check docker compose is reading it
docker compose config | grep SECRET_KEY
```

### ❌ Kubernetes secret not injecting

```bash
# Verify secret exists
kubectl get secret ai-devops-secrets -n ai-devops-assistant

# Check pod is using it
kubectl describe pod <pod-name> -n ai-devops-assistant | grep -i secret

# Check environment inside pod
kubectl exec <pod-name> -n ai-devops-assistant -- env | grep SECRET_KEY
```

---

## Related Documentation

- **Full guide**: See [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md)
- **Kubernetes**: See [infra/kubernetes/README.md](./infra/kubernetes/README.md)
- **External Secrets**: See [infra/kubernetes/external-secrets-config.yaml](./infra/kubernetes/external-secrets-config.yaml)
- **Setup helper**: Run `./infra/kubernetes/setup-secrets.sh`

