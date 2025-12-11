"""
UI routes for agentic workflow pages.
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.dependencies import templates
from src.services.provider_model_catalog import load_catalog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workflow-ui"])


@router.get("/workflow", response_class=HTMLResponse)
async def workflow_page(request: Request):
    """Unified workflow management page with tabs."""
    return templates.TemplateResponse(
        "workflow.html",
        {
            "request": request,
            "provider_model_catalog": load_catalog(),
        }
    )


@router.get("/workflow/config", response_class=HTMLResponse)
async def workflow_config_page_redirect(request: Request):
    """Redirect to unified workflow page config tab."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/workflow#config", status_code=302)


@router.get("/workflow/execution", response_class=HTMLResponse)
async def workflow_execution_page_redirect(request: Request):
    """Redirect to unified workflow page executions tab."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/workflow#executions", status_code=302)


@router.get("/workflow/executions", response_class=HTMLResponse)
async def workflow_executions_page_redirect(request: Request):
    """Redirect to unified workflow page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/workflow#executions", status_code=302)


@router.get("/workflow/queue", response_class=HTMLResponse)
async def workflow_queue_page_redirect(request: Request):
    """Redirect to unified workflow page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/workflow#queue", status_code=302)

