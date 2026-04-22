"""Base tool class for DevOps tools."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Base class for all DevOps tools."""

    def __init__(self, name: str, description: str):
        """Initialize tool.
        
        Args:
            name: Tool name
            description: Tool description
        """
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute tool with given parameters.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            dict: Execution result
        """
        pass

    def validate_parameters(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate tool parameters.
        
        Args:
            **kwargs: Parameters to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        return True, None

    def get_schema(self) -> dict[str, Any]:
        """Get tool schema for LLM.
        
        Returns:
            dict: JSON schema of tool parameters
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    async def __call__(self, **kwargs) -> dict[str, Any]:
        """Call tool with validation.
        
        Args:
            **kwargs: Tool parameters
            
        Returns:
            dict: Execution result
        """
        # Validate
        is_valid, error_msg = self.validate_parameters(**kwargs)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg,
            }

        try:
            logger.info(f"Executing tool: {self.name} with args: {kwargs}")
            result = await self.execute(**kwargs)
            logger.info(f"Tool {self.name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool {self.name} execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }
