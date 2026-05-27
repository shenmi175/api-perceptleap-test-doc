#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = "https://api.perceptleap.com"


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(value):
    if not value:
        return ""
    if len(value) <= 12:
        return "***"
    return value[:7] + "..." + value[-6:]


def read_key(args):
    if args.key_env and os.environ.get(args.key_env):
        return os.environ[args.key_env].strip()
    if args.key_stdin:
        key = sys.stdin.readline().strip()
        if not key:
            raise SystemExit("No API key received on stdin")
        return key
    raise SystemExit("Pass --key-stdin or set --key-env")


def summarize_body(raw, content_type):
    if raw is None:
        return {"kind": "none", "preview": ""}
    if "application/json" in (content_type or "").lower():
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
            return {"kind": "json", "json": parsed}
        except Exception:
            pass
    text = raw[:4096].decode("utf-8", errors="replace")
    return {
        "kind": "text_or_binary",
        "bytes": len(raw),
        "preview": text,
        "truncated": len(raw) > 4096,
    }


def request(base_url, key, method, path, body=None, headers=None, timeout=45, stream=False):
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "curl/8.5.0")
    req_headers.setdefault("Accept", "*/*")
    if key:
        req_headers["Authorization"] = "Bearer " + key
    data = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

    started = time.time()
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    ctx = ssl.create_default_context()
    result = {
        "method": method,
        "path": path,
        "url": url,
        "request_body": body if not isinstance(body, (bytes, bytearray)) else "<raw-bytes>",
        "started_at": now_iso(),
        "stream": stream,
    }
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            result["status"] = resp.status
            result["reason"] = resp.reason
            result["headers"] = {k.lower(): v for k, v in resp.headers.items()}
            if stream:
                result.update(read_sse(resp))
            else:
                raw = resp.read(256 * 1024)
                result["body"] = summarize_body(raw, resp.headers.get("Content-Type"))
    except urllib.error.HTTPError as e:
        raw = e.read(256 * 1024)
        result["status"] = e.code
        result["reason"] = e.reason
        result["headers"] = {k.lower(): v for k, v in e.headers.items()}
        result["body"] = summarize_body(raw, e.headers.get("Content-Type"))
    except Exception as e:
        result["status"] = None
        result["error"] = {"type": type(e).__name__, "message": str(e)}
    result["elapsed_ms"] = int((time.time() - started) * 1000)
    return result


def read_sse(resp, max_events=40, max_seconds=60):
    events = []
    started = time.time()
    current = {"event": None, "data": []}

    def flush():
        nonlocal current
        if current["event"] is None and not current["data"]:
            return None
        data = "\n".join(current["data"])
        ev = {"event": current["event"], "data_preview": data[:1000]}
        if data.strip() == "[DONE]":
            ev["done"] = True
        else:
            try:
                ev["json"] = json.loads(data)
            except Exception:
                pass
        current = {"event": None, "data": []}
        return ev

    while len(events) < max_events and time.time() - started < max_seconds:
        raw_line = resp.readline()
        if not raw_line:
            maybe = flush()
            if maybe:
                events.append(maybe)
            break
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            maybe = flush()
            if maybe:
                events.append(maybe)
                if maybe.get("done"):
                    break
            continue
        if line.startswith(":"):
            events.append({"comment": line[:200]})
            continue
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"].append(line.split(":", 1)[1].lstrip())

    return {"sse_events": events, "sse_event_count": len(events)}


def body_json(result):
    body = result.get("body") or {}
    return body.get("json")


def extract_model_ids(models_result):
    data = body_json(models_result)
    if not isinstance(data, dict):
        return []
    raw = data.get("data")
    if not isinstance(raw, list):
        return []
    ids = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
        elif isinstance(item, str):
            ids.append(item)
    return ids


def choose_model(ids, explicit=None):
    if explicit:
        return explicit
    priority = [
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5.1",
        "gpt-5",
        "gpt-4.1-mini",
        "gpt-4o-mini",
        "o4-mini",
        "o3-mini",
        "gpt-5.1-codex",
        "gpt-5-codex",
        "codex-mini-latest",
    ]
    for preferred in priority:
        for model_id in ids:
            if model_id == preferred or model_id.startswith(preferred + "-"):
                return model_id
    for model_id in ids:
        if model_id.startswith(("gpt-", "o", "codex")):
            return model_id
    return ids[0] if ids else "gpt-5.4-mini"


