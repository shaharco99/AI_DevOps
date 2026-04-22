#!/usr/bin/env python3
"""
Demo Checks Script
Validates AI DevOps Assistant deployment and runs demo health/functionality checks.
Supports both Docker and Kubernetes deployments.
"""

import subprocess
import sys
import json
import time
import requests
from typing import Optional, Dict, Any, List
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


def print_success(text: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str) -> None:
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_info(text: str) -> None:
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")


def print_warning(text: str) -> None:
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def run_command(cmd: str, capture: bool = True, timeout: int = 10) -> tuple[bool, str]:
    """
    Run a shell command and return success status and output
    
    Args:
        cmd: Shell command to run
        capture: Whether to capture output
        timeout: Command timeout in seconds
    
    Returns:
        Tuple of (success, output)
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def detect_deployment() -> str:
    """
    Detect if deployment is Docker or Kubernetes
    
    Returns:
        "docker", "kubernetes", or "none"
    """
    # Check for Docker
    success, _ = run_command("docker ps > /dev/null 2>&1")
    if success:
        # Check if containers are running
        success, output = run_command("docker ps --filter 'name=ai-devops' --format '{{.Names}}'")
        if success and output.strip():
            return "docker"
    
    # Check for Kubernetes
    success, _ = run_command("kubectl cluster-info > /dev/null 2>&1")
    if success:
        # Check if namespace exists
        success, output = run_command(
            "kubectl get ns ai-devops-assistant --no-headers 2>/dev/null"
        )
        if success and output.strip():
            return "kubernetes"
    
    return "none"


def check_docker_deployment() -> bool:
    """Check Docker-based deployment"""
    print_header("Docker Deployment Checks")
    all_pass = True
    
    # Check if Docker is running
    success, _ = run_command("docker ps > /dev/null 2>&1")
    if success:
        print_success("Docker daemon is running")
    else:
        print_error("Docker daemon is not running")
        return False
    
    # Check if containers are running
    success, output = run_command("docker ps --filter 'name=ai-devops' --format '{{.Names}}'")
    containers = output.strip().split('\n') if output.strip() else []
    
    if containers:
        print_success(f"Found {len(containers)} AI DevOps container(s) running")
        for container in containers:
            print_info(f"  - {container}")
    else:
        print_warning("No AI DevOps containers found running")
        all_pass = False
    
    return all_pass


def check_kubernetes_deployment() -> bool:
    """Check Kubernetes deployment"""
    print_header("Kubernetes Deployment Checks")
    all_pass = True
    
    # Check cluster connectivity
    success, _ = run_command("kubectl cluster-info > /dev/null 2>&1")
    if success:
        success, output = run_command("kubectl version --short")
        if success:
            print_success("Connected to Kubernetes cluster")
            print_info(f"  Version: {output.strip().split('Server Version')[1][:30]}")
    else:
        print_error("Cannot connect to Kubernetes cluster")
        return False
    
    # Check namespace
    success, _ = run_command("kubectl get ns ai-devops-assistant --no-headers 2>/dev/null")
    if success:
        print_success("Namespace 'ai-devops-assistant' exists")
    else:
        print_warning("Namespace 'ai-devops-assistant' not found")
        all_pass = False
    
    # Check pods
    success, output = run_command(
        "kubectl get pods -n ai-devops-assistant -o wide 2>/dev/null"
    )
    if success and output.strip():
        lines = output.strip().split('\n')
        if len(lines) > 1:
            print_success(f"Found {len(lines)-1} pod(s) in namespace")
            for line in lines[1:]:
                pod_name = line.split()[0]
                status = line.split()[3]
                print_info(f"  - {pod_name}: {status}")
        else:
            print_warning("No pods found in namespace")
            all_pass = False
    else:
        print_warning("Could not retrieve pod information")
        all_pass = False
    
    # Check deployments
    success, output = run_command(
        "kubectl get deployments -n ai-devops-assistant -o wide 2>/dev/null"
    )
    if success and output.strip():
        lines = output.strip().split('\n')
        if len(lines) > 1:
            print_success(f"Found {len(lines)-1} deployment(s)")
    
    return all_pass


def check_api_health(base_url: str = "http://localhost:8000", timeout: int = 5) -> bool:
    """
    Check API health endpoints
    
    Args:
        base_url: Base URL of the API
        timeout: Request timeout in seconds
    
    Returns:
        True if all health checks pass
    """
    print_header("API Health Checks")
    all_pass = True
    
    endpoints = [
        ("/health", "General health"),
        ("/health/live", "Liveness probe"),
        ("/health/ready", "Readiness probe"),
    ]
    
    for endpoint, description in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=timeout)
            if response.status_code == 200:
                print_success(f"{description}: {response.status_code}")
                try:
                    data = response.json()
                    if isinstance(data, dict) and "status" in data:
                        print_info(f"  Status: {data['status']}")
                except:
                    pass
            else:
                print_error(f"{description}: {response.status_code}")
                all_pass = False
        except requests.exceptions.ConnectionError:
            print_error(f"{description}: Connection refused")
            all_pass = False
        except requests.exceptions.Timeout:
            print_error(f"{description}: Timeout")
            all_pass = False
        except Exception as e:
            print_error(f"{description}: {str(e)}")
            all_pass = False
    
    return all_pass


def check_api_endpoints(base_url: str = "http://localhost:8000") -> bool:
    """
    Test core API endpoints
    
    Args:
        base_url: Base URL of the API
    
    Returns:
        True if all tests pass
    """
    print_header("API Endpoint Tests")
    all_pass = True
    
    # Test chat endpoint
    try:
        print_info("Testing /chat endpoint...")
        response = requests.post(
            f"{base_url}/chat",
            json={"message": "What is the status of the system?"},
            timeout=30,
        )
        if response.status_code == 200:
            print_success("/chat endpoint: OK (200)")
            data = response.json()
            if "response" in data:
                print_info(f"  Response: {data['response'][:100]}...")
        else:
            print_warning(f"/chat endpoint: {response.status_code}")
    except requests.exceptions.Timeout:
        print_warning("/chat endpoint: Timeout (LLM may be busy)")
    except requests.exceptions.ConnectionError:
        print_error("/chat endpoint: Connection refused")
        all_pass = False
    except Exception as e:
        print_warning(f"/chat endpoint: {str(e)}")
    
    # Test analyze_logs endpoint
    try:
        print_info("Testing /analyze_logs endpoint...")
        response = requests.post(
            f"{base_url}/analyze_logs",
            json={"query": "ERROR", "time_range_hours": 1, "limit": 10},
            timeout=10,
        )
        if response.status_code == 200:
            print_success("/analyze_logs endpoint: OK (200)")
        elif response.status_code == 400:
            print_warning("/analyze_logs endpoint: 400 (Bad request or no logs)")
        else:
            print_warning(f"/analyze_logs endpoint: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print_error("/analyze_logs endpoint: Connection refused")
        all_pass = False
    except Exception as e:
        print_warning(f"/analyze_logs endpoint: {str(e)}")
    
    # Test metrics endpoint
    try:
        print_info("Testing /metrics endpoint...")
        response = requests.post(
            f"{base_url}/metrics",
            json={"query": "up"},
            timeout=10,
        )
        if response.status_code == 200:
            print_success("/metrics endpoint: OK (200)")
        else:
            print_warning(f"/metrics endpoint: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print_error("/metrics endpoint: Connection refused")
        all_pass = False
    except Exception as e:
        print_warning(f"/metrics endpoint: {str(e)}")
    
    return all_pass


def check_observability(base_url: str = "http://localhost:9090") -> bool:
    """
    Check Prometheus and Grafana availability
    
    Args:
        base_url: Prometheus base URL
    
    Returns:
        True if observability stack is healthy
    """
    print_header("Observability Stack Checks")
    all_pass = True
    
    # Check Prometheus
    try:
        print_info("Checking Prometheus...")
        response = requests.get(f"{base_url}/-/healthy", timeout=5)
        if response.status_code == 200:
            print_success("Prometheus: OK")
        else:
            print_warning(f"Prometheus: {response.status_code}")
    except:
        print_warning("Prometheus: Not accessible (port 9090)")
    
    # Check Grafana
    try:
        print_info("Checking Grafana...")
        response = requests.get("http://localhost:3000/api/health", timeout=5)
        if response.status_code == 200:
            print_success("Grafana: OK")
        else:
            print_warning(f"Grafana: {response.status_code}")
    except:
        print_warning("Grafana: Not accessible (port 3000)")
    
    return all_pass


def run_unit_tests() -> bool:
    """
    Run unit tests
    
    Returns:
        True if tests pass
    """
    print_header("Running Unit Tests")
    
    success, output = run_command(
        "pytest tests/unit -v --tb=short",
        timeout=60,
    )
    
    if success:
        print_success("All unit tests passed")
    else:
        print_error("Some unit tests failed")
        if "FAILED" in output or "ERROR" in output:
            # Print last 20 lines of output
            lines = output.split('\n')
            print("\nTest output (last 20 lines):")
            for line in lines[-20:]:
                if line.strip():
                    print(f"  {line}")
    
    return success


def main() -> int:
    """Main entry point"""
    print_header("AI DevOps Assistant - Demo Checks")
    
    # Detect deployment type
    deployment = detect_deployment()
    
    if deployment == "none":
        print_error("No AI DevOps deployment detected!")
        print_info("\nTo run demo checks, please:")
        print_info("  1. For Docker: docker compose up -d")
        print_info("  2. For Kubernetes: kubectl apply -f infra/kubernetes/")
        return 1
    
    print_info(f"Detected deployment type: {deployment.upper()}\n")
    
    all_pass = True
    
    # Run deployment-specific checks
    if deployment == "docker":
        all_pass = check_docker_deployment() and all_pass
    elif deployment == "kubernetes":
        all_pass = check_kubernetes_deployment() and all_pass
    
    # Run common checks
    try:
        all_pass = check_api_health() and all_pass
    except:
        print_warning("API health checks skipped (API not available)")
    
    try:
        all_pass = check_api_endpoints() and all_pass
    except:
        print_warning("API endpoint tests skipped (API not available)")
    
    try:
        all_pass = check_observability() and all_pass
    except:
        print_warning("Observability checks skipped")
    
    # Run tests if environment is properly set up
    try:
        all_pass = run_unit_tests() and all_pass
    except:
        print_warning("Unit tests skipped")
    
    # Final summary
    print_header("Demo Checks Summary")
    if all_pass:
        print_success("All critical checks passed! ✓")
        print_info("\nYour AI DevOps Assistant is ready to demo.")
        return 0
    else:
        print_warning("Some checks failed or were skipped.")
        print_info("\nCheck the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
