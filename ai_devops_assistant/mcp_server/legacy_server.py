from __future__ import annotations

import os
import platform
import re
import shlex
import subprocess
import tempfile

import yaml
from dotenv import load_dotenv
from fastmcp import FastMCP
from kubernetes import client, config
from kubernetes.client import Configuration

mcp = FastMCP('DevOps Tools')


# =============================
# Utilities
# =============================
def run_cmd(cmd: str):
    args = shlex.split(cmd)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    return result.stdout


def load_kube():
    load_dotenv()
    home = os.environ.get('HOME') or os.path.expanduser('~')
    is_windows = platform.system() == 'Windows'

    kube_path = os.environ.get('KUBECONFIG')
    if not kube_path:
        kube_path = (
            os.path.join(os.environ.get('USERPROFILE', ''), '.kube', 'config')
            if is_windows
            else os.path.join(home, '.kube', 'config')
        )

    if not os.path.exists(kube_path):
        raise FileNotFoundError(f"Kubeconfig not found at {kube_path}")

    with open(kube_path, 'r') as f:
        kube_cfg = yaml.safe_load(f)

    if not is_windows:
        for cluster in kube_cfg.get('clusters', []):
            ca = cluster.get('cluster', {}).get('certificate-authority')
            if ca and (ca.startswith('C:') or '\\' in ca):
                cluster['cluster']['certificate-authority'] = '/root/.minikube/ca.crt'
            server = cluster.get('cluster', {}).get('server')
            if server and '127.0.0.1' in server:
                port = re.search(r':(\d+)$', server)
                cluster['cluster']['server'] = (
                    f"https://host.docker.internal:{port.group(1) if port else '8443'}"
                )

        for user in kube_cfg.get('users', []):
            for key in ['client-certificate', 'client-key']:
                path = user.get('user', {}).get(key)
                if path and (path.startswith('C:') or '\\' in path):
                    user['user'][key] = path.replace(
                        'C:\\Users\\shahar\\.minikube\\', '/root/.minikube/'
                    ).replace('\\', '/')

        with tempfile.NamedTemporaryFile('w', delete=False) as tmp:
            yaml.safe_dump(kube_cfg, tmp)
            kube_path = tmp.name

    config.load_kube_config(config_file=kube_path)

    # Disable SSL verification for Linux/Docker
    if not is_windows:
        conf = Configuration.get_default_copy()
        conf.verify_ssl = False
        Configuration.set_default(conf)

    contexts, active_context = config.list_kube_config_contexts()
    return (
        active_context['context']['namespace']
        if active_context and 'namespace' in active_context['context']
        else 'default'
    )


# =============================
# kubectl Tools
# =============================
@mcp.tool()
def kubectl(namespace: str = None, args: str = 'get namespaces'):
    if any(tok in args for tok in [';', '|', '>', '<']):
        return '❌ Unsafe kubectl args detected'
    ns_flag = f"-n {namespace}" if namespace else ''
    cmd = f"kubectl {args} {ns_flag}".strip()
    return run_cmd(cmd)


@mcp.tool()
def run_shell(cmd: str):
    allowed_prefixes = ['kubectl ', 'docker ', 'helm ']
    if not any(cmd.strip().startswith(p) for p in allowed_prefixes):
        return '❌ Command not allowed'
    if any(tok in cmd for tok in [';', '|', '>', '<']):
        return '❌ Unsafe characters in command'
    return run_cmd(cmd)


@mcp.tool()
def run_python_script(script: str):
    result = subprocess.run(['python', '-c', script], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else result.stderr


@mcp.tool()
def cluster_overview():
    ns = load_kube()
    v1 = client.CoreV1Api()
    apps = client.AppsV1Api()

    namespaces = [n.metadata.name for n in v1.list_namespace().items]
    pods = [p.metadata.name for p in v1.list_namespaced_pod(ns).items]
    deployments = [d.metadata.name for d in apps.list_namespaced_deployment(ns).items]

    return (
        f"🌍 Cluster Overview\n"
        f"📂 Active Namespace: {ns}\n"
        f"📂 All Namespaces: {', '.join(namespaces)}\n\n"
        f"🐳 Pods in {ns}: {', '.join(pods) if pods else '(none)'}\n"
        f"📦 Deployments in {ns}: {', '.join(deployments) if deployments else '(none)'}"
    )


# =============================
# Run MCP Server
# =============================
if __name__ == '__main__':
    mcp.run(transport='http', host='0.0.0.0', port=8000)
