"""Structured operational events; never log request bodies or credentials."""
import contextvars
import functools
import json
import time
import uuid
from datetime import datetime, timezone

context = contextvars.ContextVar("audit_context", default={})


def audit_thread(*, target, args=(), kwargs=None, **options):
    import threading
    copied = contextvars.copy_context()
    return threading.Thread(target=copied.run, args=(target, *args), kwargs=kwargs or {}, **options)
FIELDS = frozenset(("request_id", "visitor_id", "job_id", "action", "method",
                    "status", "duration_ms", "reason", "error_type", "provider",
                    "model", "input_tokens", "output_tokens", "cost_usd", "finish", "mode", "lang", "stage"))


def event(name, **fields):
    # Logging failure must never break a calculation or response.
    try:
        data = {"event": name, "time": datetime.now(timezone.utc).isoformat()}
        data.update({k: v for k, v in {**context.get(), **fields}.items() if k in FIELDS})
        print("AUDIT " + json.dumps(data, ensure_ascii=False), flush=True)
    except Exception:
        pass


def model_call(provider, model):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            start = time.monotonic()
            name = model(*args, **kwargs) if callable(model) else model
            event("model.started", provider=provider, model=name)
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                event("model.failed", provider=provider, model=name,
                      error_type=type(exc).__name__, reason="provider_call_failed",
                      duration_ms=round((time.monotonic() - start) * 1000))
                raise
            event("model.completed", provider=provider, model=name,
                  duration_ms=round((time.monotonic() - start) * 1000))
            return result
        return wrapped
    return decorate


def tracked_job(action):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(job_id, *args, **kwargs):
            token = context.set({**context.get(), "job_id": job_id})
            event("job.started", action=action)
            try:
                return fn(job_id, *args, **kwargs)
            finally:
                state = fn.__globals__.get("ЗАДАЧИ", {}).get(job_id, {})
                failed = bool(state.get("oshibka"))
                event("job.finished", action=action,
                      reason="generation_failed" if failed else "completed" if state.get("gotovo") else "pending")
                context.reset(token)
        return wrapped
    return decorate


class AuditMiddleware:
    """Pure ASGI: preserve streaming, websocket messages and application errors."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        # Anonymous browser ID, never an IP address or authenticated identity.
        from http.cookies import SimpleCookie
        cookie = SimpleCookie()
        try:
            cookie.load(dict(scope.get("headers", [])).get(b"cookie", b"").decode("latin1"))
            visitor = cookie["qa_visit"].value if "qa_visit" in cookie else ""
        except Exception:
            visitor = ""
        visitor = dict(scope.get("headers", [])).get(b"x-visit-id", b"").decode("latin1") or visitor
        if len(visitor) != 32 or any(c not in "0123456789abcdef" for c in visitor):
            visitor = uuid.uuid4().hex
        token = context.set({"request_id": request_id, "visitor_id": visitor})
        from urllib.parse import parse_qs
        query = parse_qs(scope.get("query_string", b"").decode("latin1"))
        job = query.get("nomer", [""])[0]
        if 12 <= len(job) <= 32 and all(c in "0123456789abcdef" for c in job):
            context.set({**context.get(), "job_id": job})
        scope.setdefault("state", {})["audit_context"] = dict(context.get())
        start = time.monotonic()
        status = None
        reason = None
        def action():
            route = scope.get("route")
            return getattr(route, "path", None) or "unmatched_route"
        event("request.started", method=scope.get("method", "WEBSOCKET"))

        async def audited_send(message):
            nonlocal status, reason
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()),
                    (b"set-cookie", ("qa_visit=" + visitor + "; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax").encode())]}
            elif message["type"] == "websocket.close":
                status = message.get("code", 1000)
            elif message["type"] == "http.response.body" and status and status >= 400:
                body = message.get("body", b"")
                if len(body) <= 4096:
                    try:
                        value = json.loads(body).get("reason")
                        if value in {"bad_request", "bad_coords", "bad_time", "locked", "busy"}:
                            reason = value
                    except Exception:
                        pass
            await send(message)
        try:
            await self.app(scope, receive, audited_send)
        except BaseException as exc:
            event("request.failed", action=action(), error_type=type(exc).__name__, reason="application_exception")
            raise
        finally:
            event("request.finished", action=action(), status=status,
                  reason=reason or ({401: "authentication_required", 403: "access_denied", 404: "not_found", 429: "rate_limit", 503: "unavailable"}.get(status) or ("http_error" if status and 400 <= status < 600 else "completed")),
                  duration_ms=round((time.monotonic() - start) * 1000))
            context.reset(token)
