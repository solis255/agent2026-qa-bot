"""Request-local policy and a final JSON presentation safety pass."""
import json

from .logging import audit
from .policy import PrivacyPolicy, current_policy
from .redactor import Redactor


class PrivacyMiddleware:
    def __init__(self, app, policy: PrivacyPolicy):
        self.app = app
        self.policy = policy

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = current_policy.set(self.policy)
        start = None
        chunks = []
        sent = False

        async def safe_send(message):
            nonlocal start, sent
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                if message["status"] not in {204, 304} and scope.get("method") != "HEAD" and b"application/json" in headers.get(b"content-type", b""):
                    start = message
                    return
            if start is not None and message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body", False): return
                result = Redactor(self.policy).redact(json.loads(b"".join(chunks)))
                audit(result, "presentation")
                content = json.dumps(result.value, ensure_ascii=False, separators=(",", ":")).encode()
                headers = [(k, v) for k, v in start["headers"] if k != b"content-length"]
                start["headers"] = headers + [(b"content-length", str(len(content)).encode())]
                await send(start)
                sent = True
                await send({"type": "http.response.body", "body": content})
                return
            await send(message)
            if message["type"] == "http.response.start": sent = True

        try:
            await self.app(scope, receive, safe_send)
        except Exception as exc:
            if sent:
                raise
            import logging
            from netpilot.observability import get_request_id, log_event
            log_event(logging.getLogger("netpilot.privacy"), "request_failed", error_type=type(exc).__name__)
            content = json.dumps({"detail": "请求处理失败，请稍后重试。", "request_id": get_request_id()}, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 500,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(content)).encode())]})
            await send({"type": "http.response.body", "body": content})
        finally:
            current_policy.reset(token)
