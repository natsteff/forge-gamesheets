"""Admin-only server-rendered bulk FORGE Reprint maintenance UI."""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.library.reprint_maintenance import (
    OPERATIONS,
    ReprintJobError,
    cancel_job,
    create_job,
    inventory,
    job_detail,
    preview,
    recent_jobs,
    resume_job,
    start_worker,
)
from app.preferences import get_preferences
from app.web import _format_local_timestamp, templates

router = APIRouter()


def _settings(request: Request):
    return request.app.state.settings


def _start(request: Request, job_id: int) -> None:
    settings = _settings(request)
    thread = start_worker(
        request.app.state.database,
        settings.library_path,
        settings.data_path,
        settings.base_url,
        job_id,
    )
    request.app.state.reprint_worker = thread


@router.get(
    "/settings/reprints", response_class=HTMLResponse, name="reprint_maintenance"
)
def reprint_maintenance(request: Request):
    settings = _settings(request)
    summary = inventory(
        request.app.state.database,
        settings.library_path,
        settings.data_path,
        settings.base_url,
    )
    timezone_name = get_preferences(request.app.state.database).timezone_name
    jobs = tuple(
        {
            **job,
            "display_time": _format_local_timestamp(
                job["created_at"], timezone_name
            ),
        }
        for job in recent_jobs(request.app.state.database)
    )
    return templates.TemplateResponse(
        request=request,
        name="reprint_maintenance.html",
        context={
            "inventory": summary,
            "operations": OPERATIONS,
            "recent_jobs": jobs,
            "generation_enabled": bool(settings.base_url),
            "error": request.query_params.get("error"),
        },
    )


@router.post(
    "/settings/reprints/confirm",
    response_class=HTMLResponse,
    name="reprint_maintenance_confirm",
)
async def reprint_maintenance_confirm(request: Request):
    form = await request.form()
    operation = str(form.get("operation", ""))
    try:
        plan = preview(
            request.app.state.database, _settings(request).data_path, operation
        )
    except ReprintJobError as error:
        return RedirectResponse(
            "/settings/reprints?" + urlencode({"error": str(error)}), 303
        )
    return templates.TemplateResponse(
        request=request,
        name="reprint_maintenance_confirm.html",
        context={"plan": plan},
    )


@router.post(
    "/settings/reprints/start",
    response_class=RedirectResponse,
    name="reprint_maintenance_start",
)
async def reprint_maintenance_start(request: Request):
    if not _settings(request).base_url:
        raise HTTPException(409, "Configure the public base URL first.")
    form = await request.form()
    try:
        job_id = create_job(
            request.app.state.database,
            _settings(request).data_path,
            str(form.get("operation", "")),
        )
    except ReprintJobError as error:
        return RedirectResponse(
            "/settings/reprints?" + urlencode({"error": str(error)}), 303
        )
    detail = job_detail(request.app.state.database, job_id)
    if detail and detail["status"] == "queued":
        _start(request, job_id)
    return RedirectResponse(f"/settings/reprints/jobs/{job_id}", 303)


@router.get(
    "/settings/reprints/jobs/{job_id}",
    response_class=HTMLResponse,
    name="reprint_maintenance_job",
)
def reprint_maintenance_job(request: Request, job_id: int):
    job = job_detail(request.app.state.database, job_id)
    if not job:
        raise HTTPException(404, "Reprint maintenance job not found.")
    return templates.TemplateResponse(
        request=request, name="reprint_maintenance_job.html", context={"job": job}
    )


@router.post(
    "/settings/reprints/jobs/{job_id}/cancel",
    response_class=RedirectResponse,
    name="reprint_maintenance_cancel",
)
def reprint_maintenance_cancel(request: Request, job_id: int):
    try:
        cancel_job(request.app.state.database, job_id)
    except ReprintJobError as error:
        raise HTTPException(409, str(error)) from error
    return RedirectResponse(f"/settings/reprints/jobs/{job_id}", 303)


@router.post(
    "/settings/reprints/jobs/{job_id}/resume",
    response_class=RedirectResponse,
    name="reprint_maintenance_resume",
)
def reprint_maintenance_resume(request: Request, job_id: int):
    try:
        resume_job(request.app.state.database, job_id)
    except ReprintJobError as error:
        raise HTTPException(409, str(error)) from error
    _start(request, job_id)
    return RedirectResponse(f"/settings/reprints/jobs/{job_id}", 303)
