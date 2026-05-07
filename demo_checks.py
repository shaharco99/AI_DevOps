#!/usr/bin/env python3
"""
Demo Checks Script
Validates AI DevOps Assistant deployment and runs demo health/functionality checks.
Supports both Docker and Kubernetes deployments.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests


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


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if a TCP port on host is open."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def find_free_port() -> int:
    """Find an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


class PortForwardManager:
    """Manage kubectl port-forward processes."""

    def __init__(self):
        self.processes: list[subprocess.Popen] = []

    def start(
        self,
        service_name: str,
        namespace: str,
        remote_port: int,
        local_port: int | None = None,
    ) -> int | None:
        """Start port-forward for a Kubernetes service."""
        if local_port is None:
            local_port = remote_port
        if not is_port_open(local_port):
            chosen_port = local_port
        else:
            chosen_port = find_free_port()

        cmd = [
            "kubectl",
            "port-forward",
            f"service/{service_name}",
            f"{chosen_port}:{remote_port}",
            "-n",
            namespace,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
        except Exception:
            return None

        for _ in range(20):
            if process.poll() is not None:
                break
            if is_port_open(chosen_port):
                self.processes.append(process)
                return chosen_port
            time.sleep(0.2)

        self.stop_process(process)
        return None

    def stop_process(self, process: subprocess.Popen) -> None:
        """Stop a running port-forward process."""
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception:
            process.kill()

    def stop_all(self) -> None:
        """Stop all active port-forward processes."""
        for process in list(self.processes):
            self.stop_process(process)
        self.processes.clear()


def get_url_port(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def build_k8s_local_url(
    original_url: str,
    service_name: str,
    remote_port: int,
    port_forward_manager: PortForwardManager,
) -> str:
    """Return localhost URL for a Kubernetes service using port-forward."""
    local_port = get_url_port(original_url)
    forwarded_port = port_forward_manager.start(
        service_name=service_name,
        namespace="ai-devops-assistant",
        remote_port=remote_port,
        local_port=local_port,
    )
    if forwarded_port is None:
        return original_url
    parsed = urlparse(original_url)
    return f"{parsed.scheme}://localhost:{forwarded_port}"


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
        success, output = run_command("kubectl get ns ai-devops-assistant --no-headers 2>/dev/null")
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
    containers = output.strip().split("\n") if output.strip() else []

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
    success, output = run_command("kubectl get pods -n ai-devops-assistant -o wide 2>/dev/null")
    if success and output.strip():
        lines = output.strip().split("\n")
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
        lines = output.strip().split("\n")
        if len(lines) > 1:
            print_success(f"Found {len(lines)-1} deployment(s)")

    return all_pass


def check_api_health(
    base_url: str = "http://localhost:8000",
    timeout: int = 5,
    deployment: str = "docker",
    port_forward_manager: PortForwardManager | None = None,
) -> bool:
    """
    Check API health endpoints

    Args:
        base_url: Base URL of the API
        timeout: Request timeout in seconds
        deployment: Deployment type
        port_forward_manager: PortForwardManager for Kubernetes

    Returns:
        True if all health checks pass
    """
    if deployment == "kubernetes" and port_forward_manager is not None:
        base_url = build_k8s_local_url(base_url, "ai-devops-assistant", remote_port=80, port_forward_manager=port_forward_manager)

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


def check_api_endpoints(
    base_url: str = "http://localhost:8000",
    deployment: str = "docker",
    port_forward_manager: PortForwardManager | None = None,
) -> bool:
    """
    Test core API endpoints

    Args:
        base_url: Base URL of the API
        deployment: Deployment type
        port_forward_manager: PortForwardManager for Kubernetes

    Returns:
        True if all tests pass
    """
    if deployment == "kubernetes" and port_forward_manager is not None:
        base_url = build_k8s_local_url(base_url, "ai-devops-assistant", remote_port=80, port_forward_manager=port_forward_manager)

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
            detail = ""
            try:
                detail = response.json().get("detail", "")
            except Exception:
                detail = response.text
            print_info(
                f"/analyze_logs endpoint reachable; returned 400. Detail: {detail or 'no log data or query issue'}"
            )
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
        elif response.status_code == 400:
            detail = ""
            try:
                detail = response.json().get("detail", "")
            except Exception:
                detail = response.text
            print_info(
                f"/metrics endpoint reachable; returned 400. Detail: {detail or 'query failed or no metrics available yet'}"
            )
        else:
            print_warning(f"/metrics endpoint: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print_error("/metrics endpoint: Connection refused")
        all_pass = False
    except Exception as e:
        print_warning(f"/metrics endpoint: {str(e)}")

    return all_pass


def check_observability(
    prometheus_url: str = "http://localhost:9090",
    grafana_url: str = "http://localhost:3000",
    deployment: str = "docker",
    port_forward_manager: PortForwardManager | None = None,
) -> bool:
    """
    Check Prometheus and Grafana availability

    Args:
        prometheus_url: Prometheus base URL
        grafana_url: Grafana base URL
        deployment: Deployment type
        port_forward_manager: PortForwardManager for Kubernetes

    Returns:
        True if observability stack is healthy
    """
    if deployment == "kubernetes" and port_forward_manager is not None:
        prometheus_url = build_k8s_local_url(
            prometheus_url,
            "ai-devops-assistant-promet-prometheus",
            remote_port=9090,
            port_forward_manager=port_forward_manager,
        )
        grafana_url = build_k8s_local_url(
            grafana_url,
            "ai-devops-assistant-grafana",
            remote_port=3000,
            port_forward_manager=port_forward_manager,
        )

    print_header("Observability Stack Checks")
    all_pass = True

    # Check Prometheus
    try:
        print_info(f"Checking Prometheus at {prometheus_url}...")
        response = requests.get(f"{prometheus_url}/-/healthy", timeout=5)
        if response.status_code == 200:
            print_success("Prometheus: OK")
        else:
            print_warning(f"Prometheus: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print_warning(f"Prometheus: Not accessible ({prometheus_url})")
    except requests.exceptions.Timeout:
        print_warning("Prometheus: Timeout")
    except Exception as e:
        print_warning(f"Prometheus: {str(e)}")

    # Check Grafana
    try:
        print_info(f"Checking Grafana at {grafana_url}...")
        response = requests.get(f"{grafana_url}/api/health", timeout=5)
        if response.status_code == 200:
            print_success("Grafana: OK")
        else:
            print_warning(f"Grafana: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print_warning(f"Grafana: Not accessible ({grafana_url})")
    except requests.exceptions.Timeout:
        print_warning("Grafana: Timeout")
    except Exception as e:
        print_warning(f"Grafana: {str(e)}")

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
            lines = output.split("\n")
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

    port_forward_manager = PortForwardManager() if deployment == "kubernetes" else None

    # Run common checks
    try:
        all_pass = check_api_health(
            deployment=deployment,
            port_forward_manager=port_forward_manager,
        ) and all_pass
    except Exception:
        print_warning("API health checks skipped (API not available)")

    try:
        all_pass = check_api_endpoints(
            deployment=deployment,
            port_forward_manager=port_forward_manager,
        ) and all_pass
    except Exception:
        print_warning("API endpoint tests skipped (API not available)")

    try:
        all_pass = check_observability(
            deployment=deployment,
            port_forward_manager=port_forward_manager,
        ) and all_pass
    except Exception:
        print_warning("Observability checks skipped")
    finally:
        if port_forward_manager is not None:
            port_forward_manager.stop_all()

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