def classify(result):
    status = result.get("status")
    if status is None:
        return "transport_error"
    if 200 <= status < 300:
        return "success"
    if status in (401, 403):
        return "auth_or_permission_error"
    if status == 404:
        return "not_found"
    if status == 405:
        return "method_not_allowed"
    if status == 429:
        return "rate_limited"
    if 400 <= status < 500:
        return "client_error"
    if status >= 500:
        return "server_error"
    return "other"


def run_suite(base_url, key, model):
    results = []

    def add(name, method, path, body=None, headers=None, stream=False, key_override=None):
        result = request(
            base_url,
            key if key_override is None else key_override,
            method,
            path,
            body=body,
            headers=headers,
            stream=stream,
        )
        result["name"] = name
        result["classification"] = classify(result)
        results.append(result)
        return result

    add("missing_auth_models", "GET", "/v1/models", key_override="")
    models = add("models", "GET", "/v1/models")
    ids = extract_model_ids(models)
    selected = choose_model(ids, model)

    add("unknown_endpoint", "GET", "/v1/__probe_unknown__")
    add(
        "invalid_json_responses",
        "POST",
        "/v1/responses",
        body=b"{",
        headers={"Content-Type": "application/json"},
    )

    response_body = {
        "model": selected,
        "input": "Reply with exactly: OK",
        "max_output_tokens": 24,
        "stream": False,
        "store": False,
    }
    add("responses_min", "POST", "/v1/responses", response_body)
    add("responses_alias_min", "POST", "/responses", response_body)
    add("codex_backend_responses_min", "POST", "/backend-api/codex/responses", response_body)

    stream_response_body = dict(response_body)
    stream_response_body["stream"] = True
    add("responses_stream", "POST", "/v1/responses", stream_response_body, stream=True)

    json_schema_body = {
        "model": selected,
        "input": "Return JSON with one field ok set to true.",
        "max_output_tokens": 64,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ok_result",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
                "strict": True,
            }
        },
    }
    add("responses_json_schema", "POST", "/v1/responses", json_schema_body)

    function_body = {
        "model": selected,
        "input": "Call the record_answer tool with answer OK.",
        "max_output_tokens": 96,
        "store": False,
        "tools": [
            {
                "type": "function",
                "name": "record_answer",
                "description": "Record a short answer.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                },
                "strict": True,
            }
        ],
        "tool_choice": "auto",
    }
    add("responses_function_tool", "POST", "/v1/responses", function_body)

    add("responses_compact_probe", "POST", "/v1/responses/compact", {"model": selected})

    chat_body = {
        "model": selected,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_completion_tokens": 24,
        "stream": False,
    }
    add("chat_min", "POST", "/v1/chat/completions", chat_body)
    add("chat_alias_min", "POST", "/chat/completions", chat_body)

    chat_max_tokens = dict(chat_body)
    chat_max_tokens.pop("max_completion_tokens", None)
    chat_max_tokens["max_tokens"] = 24
    add("chat_max_tokens_legacy", "POST", "/v1/chat/completions", chat_max_tokens)

    chat_stream = dict(chat_body)
    chat_stream["stream"] = True
    add("chat_stream", "POST", "/v1/chat/completions", chat_stream, stream=True)

    chat_json = {
        "model": selected,
        "messages": [{"role": "user", "content": "Return JSON: {\"ok\": true}"}],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 64,
    }
    add("chat_json_object", "POST", "/v1/chat/completions", chat_json)

    chat_tool = {
        "model": selected,
        "messages": [{"role": "user", "content": "Call record_answer with answer OK."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "record_answer",
                    "description": "Record a short answer.",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
        "max_completion_tokens": 96,
    }
    add("chat_function_tool", "POST", "/v1/chat/completions", chat_tool)

    messages_body = {
        "model": selected,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 24,
        "stream": False,
    }
    add("anthropic_messages_probe", "POST", "/v1/messages", messages_body)

    add("model_get_selected", "GET", "/v1/models/" + urllib.parse.quote(selected, safe=""))
    add("files_list", "GET", "/v1/files")
    add("batches_list", "GET", "/v1/batches")
    add("assistants_list", "GET", "/v1/assistants")
    add("threads_list_probe", "GET", "/v1/threads")
    add("vector_stores_list", "GET", "/v1/vector_stores")

    add("embeddings_tiny", "POST", "/v1/embeddings", {"model": "text-embedding-3-small", "input": "hello"})
    add("moderations_tiny", "POST", "/v1/moderations", {"model": "omni-moderation-latest", "input": "hello"})

    add(
        "images_generations_route_probe",
        "POST",
        "/v1/images/generations",
        {"model": "gpt-image-1-mini", "prompt": "", "n": 1},
    )
    add(
        "images_edits_route_probe",
        "POST",
        "/v1/images/edits",
        {"model": "gpt-image-1-mini", "prompt": "make it blue"},
    )
    add(
        "images_variations_route_probe",
        "POST",
        "/v1/images/variations",
        {"model": "dall-e-2", "n": 1},
    )
    add(
        "audio_speech_route_probe",
        "POST",
        "/v1/audio/speech",
        {"model": "__probe__", "voice": "alloy", "input": "hi"},
    )
    add(
        "audio_transcriptions_route_probe",
        "POST",
        "/v1/audio/transcriptions",
        {"model": "whisper-1"},
    )
    add(
        "fine_tuning_jobs_list_probe",
        "GET",
        "/v1/fine_tuning/jobs",
    )

    return {"selected_model": selected, "model_ids": ids, "results": results}


def short_error(result):
    data = body_json(result)
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return {
                "type": err.get("type"),
                "code": err.get("code"),
                "message": str(err.get("message"))[:300],
            }
        if data.get("message"):
            return {"message": str(data.get("message"))[:300]}
    if result.get("error"):
        return result["error"]
    body = result.get("body") or {}
    if body.get("preview"):
        return {"message": body["preview"][:300]}
    return {}


def response_shape(result):
    data = body_json(result)
    if isinstance(data, dict):
        return sorted(data.keys())
    if result.get("sse_events"):
        names = []
        for ev in result["sse_events"][:10]:
            if ev.get("event"):
                names.append(ev["event"])
            elif ev.get("done"):
                names.append("[DONE]")
            elif ev.get("json"):
                names.append("json:" + str(ev["json"].get("object", "")))
            elif ev.get("comment"):
                names.append("comment")
        return names
    return []


def write_report(path, suite, key_redacted, base_url):
    lines = []
    lines.append("# PerceptLeap / sub2api API Compatibility Probe")
    lines.append("")
    lines.append(f"- Base URL: `{base_url}`")
    lines.append(f"- API key: `{key_redacted}`")
    lines.append(f"- Tested at: `{now_iso()}`")
    lines.append(f"- Selected model: `{suite['selected_model']}`")
    lines.append(f"- Models returned: `{len(suite['model_ids'])}`")
    lines.append("")
    lines.append("## Endpoint Results")
    lines.append("")
    lines.append("| Test | Method | Path | Status | Class | Elapsed | Shape / Error |")
    lines.append("| --- | --- | --- | ---: | --- | ---: | --- |")
    for r in suite["results"]:
        err = short_error(r)
        shape = response_shape(r)
        detail = json.dumps(err or shape, ensure_ascii=False)
        detail = detail.replace("|", "\\|").replace("\n", " ")
        if len(detail) > 360:
            detail = detail[:357] + "..."
        lines.append(
            f"| `{r['name']}` | `{r['method']}` | `{r['path']}` | "
            f"{r.get('status')} | `{r['classification']}` | {r.get('elapsed_ms')}ms | {detail} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `success` means the endpoint accepted the request used in this probe. It does not prove every OpenAI field is supported.")
    lines.append("- Route probes with intentionally invalid payloads, such as image/audio probes, are used to avoid unnecessary generation cost; their status mainly identifies routing and error-format behavior.")
    lines.append("- Raw summarized results are in `perceptleap_probe_results.json`.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--key-stdin", action="store_true")
    parser.add_argument("--key-env")
    parser.add_argument("--model")
    parser.add_argument("--json-out", default="perceptleap_probe_results.json")
    parser.add_argument("--report-out", default="perceptleap_probe_report.md")
    args = parser.parse_args()

    key = read_key(args)
    suite = run_suite(args.base_url, key, args.model)
    output = {
        "base_url": args.base_url,
        "api_key": redact(key),
        "tested_at": now_iso(),
        **suite,
    }
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    from pathlib import Path

    write_report(Path(args.report_out), suite, redact(key), args.base_url)

    summary = {
        "base_url": args.base_url,
        "api_key": redact(key),
        "selected_model": suite["selected_model"],
        "model_count": len(suite["model_ids"]),
        "successes": [r["name"] for r in suite["results"] if r["classification"] == "success"],
        "failures": [
            {
                "name": r["name"],
                "status": r.get("status"),
                "class": r["classification"],
                "error": short_error(r),
            }
            for r in suite["results"]
            if r["classification"] != "success"
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
