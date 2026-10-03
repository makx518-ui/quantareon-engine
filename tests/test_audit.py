import asyncio
import contextlib
import io
import json
import unittest
from engine.audit import AuditMiddleware, audit_thread, context, event, model_call


class AuditTests(unittest.TestCase):
    def test_secrets_are_not_recorded(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            event("test", action="safe", password="SECRET", email="PRIVATE", body="SECRET")
        self.assertNotIn("SECRET", stream.getvalue())
        self.assertNotIn("PRIVATE", stream.getvalue())

    def test_thread_inherits_context_and_parent_is_restored(self):
        seen = []
        token = context.set({"request_id": "parent"})
        try:
            worker = audit_thread(target=lambda: seen.append(context.get()["request_id"]))
            worker.start(); worker.join()
            self.assertEqual(seen, ["parent"])
        finally:
            context.reset(token)
        self.assertEqual(context.get(), {})

    def test_streaming_and_rejection_reason_preserved(self):
        messages = []
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 429, "headers": []})
            await send({"type": "http.response.body", "body": b'{"reason":"busy"}', "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        async def send(message):
            messages.append(message)
        async def receive():
            return {"type": "http.request", "body": b""}
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            asyncio.run(AuditMiddleware(app)({"type": "http", "method": "POST", "headers": [], "query_string": b"key=SECRET"}, receive, send))
        self.assertEqual(messages[1]["body"], b'{"reason":"busy"}')
        self.assertTrue(messages[1]["more_body"])
        self.assertIn('"reason": "busy"', stream.getvalue())
        self.assertNotIn("SECRET", stream.getvalue())
        self.assertEqual(context.get(), {})

    def test_concurrent_requests_keep_distinct_ids(self):
        seen = []
        async def app(scope, receive, send):
            before = context.get()["request_id"]
            await asyncio.sleep(0)
            seen.append((before, context.get()["request_id"]))
        async def nothing(*args):
            pass
        async def run():
            await asyncio.gather(*(AuditMiddleware(app)({"type": "http", "headers": []}, nothing, nothing) for _ in range(2)))
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(run())
        self.assertEqual(len({x[0] for x in seen}), 2)
        self.assertTrue(all(a == b for a, b in seen))

    def test_websocket_payload_is_untouched(self):
        sent = []
        async def app(scope, receive, send):
            await send({"type": "websocket.send", "text": "PRIVATE"})
            await send({"type": "websocket.close", "code": 1000})
        async def send(message):
            sent.append(message)
        async def receive():
            return {}
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            asyncio.run(AuditMiddleware(app)({"type": "websocket", "headers": []}, receive, send))
        self.assertEqual(sent[0]["text"], "PRIVATE")
        self.assertNotIn("PRIVATE", stream.getvalue())

    def test_model_failure_logged_without_error_text_and_reraised(self):
        @model_call("test", "model")
        def fail():
            raise RuntimeError("SECRET API KEY")
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(RuntimeError):
            fail()
        self.assertIn("model.failed", stream.getvalue())
        self.assertNotIn("SECRET", stream.getvalue())

    def test_activity_rejects_personal_text_and_oversize(self):
        from api.activity import activity
        class Request:
            def __init__(self, body): self.body = body
            async def stream(self): yield self.body
        bad = json.dumps({"visitor": "a" * 32, "page": "/", "action": "my private text"}).encode()
        self.assertEqual(asyncio.run(activity(Request(bad))).status_code, 400)
        self.assertEqual(asyncio.run(activity(Request(b"a" * 2049))).status_code, 413)


if __name__ == "__main__":
    unittest.main()
