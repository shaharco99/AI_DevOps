"""Model listing for the UI's model picker."""

import logging

from fastapi import APIRouter

from ai_devops_assistant.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models() -> dict:
    """List models available from the configured provider.

    Degrades to the configured default rather than failing: a model picker that
    cannot reach the provider should not stop anyone from chatting.

    Returns:
        dict: available model names and the current default
    """
    default = settings.LLM_MODEL
    models: list[str] = []

    try:
        from ai_devops_assistant.services.llm_service import get_llm_service

        service = await get_llm_service()
        lister = getattr(service, "list_models", None)
        if lister is not None:
            listed = await lister()
            models = [m for m in listed if isinstance(m, str)]
    except Exception as e:
        logger.warning(f"Could not list models: {e}")

    if default and default not in models:
        models.insert(0, default)

    return {"models": models, "default": default}
