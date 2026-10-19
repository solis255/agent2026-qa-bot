import pytest
from netpilot.privacy import redact_headers, redact_text, sanitize_url


@pytest.mark.parametrize("key", ["token", "access_token", "refresh_token", "api_key", "key", "secret", "password", "passwd", "auth", "authorization", "session", "sessionid", "sid", "%74oken"])
def test_url_credentials_query_and_fragment(key):
    value = f"https://user:pass@example.com/path?{key}=opaque&lang=zh#access_token=hidden"
    assert sanitize_url(value) == "https://example.com/path?lang=zh"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,evil", "file:///tmp/private", "https://[", "https://example.com:bad", "//example.com"])
def test_only_absolute_web_links(url):
    assert sanitize_url(url) == "[REDACTED]"


def test_headers_and_markdown_citation_are_clickable_without_secret():
    result = redact_headers({"Authorization": "Bearer opaque", "Cookie": "sid=opaque", "Proxy-Authorization": "Basic opaque", "X-API-Key": "opaque", "Content-Type": "application/json"})
    assert "opaque" not in str(result.value)
    assert result.value["Content-Type"] == "application/json"
    assert redact_text("[参考](https://example.com/?token=opaque&lang=zh)").value == "[参考](https://example.com/?lang=zh)"
