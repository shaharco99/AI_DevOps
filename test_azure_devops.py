"""Test Azure DevOps pipeline tool integration."""

import asyncio
import os
from ai_devops_assistant.tools.pipeline_tool import PipelineTool


async def test_azure_devops_connection():
    """Test Azure DevOps API connection."""
    # Set test environment variables (replace with your values)
    os.environ["AZURE_DEVOPS_URL"] = "https://dev.azure.com"
    os.environ["AZURE_DEVOPS_ORG"] = "your-org"
    os.environ["AZURE_DEVOPS_PROJECT"] = "your-project"
    os.environ["AZURE_DEVOPS_PAT"] = "your-pat"

    tool = PipelineTool()

    # Test getting recent builds
    result = await tool.execute(action="get_recent_builds")
    print("Recent builds result:")
    print(result)

    if result.get("success") and result.get("builds"):
        # Test getting details of first build
        first_build_id = str(result["builds"][0]["id"])
        details_result = await tool.execute(
            action="get_build_details",
            build_id=first_build_id
        )
        print(f"\nBuild {first_build_id} details:")
        print(details_result)


if __name__ == "__main__":
    asyncio.run(test_azure_devops_connection())