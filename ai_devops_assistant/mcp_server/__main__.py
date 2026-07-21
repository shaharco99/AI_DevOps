"""Entrypoint: python -m ai_devops_assistant.mcp_server

Run from the same image as the API, as a separate container. Separate containers
rather than separate images means one build, but independent scaling, independent
NetworkPolicy and an independent blast radius.
"""

from ai_devops_assistant.config.logging import setup_logging
from ai_devops_assistant.mcp_server.server import run

if __name__ == "__main__":
    setup_logging()
    run()
