"""Read-only provider HTTP guard/capture, including curl_cffi native sockets."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from unittest.mock import patch

SOURCE_HOSTS = frozenset({"query1.finance.yahoo.com", "query2.finance.yahoo.com", "finance.yahoo.com",
    "fc.yahoo.com", "gamma-api.polymarket.com", "api.stlouisfed.org"})
SECRET_KEYS = {"api_key", "apikey", "key", "token", "crumb", "sessionid", "csrf", "csrftoken"}
HTTP_EVIDENCE_ID = ContextVar("live_source_evidence_id", default=None)


class SourceNetworkError(PermissionError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def safe_url(url, params=None):
    parts = urlsplit(str(url))
    query = list(parse_qsl(parts.query, keep_blank_values=True))
    if isinstance(params, dict):
        query += list(params.items())
    elif isinstance(params, (list, tuple)):
        query += list(params)
    query = [(k, "[REDACTED]" if str(k).lower() in SECRET_KEYS else v) for k, v in query]
    return urlunsplit((parts.scheme, parts.netloc.split("@")[-1], parts.path, urlencode(query, doseq=True), ""))


def check_request(method, url):
    parts = urlsplit(str(url))
    if parts.scheme != "https" or parts.hostname not in SOURCE_HOSTS or parts.port not in (None, 443) or parts.username or parts.password:
        raise SourceNetworkError("Source destination is not an approved public HTTPS provider")
    method = str(method).upper()
    host, path = parts.hostname, parts.path
    allowed = False
    if host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        allowed = method in ("GET", "HEAD") and (
            path.startswith("/v8/finance/chart/") or path in ("/v1/test/getcrumb", "/v1/finance/search", "", "/")
        )
    elif host == "finance.yahoo.com":
        query = dict(parse_qsl(parts.query))
        allowed = method == "POST" and path == "/xhr/ncp" and query.get("serviceKey") == "ncp_fin" and query.get("queryRef") in ("latestNews", "newsAll", "pressRelease")
    elif host == "fc.yahoo.com":
        allowed = method in ("GET", "HEAD") and path in ("", "/")
    elif host == "gamma-api.polymarket.com":
        allowed = method == "GET" and path == "/public-search"
    elif host == "api.stlouisfed.org":
        allowed = method == "GET" and path in ("/fred/series", "/fred/series/observations")
    if not allowed:
        raise SourceNetworkError("Source method/path is outside the inspected native read-only routes")


def _time_fields(body):
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        return []
    result = []
    names = {"pubDate", "providerPublishTime", "timestamp", "regularMarketTime", "exchangeTimezoneName", "endDate"}
    def visit(value, path="", depth=0):
        if depth > 12 or len(result) >= 80:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                next_path = path + "/" + key
                if key in names and child is not None:
                    if isinstance(child, list):
                        result.append({"pointer": next_path, "first": child[0] if child else None,
                            "last": child[-1] if child else None, "count": len(child),
                            "precision": "provider_declared"})
                    elif isinstance(child, (str, int, float)):
                        result.append({"pointer": next_path, "value": child, "precision": "provider_declared"})
                else:
                    visit(child, next_path, depth + 1)
        elif isinstance(value, list):
            for i, child in enumerate(value[:100]):
                visit(child, path + "/" + str(i), depth + 1)
    visit(data)
    return result


class HttpCapture:
    def __init__(self, trace, cfg):
        self.trace = trace
        self.timeout = min(float(cfg.get("source_http_timeout", 15)), 30)
        self.max_bytes = min(int(cfg.get("source_max_response_bytes", 4_000_000)), 8_000_000)
        self.max_requests = int(cfg.get("source_max_http_requests", 160))
        if self.timeout <= 0 or self.max_bytes <= 0 or self.max_requests <= 0:
            raise ValueError("Positive bounded HTTP source limits required")
        self.records = []
        self._count = 0
        self._lock = threading.Lock()

    def _emit(self, kind, record):
        if self.trace is not None:
            self.trace.emit(kind, record)

    def request(self, transport, original, session, method, url, args, kwargs):
        if args or kwargs.get("stream") or kwargs.get("content_callback"):
            raise SourceNetworkError("Unsupported streaming/custom source transport")
        kwargs = dict(kwargs)
        if kwargs.get("verify") is False:
            raise SourceNetworkError("TLS verification cannot be disabled")
        kwargs["verify"] = True
        # Both native transports must validate every redirect before following.
        kwargs["allow_redirects"] = False
        timeout = kwargs.get("timeout")
        if isinstance(timeout, (int, float)):
            kwargs["timeout"] = min(float(timeout), self.timeout)
        elif isinstance(timeout, tuple):
            kwargs["timeout"] = tuple(min(float(v or self.timeout), self.timeout) for v in timeout)
        else:
            kwargs["timeout"] = self.timeout
        for redirect in range(5):
            check_request(method, url)
            with self._lock:
                self._count += 1
                if self._count > self.max_requests:
                    raise SourceNetworkError("Source HTTP request count exceeded")
            identity = "source-http:" + uuid.uuid4().hex
            record = {"http_id": identity, "transport": transport, "method": str(method).upper(),
                "evidence_id": HTTP_EVIDENCE_ID.get(),
                "url": safe_url(url, kwargs.get("params")), "requested_at": utc(),
                "timeout_seconds": kwargs["timeout"], "redirect_index": redirect}
            self._emit("source.http.start", record)
            started = time.monotonic()
            try:
                if transport == "requests":
                    kwargs["stream"] = True
                    response = original(session, method, url, **kwargs)
                    chunks, total = [], 0
                    for chunk in response.iter_content(64 * 1024):
                        total += len(chunk)
                        if total > self.max_bytes:
                            response.close()
                            raise SourceNetworkError("Source HTTP response size exceeded")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    response._content = body
                    response._content_consumed = True
                else:
                    chunks, total, overflow = [], [0], [False]
                    def consume(chunk):
                        total[0] += len(chunk)
                        if total[0] > self.max_bytes:
                            overflow[0] = True
                            return 0
                        chunks.append(bytes(chunk))
                        return len(chunk)
                    kwargs["content_callback"] = consume
                    try:
                        response = original(session, method, url, **kwargs)
                    except Exception as exc:
                        if overflow[0]:
                            raise SourceNetworkError("Source HTTP response size exceeded") from exc
                        raise
                    finally:
                        kwargs.pop("content_callback", None)
                    if overflow[0]:
                        raise SourceNetworkError("Source HTTP response size exceeded")
                    body = b"".join(chunks)
                    response.content = body
                record.update(status=int(response.status_code), retrieved_at=utc(),
                    elapsed_seconds=round(time.monotonic() - started, 6),
                    response_bytes=len(body), response_sha256=hashlib.sha256(body).hexdigest(),
                    final_url=safe_url(response.url or url),
                    source_time_fields=_time_fields(body), cache_status="network_transport")
                with self._lock:
                    self.records.append(dict(record))
                self._emit("source.http.end", record)
                if response.status_code not in (301, 302, 303, 307, 308):
                    return response
                location = response.headers.get("Location") or response.headers.get("location")
                if not location:
                    return response
                url = urljoin(str(url), location)
                if response.status_code == 303 or (response.status_code in (301, 302) and str(method).upper() == "POST"):
                    method = "GET"
                    for key in ("data", "json", "content"):
                        kwargs.pop(key, None)
                kwargs.pop("params", None)
                kwargs.pop("stream", None)
                # The next loop iteration checks the new host/path before IO.
            except Exception as exc:
                record.update(retrieved_at=utc(), elapsed_seconds=round(time.monotonic() - started, 6),
                              error_type=type(exc).__name__, status=record.get("status"), source_time_fields=[])
                with self._lock:
                    self.records.append(dict(record))
                self._emit("source.http.error", record)  # Never log exception URLs/keys/cookies.
                raise
        raise SourceNetworkError("Source redirect limit exceeded")


@contextmanager
def data_http(trace=None, cfg=None):
    import requests
    from curl_cffi import requests as curl_requests
    capture = HttpCapture(trace, cfg or {})
    requests_original = requests.sessions.Session.request
    curl_original = curl_requests.Session.request
    def guarded_requests(session, method, url, *args, **kwargs):
        return capture.request("requests", requests_original, session, method, url, args, kwargs)
    def guarded_curl(session, method, url, *args, **kwargs):
        return capture.request("curl_cffi", curl_original, session, method, url, args, kwargs)
    with patch.object(requests.sessions.Session, "request", guarded_requests), \
         patch.object(curl_requests.Session, "request", guarded_curl):
        yield capture
