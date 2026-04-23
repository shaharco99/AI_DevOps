#!/bin/bash
# infra/kubernetes/setup-secrets.sh
# Script to help set up secrets for the AI DevOps Assistant in Kubernetes
#
# This script demonstrates different approaches for secret management
# Choose one based on your infrastructure and requirements

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

NAMESPACE="ai-devops-assistant"

# ==============================================================================
# Option 1: Manual kubectl create-secret
# ==============================================================================
function setup_manual_secrets() {
    echo -e "${BLUE}Setting up secrets using kubectl...${NC}"
    
    read -p "SECRET_KEY: " SECRET_KEY
    read -p "DATABASE_URL: " DATABASE_URL
    read -p "AZURE_DEVOPS_ORG: " AZURE_DEVOPS_ORG
    read -p "AZURE_DEVOPS_PROJECT: " AZURE_DEVOPS_PROJECT
    read -s -p "AZURE_DEVOPS_PAT: " AZURE_DEVOPS_PAT
    echo ""
    read -s -p "JENKINS_API_TOKEN: " JENKINS_API_TOKEN
    echo ""
    read -s -p "GITHUB_TOKEN: " GITHUB_TOKEN
    echo ""
    
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    kubectl create secret generic ai-devops-secrets \
        --from-literal=SECRET_KEY="$SECRET_KEY" \
        --from-literal=DATABASE_URL="$DATABASE_URL" \
        --from-literal=AZURE_DEVOPS_ORG="$AZURE_DEVOPS_ORG" \
        --from-literal=AZURE_DEVOPS_PROJECT="$AZURE_DEVOPS_PROJECT" \
        --from-literal=AZURE_DEVOPS_PAT="$AZURE_DEVOPS_PAT" \
        --from-literal=JENKINS_USER="$JENKINS_USER" \
        --from-literal=JENKINS_API_TOKEN="$JENKINS_API_TOKEN" \
        --from-literal=GITHUB_OWNER="$GITHUB_OWNER" \
        --from-literal=GITHUB_REPO="$GITHUB_REPO" \
        --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN" \
        -n $NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    echo -e \"${GREEN}Secrets created successfully!${NC}\"
}

