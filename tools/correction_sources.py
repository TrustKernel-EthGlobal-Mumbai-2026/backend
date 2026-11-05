"""Opt-in data-only native capture; exact, offline common-evidence replay.

No models, budget, account credentials or verification schemas are involved.
Default CLI is a plan, not a fetch. Capture runs only in a fresh bounded child.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live_experiment import source_http
from live_experiment.sources import classify, content_digest, current_source_date, sanitize_text

VERSION = "correction-source-capture-0.1"
PIN = "c4544913a14ed3df5f1ed7b9e8483270ce20682a"
YAHOO_HOSTS = frozenset({"query1.finance.yahoo.com", "query2.finance.yahoo.com", "finance.yahoo.com", "fc.yahoo.com"})
LIMITS = dict(http_timeout_seconds=8, max_http_requests=24, max_response_bytes=2_000_000,
              max_retained_bytes=16_000_000, max_native_text_bytes=64_000,
              max_model_text_bytes=16_000, wall_seconds=90)
INDICATORS = ("rsi", "macd", "close_200_sma")


class SourceBundleError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def _redact_text(text):
    text = sanitize_text(text)
    return re.sub(r'''(?i)(\b(?:access[_-]?token|refresh[_-]?token|private[_-]?key)\b["']?\s*[:=]\s*)["']?[^\s"'&,}]+''',
                  r'\1[REDACTED]', text)


def make_plan(as_of, stock_days=60):
    """Seven exact queries. Native injected arguments are included explicitly."""
    day = date.fromisoformat(as_of)
    if day.isoformat() != as_of or type(stock_days) is not int or not 30 <= stock_days <= 90:
        raise SourceBundleError("Expected ISO date and a 30..90-day stock window")
    end = day.isoformat()
    base = dict(symbol="ETH-USD", trade_date=end)
    calls = [dict(tool="get_stock_data", args=dict(base, start_date=(day - timedelta(days=stock_days)).isoformat(), end_date=end))]
    calls += [dict(tool="get_indicators", args=dict(base, indicator=name, curr_date=end, look_back_days=10)) for name in INDICATORS]
    calls += [dict(tool="get_verified_market_snapshot", args=dict(base, curr_date=end, look_back_days=10)),
              dict(tool="get_global_news", args=dict(curr_date=end, look_back_days=7, limit=5, trade_date=end)),
              dict(tool="get_news", args=dict(ticker="ETH-USD", start_date=(day - timedelta(days=7)).isoformat(), end_date=end, trade_date=end))]
    return dict(format_version=VERSION, as_of=end, as_of_timezone="Asia/Calcutta", stock_days=stock_days,
                symbol="ETH-USD", calls=calls, limits=copy.deepcopy(LIMITS),
                required_model_order=["get_stock_data", "get_indicators", "get_verified_market_snapshot", "optional_news"],
                replay_matching="EXACT_FULL_NATIVE_ARGUMENTS_ONLY", continuously_live=False)


def request_key(tool, args):
    return sha(canonical([tool, args]))


def _clean(value):
    """Named-field redaction only, never environment value enumeration."""
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if re.search(r"(?i)api.?key|authorization|password|secret|cookie|crumb|token|sessionid|csrf", key)
                      else _clean(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return _redact_text(value) if isinstance(value, str) else value


class Artifacts:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.total = 0

    def write(self, relative, body):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise SourceBundleError("Artifact path escaped capture directory")
        if self.total + len(body) > LIMITS["max_retained_bytes"]:
            raise SourceBundleError("Retained capture byte bound exceeded")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        self.total += len(body)
        return dict(path=path.relative_to(self.root).as_posix(), sha256=sha(body), bytes=len(body))


def _body_metadata(raw):
    try:
        value = json.loads(raw)
        results = value.get("chart", {}).get("result") or []
        meta = results[0].get("meta", {}) if results else {}
        return {key: meta[key] for key in ("symbol", "currency", "exchangeTimezoneName", "timezone", "gmtoffset", "dataGranularity", "regularMarketTime") if key in meta}
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        return {}


def retaining_http_class(artifacts):
    """Reuse the reviewed guard; tap every redirect/body without altering data.

    Only privacy-filtered provider bodies are retained. Handshake/crumb/cookie
    responses have hashes/transport metadata only. No headers are persisted.
    """
    class RetainingHttp(source_http.HttpCapture):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.local = threading.local()
            self.retained = {}

        def _emit(self, kind, record):
            if kind == "source.http.start":
                self.local.identity = record["http_id"]
            elif kind == "source.http.end":
                record.update(self.retained.get(record["http_id"], {"body_retention": "NOT_COMPLETED"}))
            super()._emit(kind, record)

        def _save(self, response, url, raw):
            from urllib.parse import urlsplit
            identity = self.local.identity
            if urlsplit(str(url)).hostname == "fc.yahoo.com" or "/getcrumb" in str(url):
                self.retained[identity] = dict(body_retention="HANDSHAKE_SECRET_BODY_OMITTED")
                return
            try:
                text = raw.decode("utf-8")
            except UnicodeError:
                self.retained[identity] = dict(body_retention="BINARY_BODY_NOT_RETAINED")
                return
            filtered = _redact_text(text)
            try:
                parsed = json.loads(text)
                cleaned = _clean(parsed)
                if cleaned != parsed:
                    filtered = canonical(cleaned)
            except (ValueError, TypeError):
                pass
            retained = filtered.encode("utf-8")
            descriptor = artifacts.write("http/" + identity.split(":")[-1] + ".body", retained)
            self.retained[identity] = dict(body_retention="REDACTED" if retained != raw else "EXACT_PROVIDER_BYTES",
                body_artifact=descriptor, provider_metadata=_clean(_body_metadata(raw)))

        def request(self, transport, original, session, method, url, args, kwargs):
            def tap(active_session, active_method, active_url, **active_kwargs):
                if transport == "requests":
                    response = original(active_session, active_method, active_url, **active_kwargs)
                    original_chunks = response.iter_content
                    def chunks(size):
                        parts, count = [], 0
                        for block in original_chunks(size):
                            count += len(block)
                            if count <= self.max_bytes:
                                parts.append(block)
                            yield block
                        self._save(response, active_url, b"".join(parts))
                    response.iter_content = chunks
                    return response
                callback, parts = active_kwargs["content_callback"], []
                def consume(block):
                    used = callback(block)
                    if used == len(block):
                        parts.append(bytes(block))
                    return used
                active_kwargs["content_callback"] = consume
                response = original(active_session, active_method, active_url, **active_kwargs)
                self._save(response, active_url, b"".join(parts))
                return response
            return super().request(transport, tap, session, method, url, args, kwargs)
    return RetainingHttp


class CaptureTrace:
    def __init__(self):
        self.events = []

    def emit(self, kind, payload):
        # Do not duplicate full native tool text into diagnostic/provenance logs.
        payload = {key: item for key, item in payload.items() if key not in ("content", "cache_files")}
        self.events.append(dict(kind=kind, payload=_clean(copy.deepcopy(payload))))


def _coverage(tool, arguments, text):
    info = dict(requested=copy.deepcopy(arguments), precision="NATIVE_FORMATTED_STRING",
                timezone="UNKNOWN_IN_NATIVE_STRING; see provider HTTP metadata",
                source_authority="NOT_ESTABLISHED", completeness="UNKNOWN")
    if tool == "get_stock_data":
        content = "\n".join(row for row in text.splitlines() if not row.startswith("#") and row.strip())
        rows = list(csv.DictReader(io.StringIO(content)))
        dates = [str(row.get("Date", ""))[:10] for row in rows if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("Date", ""))[:10])]
        start, end = date.fromisoformat(arguments["start_date"]), date.fromisoformat(arguments["end_date"])
        expected = {(start + timedelta(days=i)).isoformat() for i in range((end-start).days + 1)}
        info.update(bar_interval="1d native history default", observed_rows=len(rows),
                    observed_first=min(dates, default=None), observed_last=max(dates, default=None),
                    missing_requested_dates=sorted(expected-set(dates)),
                    current_daily_bar_finality="UNKNOWN; current bar may be partial",
                    formatting="Native price_text: six significant digits, at least two decimals; timezone stripped natively",
                    usable_shape=bool(dates) and {"Open", "High", "Low", "Close", "Volume"} <= set(rows[0] if rows else {}))
    elif tool == "get_indicators":
        values = re.findall(r"(?m)^(\d{4}-\d{2}-\d{2}): (.*)$", text)
        valid = []
        for day, value in values:
            try:
                if math.isfinite(float(value)):
                    valid.append(day)
            except ValueError:
                pass
        info.update(observed_value_dates=valid, missing_or_unavailable_dates=[day for day, _ in values if day not in valid],
                    usable_shape=bool(valid), calculation="Native stockstats over fresh native 5y history, as-of filtered",
                    native_gap_fill="Native load_ohlcv default fill_gaps=True (forward/back fill); no correction by this adapter")
    elif tool == "get_verified_market_snapshot":
        latest = re.search(r"Latest trading row used: (\d{4}-\d{2}-\d{2})", text)
        close = re.search(r"(?m)^\| Close \| ([^|]+) \|", text)
        try:
            numeric = close is not None and math.isfinite(float(close[1].strip()))
        except ValueError:
            numeric = False
        info.update(observed_last=latest[1] if latest else None, usable_shape=bool(latest and numeric),
                    native_gap_fill="fill_gaps=False", current_daily_bar_finality="UNKNOWN",
                    snapshot_label="Native function name; not independent source authority/finality certification")
    else:
        info.update(usable_shape="### " in text and "News" in text,
                    news_coverage="Native Yahoo recent/sample feed; not exhaustive; publication times only when provider supplied")
    return info


def _status(tool, text, coverage):
    declared = classify(tool, text)
    if text.startswith("No global news found"):
        declared = "NO_DATA"
    if declared == "AVAILABLE" and not coverage["usable_shape"]:
        if tool == "get_indicators" and coverage.get("missing_or_unavailable_dates"):
            return "NO_DATA", declared
        return "UNAVAILABLE_FORMAT", declared
    return declared, declared


def _bar_coverage(raw, as_of):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    date.fromisoformat(as_of)
    dated, invalid_dates = [], 0
    for row in rows:
        day = str(row.get("Date", row.get("Datetime", "")))[:10]
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or date.fromisoformat(day).isoformat() != day:
                raise ValueError()
        except ValueError:
            invalid_dates += 1
            continue
        dated.append((day, row))
    dates = [day for day, _ in dated]
    in_range = [(day, row) for day, row in dated if day <= as_of]
    valid_close_dates = set()
    for day, row in in_range:
        try:
            if math.isfinite(float(row.get("Close", ""))):
                valid_close_dates.add(day)
        except (ValueError, TypeError):
            pass
    missing = []
    gap_enumeration_truncated = False
    if dates:
        first, last = date.fromisoformat(min(dates)), date.fromisoformat(min(max(dates), as_of))
        count, known_dates = max(0, (last-first).days+1), set(dates)
        gap_enumeration_truncated = count > 6*366
        missing = [(first + timedelta(days=i)).isoformat() for i in range(min(count, 6*366))
                   if (first + timedelta(days=i)).isoformat() not in known_dates]
    return dict(rows=len(rows), first=min(dates, default=None), last=max(dates, default=None),
                as_of=as_of, rows_on_or_before_asof=len(in_range), distinct_dates_on_or_before_asof=len({day for day, _ in in_range}),
                finite_close_rows_on_or_before_asof=len(valid_close_dates),
                at_least_200_real_close_rows=len(valid_close_dates) >= 200, missing_daily_dates=missing,
                invalid_date_rows=invalid_dates, duplicate_valid_date_rows=len(dates)-len(set(dates)),
                future_dated_rows=sum(day > as_of for day, _ in dated),
                coverage_status="UNKNOWN" if invalid_dates or not dates else "OBSERVED_DATED_ROWS",
                completeness="UNKNOWN",
                gap_enumeration_truncated=gap_enumeration_truncated,
                precision="Native saved OHLCV CSV; no rounding/conversion by capture adapter",
                timezone="Retained Date strings; provider timezone remains in HTTP metadata",
                current_daily_bar_finality="UNKNOWN")


def _record_bundle(output, plan, invoke, *, trace, schemas, upstream_binding, artifacts, clock=utc, finish=None):
    """Internal writer seam; offline tests inject authored HTTP/tool functions."""
    if plan != make_plan(plan["as_of"], plan["stock_days"]):
        raise SourceBundleError("Capture plan differs from bounded candidate")
    started, entries = clock(), []
    for call in plan["calls"]:
        name, arguments = call["tool"], call["args"]
        requested, event_start = clock(), len(trace.events)
        error_type = None
        try:
            text = invoke(name, copy.deepcopy(arguments))
            if not isinstance(text, str):
                raise SourceBundleError("Native tool did not return a string")
        except Exception as exc:
            text, error_type = None, type(exc).__name__
        captured = clock()
        provenance = trace.events[event_start:]
        http = [event["payload"] for event in provenance if event["kind"] in ("source.http.end", "source.http.error")]
        descriptor, coverage, source_status, declared = None, None, "ERROR", None
        if text is not None:
            # Secrets cannot be redacted inside native evidence without changing
            # its bytes. Refuse retention/exposure rather than silently edit it.
            if _redact_text(text) != text:
                source_status = "SECRET_BEARING_NATIVE_OUTPUT_REFUSED"
            elif len(text.encode()) > LIMITS["max_native_text_bytes"]:
                source_status = "NATIVE_OUTPUT_TOO_LARGE"
            else:
                descriptor = artifacts.write("returns/" + request_key(name, arguments) + ".txt", text.encode("utf-8"))
                coverage = _coverage(name, arguments, text)
                source_status, declared = _status(name, text, coverage)
        serve_status = source_status
        if descriptor and descriptor["bytes"] > LIMITS["max_model_text_bytes"]:
            serve_status = "MODEL_OUTPUT_TOO_LARGE"
        entries.append(dict(entry_id="source-" + request_key(name, arguments), tool=name, args=arguments,
            request_key=request_key(name, arguments), provider="yfinance/Yahoo", requested_at=requested,
            captured_at=captured, as_of=plan["as_of"], as_of_timezone=plan["as_of_timezone"],
            source_status=source_status, declared_native_status=declared, status=serve_status,
            native_error_type=error_type, content=descriptor, coverage=coverage, http_records=http,
            provenance=provenance, text_origin="NATIVE_UNCHANGED" if descriptor else "NO_NATIVE_TEXT_RETAINED"))
    fresh_bars = finish() if finish else []
    bar_coverage = [dict(path=item["path"], coverage=_bar_coverage((Path(output)/item["path"]).read_bytes(), plan["as_of"])) for item in fresh_bars]
    manifest = dict(format_version=VERSION, capture_id="capture-" + uuid4().hex,
        captured_at_start=started, captured_at_end=clock(), as_of=plan["as_of"],
        as_of_timezone=plan["as_of_timezone"], mode="ONCE_CAPTURED_COMMON_REPLAY", continuously_live=False,
        plan=plan, plan_sha256=sha(canonical(plan)), schemas=schemas, schemas_sha256=sha(canonical(schemas)),
        entries=entries, upstream=upstream_binding, fresh_bar_artifacts=fresh_bars, fresh_bar_coverage=bar_coverage,
        indicator_history_ready=any(item["coverage"]["at_least_200_real_close_rows"] for item in bar_coverage),
        implementation_sha256=sha(Path(__file__).read_bytes()), model_calls=0,
        limitations=["Replay is the original capture, not a live refresh or continuous feed.",
                      "Native snapshot is not independent price truth or bar finality.",
                      "Unavailable news is not absence of news; native indicator gap filling is disclosed."])
    by_tool = {entry["tool"]: entry for entry in entries}
    manifest["core_ready"] = all(by_tool[name]["status"] == "AVAILABLE" for name in ("get_stock_data", "get_verified_market_snapshot"))
    manifest["status"] = "CAPTURED" if all(entry["status"] == "AVAILABLE" for entry in entries) else "CAPTURED_WITH_GAPS"
    manifest["retained_bytes_before_manifest"] = artifacts.total
    artifacts.write("manifest.json", (canonical(manifest) + "\n").encode())
    return dict(manifest_path=str(Path(output).resolve() / "manifest.json"),
                manifest_sha256=sha((Path(output) / "manifest.json").read_bytes()),
                status=manifest["status"], core_ready=manifest["core_ready"])


class ReplayBundle:
    def __init__(self, manifest_path, *, expected_sha256):
        self.path = Path(manifest_path).resolve()
        if self.path.stat().st_size > LIMITS["max_retained_bytes"]:
            raise SourceBundleError("Capture manifest is oversized")
        raw = self.path.read_bytes()
        if len(raw) > LIMITS["max_retained_bytes"] or sha(raw) != expected_sha256:
            raise SourceBundleError("Capture manifest byte binding mismatch")
        self._manifest = json.loads(raw)
        value = self._manifest
        if value["format_version"] != VERSION or value["implementation_sha256"] != sha(Path(__file__).read_bytes()):
            raise SourceBundleError("Capture version/implementation mismatch")
        if (value["plan"] != make_plan(value["as_of"], value["plan"]["stock_days"]) or
                value["as_of_timezone"] != value["plan"]["as_of_timezone"] or value["upstream"]["commit"] != PIN):
            raise SourceBundleError("Capture plan/upstream mismatch")
        if value["plan_sha256"] != sha(canonical(value["plan"])) or value["schemas_sha256"] != sha(canonical(value["schemas"])):
            raise SourceBundleError("Capture plan/schema byte binding mismatch")
        names = {call["tool"] for call in value["plan"]["calls"]}
        if set(value["schemas"]) != names or any(not isinstance(schema.get("description"), str) or not isinstance(schema.get("args_schema"), dict) for schema in value["schemas"].values()):
            raise SourceBundleError("Capture native schema catalog mismatch")
        self.manifest_sha256 = expected_sha256
        self._entries, self._texts = {}, {}
        planned = {request_key(call["tool"], call["args"]) for call in value["plan"]["calls"]}
        for entry in value["entries"]:
            key = request_key(entry["tool"], entry["args"])
            if key != entry["request_key"] or entry["entry_id"] != "source-" + key or key in self._entries or key not in planned:
                raise SourceBundleError("Capture query identity mismatch")
            self._entries[key] = copy.deepcopy(entry)
            self._texts[key] = self._read(entry["content"]).decode("utf-8") if entry["content"] else None
            text = self._texts[key]
            if (entry["as_of"], entry["as_of_timezone"]) != (value["as_of"], value["as_of_timezone"]):
                raise SourceBundleError("Entry analysis clock binding mismatch")
            if text is not None:
                if _redact_text(text) != text:
                    raise SourceBundleError("Secret-bearing native text cannot be replayed")
                coverage = _coverage(entry["tool"], entry["args"], text)
                status, declared = _status(entry["tool"], text, coverage)
                serve = "MODEL_OUTPUT_TOO_LARGE" if len(text.encode()) > LIMITS["max_model_text_bytes"] else status
                if (entry["coverage"], entry["source_status"], entry["declared_native_status"], entry["status"]) != (coverage, status, declared, serve):
                    raise SourceBundleError("Native status/coverage replay mismatch")
            elif entry["source_status"] not in ("ERROR", "SECRET_BEARING_NATIVE_OUTPUT_REFUSED", "NATIVE_OUTPUT_TOO_LARGE"):
                raise SourceBundleError("Missing native text cannot assert availability")
            for record in entry["http_records"]:
                if "body_artifact" in record:
                    self._read(record["body_artifact"])
        if set(self._entries) != planned:
            raise SourceBundleError("Capture plan is missing explicit entry outcomes")
        actual_bar_coverage = [dict(path=descriptor["path"], coverage=_bar_coverage(self._read(descriptor), value["as_of"])) for descriptor in value["fresh_bar_artifacts"]]
        if value["fresh_bar_coverage"] != actual_bar_coverage:
            raise SourceBundleError("Fresh bar coverage binding mismatch")
        if value["indicator_history_ready"] != any(item["coverage"]["at_least_200_real_close_rows"] for item in actual_bar_coverage):
            raise SourceBundleError("Indicator history readiness mismatch")

    def _read(self, descriptor):
        if (type(descriptor) is not dict or set(descriptor) != {"path", "sha256", "bytes"} or
                type(descriptor["path"]) is not str or Path(descriptor["path"]).is_absolute() or
                ".." in Path(descriptor["path"]).parts or type(descriptor["bytes"]) is not int or
                not 0 <= descriptor["bytes"] <= LIMITS["max_retained_bytes"]):
            raise SourceBundleError("Invalid capture artifact descriptor")
        path = (self.path.parent / descriptor["path"]).resolve()
        if not path.is_relative_to(self.path.parent) or not path.is_file() or path.stat().st_size != descriptor["bytes"]:
            raise SourceBundleError("Capture artifact path is unavailable or outside bundle")
        raw = path.read_bytes()
        if len(raw) != descriptor["bytes"] or sha(raw) != descriptor["sha256"]:
            raise SourceBundleError("Capture artifact byte binding mismatch")
        return raw

    @property
    def manifest(self):
        return copy.deepcopy(self._manifest)

    def offers(self):
        return [dict(tool=entry["tool"], args=copy.deepcopy(entry["args"]), status=entry["status"])
                for entry in self._entries.values()]

    def resolve(self, tool_name, arguments):
        try:
            key = request_key(tool_name, arguments)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            key = None
        entry = self._entries.get(key)
        if entry is None:
            return dict(text="DATA_UNAVAILABLE: this exact query was not captured; use the advertised captured arguments.",
                        status="UNAVAILABLE_ARGUMENTS", source_status="NOT_CAPTURED", source_refs=[], http_refs=[],
                        coverage=None, captured_at=None, as_of=self._manifest["as_of"],
                        as_of_timezone=self._manifest["as_of_timezone"], mode="CAPTURED_REPLAY",
                        continuously_live=False, text_origin="UNAVAILABLE_SENTINEL", match="NONE")
        text = self._texts[key]
        expose = text is not None and entry["status"] != "MODEL_OUTPUT_TOO_LARGE"
        return dict(text=text if expose else "DATA_UNAVAILABLE: captured query has no safely exposable bounded native return.",
                    status=entry["status"], source_status=entry["source_status"],
                    source_refs=[dict(capture_id=self.manifest["capture_id"], manifest_sha256=self.manifest_sha256,
                                      entry_id=entry["entry_id"], content=copy.deepcopy(entry["content"]))],
                    http_refs=copy.deepcopy(entry["http_records"]), coverage=copy.deepcopy(entry["coverage"]),
                    captured_at=entry["captured_at"], as_of=entry["as_of"], as_of_timezone=entry["as_of_timezone"],
                    mode="CAPTURED_REPLAY", continuously_live=False,
                    text_origin="NATIVE_UNCHANGED" if expose else "UNAVAILABLE_SENTINEL", match="EXACT")

    def bind_tools(self, originals, on_result):
        """Optional native dependency. Return strings to tools, metadata to host."""
        from langchain_core.tools import StructuredTool
        bound = []
        allowed = {call["tool"] for call in self.manifest["plan"]["calls"]}
        for original in originals:
            if original.name not in allowed:
                continue
            schema = self.manifest["schemas"].get(original.name)
            actual = dict(description=original.description, args_schema=original.args_schema.model_json_schema())
            if schema != actual:
                raise SourceBundleError("Native schema/description differs from captured dependency")
            def serve(_name=original.name, **kwargs):
                result = self.resolve(_name, kwargs)
                on_result(_name, copy.deepcopy(kwargs), copy.deepcopy(result))
                return result["text"]
            bound.append(StructuredTool.from_function(serve, name=original.name,
                         description=original.description, args_schema=original.args_schema))
        return tuple(bound)


def _data_only_socket_guard():
    """Fresh capture child only. No OpenAI destination or child processes."""
    allowed_ips, original = set(), socket.getaddrinfo
    def permitted(host):
        if isinstance(host, bytes):
            host = host.decode("ascii")
        return isinstance(host, str) and host.lower().rstrip(".") in YAHOO_HOSTS
    def resolve(host, port, *args, **kwargs):
        if not permitted(host) or str(port) not in ("443", "https"):
            raise PermissionError("Data-only source DNS destination denied")
        rows = original(host, port, *args, **kwargs)
        allowed_ips.update(row[4][0] for row in rows)
        return rows
    def audit(event, arguments):
        if event == "socket.getaddrinfo" and (not permitted(arguments[0]) or str(arguments[1]) not in ("443", "https")):
            raise PermissionError("Data-only source DNS denied")
        if event == "socket.connect":
            address = arguments[1]
            if not isinstance(address, tuple) or len(address) < 2 or address[1] != 443 or not (address[0] in allowed_ips or permitted(address[0])):
                raise PermissionError("Data-only source socket denied")
        if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn"):
            raise PermissionError("Data-only capture cannot launch a child process")
    socket.getaddrinfo = resolve
    sys.addaudithook(audit)


def _native_worker(output, upstream, plan):
    from tools.tradingagents_integration import checked_upstream, real_runtime
    from live_experiment.sources import live_tools
    upstream = checked_upstream(upstream)  # Git read finishes before socket/process guard.
    artifacts, trace = Artifacts(output), CaptureTrace()
    native_paths = ["tradingagents/agents/tools.py", "tradingagents/dataflows/vendors/yahoo/market.py",
                    "tradingagents/dataflows/vendors/yahoo/ohlcv.py", "tradingagents/dataflows/vendors/yahoo/snapshot.py",
                    "tradingagents/dataflows/vendors/yahoo/news.py", "tradingagents/dataflows/vendors/yahoo/common.py",
                    "tradingagents/dataflows/router.py", "tradingagents/dataflows/date_window.py"]
    upstream_binding = dict(commit=PIN, tag="v0.7.1", source_sha256={path: sha((upstream/path).read_bytes()) for path in native_paths},
                            guard_sha256={path: sha((ROOT/path).read_bytes()) for path in ("live_experiment/sources.py", "live_experiment/source_http.py")})
    with real_runtime(upstream) as runtime:
        from tradingagents.agents.analysts import market_analyst, news_analyst
        originals = {tool.name: tool for module in (market_analyst, news_analyst) for tool in module.TOOLS}
        names = {call["tool"] for call in plan["calls"]}
        schemas = {name: dict(description=originals[name].description,
                             args_schema=originals[name].args_schema.model_json_schema()) for name in names}
        cache = Path(output).resolve() / "private-cache"
        cfg = copy.deepcopy(runtime["defaults"].DEFAULT_CONFIG)
        cfg.update(source_cache_parent=str(cache), data_cache_dir=str(cache/"unused"), source_max_retries=0,
                   source_http_timeout=LIMITS["http_timeout_seconds"], source_max_response_bytes=LIMITS["max_response_bytes"],
                   source_max_http_requests=LIMITS["max_http_requests"], news_article_limit=5,
                   data_vendors=dict(core_stock_apis="yfinance", technical_indicators="yfinance", news_data="yfinance",
                                     macro_data="fred", prediction_markets="polymarket"), tool_vendors={})
        _data_only_socket_guard()
        with patch.object(source_http, "SOURCE_HOSTS", YAHOO_HOSTS), \
             patch.object(source_http, "HttpCapture", retaining_http_class(artifacts)), live_tools(trace, cfg):
            tools = {tool.name: tool for module in (market_analyst, news_analyst) for tool in module.TOOLS}
            def invoke(name, arguments):
                return tools[name].func(**arguments)
            def finish():
                bars = []
                for path in sorted(cache.rglob("*.csv")):
                    if path.is_symlink() or not path.resolve().is_relative_to(cache):
                        raise SourceBundleError("Fresh cache CSV path escaped capture")
                    bars.append(artifacts.write("bars/" + path.name, path.read_bytes()))
                return bars
            return _record_bundle(output, plan, invoke, trace=trace, schemas=schemas,
                                  upstream_binding=upstream_binding, artifacts=artifacts, finish=finish)


def capture_once(output, upstream, plan):
    """ROOT-ONLY opt-in public entry: one fresh bounded data-only process.

    This function performs fresh network IO. Default CLI never calls it.
    Independent review/authorization belongs to the orchestrator, not a flag.
    """
    if plan != make_plan(plan["as_of"], plan["stock_days"]):
        raise SourceBundleError("Unreviewed capture plan")
    output = Path(output).resolve()
    output.mkdir(exist_ok=False)
    (output/"plan.json").write_text(canonical(plan)+"\n", encoding="utf-8")
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--mode", "_worker",
               "--output", str(output), "--upstream", str(Path(upstream).resolve()), "--as-of", plan["as_of"],
               "--stock-days", str(plan["stock_days"])]
    try:
        result = subprocess.run(command, capture_output=True, timeout=LIMITS["wall_seconds"], shell=False)
    except subprocess.TimeoutExpired:
        raise SourceBundleError("Data-only capture deadline exceeded; partial directory retained") from None
    finally:
        # Worker has exited/killed before cleanup. Only its new private cache is
        # removed; copied CSV/body/text artifacts and all historical files remain.
        scratch = (output/"private-cache").resolve()
        if scratch.is_relative_to(output) and scratch != output and scratch.exists():
            shutil.rmtree(scratch)
    if result.returncode != 0:
        raise SourceBundleError("Data-only native capture failed; no complete replay bundle")
    path = output/"manifest.json"
    fingerprint = sha(path.read_bytes())
    bundle = ReplayBundle(path, expected_sha256=fingerprint)
    return dict(manifest_path=str(path), manifest_sha256=fingerprint,
                status=bundle.manifest["status"], core_ready=bundle.manifest["core_ready"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "capture", "inspect", "_worker"), default="preflight")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--stock-days", type=int, default=60)
    parser.add_argument("--output")
    parser.add_argument("--upstream")
    parser.add_argument("--manifest")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        plan = make_plan(args.as_of or current_source_date(), args.stock_days)
        if args.mode == "preflight":
            result = dict(status="PLAN_ONLY_NO_FETCH", plan=plan, model_calls=0,
                          network_calls=0, budget_access="NONE", dependency_check="NOT_RUN")
        elif args.mode == "inspect":
            if not args.manifest or not args.expected_sha256:
                parser.error("inspect requires --manifest and --expected-sha256")
            bundle = ReplayBundle(args.manifest, expected_sha256=args.expected_sha256)
            result = dict(status=bundle.manifest["status"], offers=bundle.offers(),
                          continuously_live=False, core_ready=bundle.manifest["core_ready"])
        else:
            if not args.output or not args.upstream:
                parser.error("capture requires explicit new --output and pinned --upstream")
            if args.mode == "_worker":
                saved = json.loads((Path(args.output)/"plan.json").read_text("utf-8"))
                if saved != plan:
                    raise SourceBundleError("Worker plan differs from requested capture")
                result = _native_worker(args.output, args.upstream, plan)
            else:
                result = capture_once(args.output, args.upstream, plan)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Native/provider exception URLs and cache paths never reach diagnostics.
        print(json.dumps(dict(status="UNAVAILABLE", error_type=type(exc).__name__,
                              message="Source adapter failed; no capture/availability success is claimed.")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
