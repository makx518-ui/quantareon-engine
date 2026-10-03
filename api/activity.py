"""Untrusted browser telemetry: bounded payload, fixed actions, no user text."""
import re
import time
from fastapi import APIRouter, Request
from starlette.responses import Response
from engine.audit import event

router = APIRouter()
_limits = {}


@router.post("/api/activity")
async def activity(request: Request):
    # Stream a bounded body; Content-Length cannot be trusted.
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > 2048:
            return Response(status_code=413)
        chunks.extend(chunk)
    import json
    try:
        data = json.loads(chunks)
        visitor = data.get("visitor", "")
        page = data.get("page", "")
        action = data.get("action", "")
        if not isinstance(visitor, str) or not re.fullmatch(r"[a-f0-9]{32}", visitor):
            raise ValueError()
        if not isinstance(page, str) or not re.fullmatch(r"/[a-z0-9_-]{0,50}(?:\.html)?", page):
            raise ValueError()
        if action not in {"page_open", "page_leave", "button_click", "link_click", "form_submit", "browser_error", "promise_rejection"}:
            raise ValueError()
        control = data.get("control", 0)
        if type(control) is not int or not 0 <= control <= 10000:
            raise ValueError()
        name = data.get("name", "")
        if name not in {"", "birth_details_send", "location_confirm", "microphone_toggle", "payment_start", "report_open", "birth_details_restart", "report_download", "payment_cancel"}:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        return Response(status_code=400)
    minute = int(time.time() / 60)
    if len(_limits) > 1000:
        _limits.clear()
    previous, count = _limits.get(visitor, (minute, 0))
    count = count + 1 if previous == minute else 1
    _limits[visitor] = (minute, count)
    if count > 120:
        return Response(status_code=429)
    # Mark browser claims separately; they never prove a server-side operation.
    event("browser." + action, visitor_id=visitor, action=page + ":" + (name or "control_" + str(control)))
    return Response(status_code=204)