# ==============================================================================
# Option 2: From files in .secrets directory
# ==============================================================================
function setup_from_files() {
    echo -e \"${BLUE}Setting up secrets from files...${NC}\"
    
    SECRETS_DIR=\".secrets\"
    
    if [ ! -d \"$SECRETS_DIR\" ]; then
        echo -e \"${RED}Error: .secrets directory not found${NC}\"
        echo \"Create .secrets directory with the following files:\"
        echo \"  - secret_key\"
        echo \"  - database_url\"
        echo \"  - azure_devops_org\"
        echo \"  - azure_devops_project\"
        echo \"  - azure_devops_pat\"
        echo \"  - jenkins_user\"
        echo \"  - jenkins_api_token\"
        echo \"  - github_owner\"
        echo \"  - github_repo\"
        echo \"  - github_token\"
        exit 1
    fi
    
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    kubectl create secret generic ai-devops-secrets \\
        --from-file=SECRET_KEY=$SECRETS_DIR/secret_key \\
        --from-file=DATABASE_URL=$SECRETS_DIR/database_url \\
        --from-file=AZURE_DEVOPS_ORG=$SECRETS_DIR/azure_devops_org \\
        --from-file=AZURE_DEVOPS_PROJECT=$SECRETS_DIR/azure_devops_project \\
        --from-file=AZURE_DEVOPS_PAT=$SECRETS_DIR/azure_devops_pat \\
        --from-file=JENKINS_USER=$SECRETS_DIR/jenkins_user \\
        --from-file=JENKINS_API_TOKEN=$SECRETS_DIR/jenkins_api_token \\
        --from-file=GITHUB_OWNER=$SECRETS_DIR/github_owner \\
        --from-file=GITHUB_REPO=$SECRETS_DIR/github_repo \\
        --from-file=GITHUB_TOKEN=$SECRETS_DIR/github_token \\
        -n $NAMESPACE \\
        --dry-run=client -o yaml | kubectl apply -f -
    
    echo -e \"${GREEN}Secrets created from files!${NC}\"
}

# ==============================================================================
# Option 3: Using External Secrets Operator (ESO)
# ==============================================================================
function setup_eso_aws() {
    echo -e \"${BLUE}Setting up External Secrets Operator for AWS Secrets Manager...${NC}\"
    echo \"\"
    echo \"This requires:\"
    echo \"1. External Secrets Operator installed (helm install external-secrets ...)\"
    echo \"2. AWS credentials configured for ESO\"
    echo \"3. Secrets already created in AWS Secrets Manager\"
    echo \"\"
    echo \"Please set these up first before running this option.\"
    echo \"\"
    echo \"Example AWS secret creation:\"
    echo \"  aws secretsmanager create-secret --name ai-devops-secrets \\\"
    echo \"    --secret-string '{\\\"SECRET_KEY\\\": \\\"value\\\", ...}'\"
}

# ==============================================================================
# List current secrets
# ==============================================================================
function list_secrets() {
    echo -e \"${BLUE}Current secrets in $NAMESPACE:${NC}\"
    kubectl get secrets -n $NAMESPACE
    echo \"\"
    echo -e \"${BLUE}Secret keys in ai-devops-secrets:${NC}\"
    kubectl describe secret ai-devops-secrets -n $NAMESPACE || echo \"Secret not found\"
}

# ==============================================================================
# Delete secrets (use with caution!)
# ==============================================================================
function delete_secrets() {
    echo -e \"${RED}WARNING: This will delete all secrets in $NAMESPACE${NC}\"
    read -p \"Are you sure? Type 'yes' to confirm: \" confirm
    if [ \"$confirm\" = \"yes\" ]; then
        kubectl delete secret ai-devops-secrets -n $NAMESPACE 2>/dev/null || echo \"Secret not found\"
        echo -e \"${GREEN}Secrets deleted${NC}\"
    else
        echo \"Cancelled\"
    fi
}

# ==============================================================================
# Verify secrets
# ==============================================================================
function verify_secrets() {
    echo -e \"${BLUE}Verifying secrets...${NC}\"
    
    if ! kubectl get secret ai-devops-secrets -n $NAMESPACE &> /dev/null; then
        echo -e \"${RED}✗ Secret ai-devops-secrets not found${NC}\"
        return 1
    fi
    
    echo -e \"${GREEN}✓ Secret exists${NC}\"
    
    required_keys=(\"SECRET_KEY\" \"DATABASE_URL\" \"AZURE_DEVOPS_PAT\" \"JENKINS_API_TOKEN\" \"GITHUB_TOKEN\")
    
    for key in \"${required_keys[@]}\"; do
        if kubectl get secret ai-devops-secrets -n $NAMESPACE -o jsonpath=\"{.data.$key}\" &> /dev/null; then
            echo -e \"${GREEN}✓ $key${NC}\"
        else
            echo -e \"${YELLOW}⚠ $key (not found)${NC}\"
        fi
    done
}

# ==============================================================================
# Main menu
# ==============================================================================
function show_menu() {
    echo -e \"${BLUE}AI DevOps Assistant - Kubernetes Secrets Setup${NC}\"
    echo \"\"
    echo \"1) Setup secrets manually (interactive)\"
    echo \"2) Setup secrets from files (.secrets directory)\"
    echo \"3) Setup with External Secrets Operator (ESO)\"
    echo \"4) List current secrets\"
    echo \"5) Verify secrets\"
    echo \"6) Delete secrets (WARNING!)\"
    echo \"7) Exit\"
    echo \"\"
    read -p \"Select an option (1-7): \" choice
    
    case $choice in
        1) setup_manual_secrets ;;
        2) setup_from_files ;;
        3) setup_eso_aws ;;
        4) list_secrets ;;
        5) verify_secrets ;;
        6) delete_secrets ;;
        7) echo \"Exiting...\"; exit 0 ;;
        *) echo \"Invalid option\"; show_menu ;;
    esac
    
    echo \"\"
    read -p \"Press Enter to continue...\"
    clear
    show_menu
}

# ==============================================================================
# Main
# ==============================================================================
if [ \"$#\" -eq 0 ]; then
    clear
    show_menu
else
    case \"$1\" in
        manual) setup_manual_secrets ;;
        files) setup_from_files ;;
        list) list_secrets ;;
        verify) verify_secrets ;;
        delete) delete_secrets ;;
        *) echo \"Usage: $0 {manual|files|list|verify|delete|eso}\"; exit 1 ;;
    esac
fi
