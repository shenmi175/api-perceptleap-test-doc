#!/usr/bin/env python3
"""Probe PerceptLeap image-generation parameter compatibility.

The script stores only summarized responses. It intentionally omits full API
keys, prompts, and base64 image payloads from the output JSON.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


BASE = "https://api.perceptleap.com"
PROMPT = "A simple flat icon of a blue square on a white background. No text."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-stdin", action="store_true")
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--out", default="perceptleap_image_param_compat_results.json")
    return parser.parse_args()


def read_key(args: argparse.Namespace) -> str:
    if args.key_stdin:
        if sys.stdin.isatty():
            return getpass.getpass("PerceptLeap API key: ").strip()
        return sys.stdin.readline().strip()
    return os.environ.get("PERCEPTLEAP_API_KEY", "").strip()


def summarize_json(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        summary: dict[str, Any] = {"keys": list(obj.keys())}
        if "error" in obj:
            summary["error"] = obj["error"]
        if "code" in obj or "message" in obj:
            summary["code"] = obj.get("code")
            summary["message"] = obj.get("message")
        if "data" in obj and isinstance(obj["data"], list) and obj["data"]:
            first = obj["data"][0]
            if isinstance(first, dict):
                summary["data0_keys"] = list(first.keys())
                for field in ("b64_json", "url"):
                    if first.get(field) is not None:
                        summary[f"data0_{field}_len"] = len(str(first[field]))
                if "revised_prompt" in first:
                    summary["revised_prompt_len"] = len(str(first.get("revised_prompt") or ""))
        if "output" in obj and isinstance(obj["output"], list):
            output_summary = []
            for item in obj["output"]:
                if not isinstance(item, dict):
                    continue
                entry = {"type": item.get("type"), "status": item.get("status")}
                if item.get("result") is not None:
                    entry["result_len"] = len(str(item["result"]))
                if "revised_prompt" in item:
                    entry["revised_prompt_len"] = len(str(item.get("revised_prompt") or ""))
                output_summary.append(entry)
            summary["output_summary"] = output_summary
        if "usage" in obj:
            summary["usage"] = obj["usage"]
        return summary
    if isinstance(obj, list):
        return {"type": "list", "len": len(obj)}
    return {"type": type(obj).__name__, "repr": repr(obj)[:500]}


def post_json(base_url: str, headers: dict[str, str], endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base_url + endpoint, data=body, headers=headers, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                summary = summarize_json(json.loads(text))
            except Exception:
                summary = {"non_json_preview": text[:500]}
            return {
                "status": resp.status,
                "elapsed_ms": int((time.time() - start) * 1000),
                "content_type": resp.headers.get("content-type", ""),
                "summary": summary,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            summary = summarize_json(json.loads(text))
        except Exception:
            summary = {"non_json_preview": text[:1000]}
        return {
            "status": exc.code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "content_type": exc.headers.get("content-type", ""),
            "summary": summary,
        }
    except Exception as exc:
        return {
            "status": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "exception": type(exc).__name__,
            "message": str(exc),
        }


def post_stream(base_url: str, headers: dict[str, str], endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base_url + endpoint, data=body, headers=headers, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            events: list[str] = []
            data_count = 0
            image_b64_lens: list[dict[str, Any]] = []
            for line in text.splitlines():
                if line.startswith("event: "):
                    events.append(line[len("event: ") :].strip())
                    continue
                if not line.startswith("data: "):
                    continue
                data_count += 1
                data = line[len("data: ") :]
                if data.strip() == "[DONE]":
                    continue
                try:
                    item = json.loads(data)
                except Exception:
                    continue
                for key in ("b64_json", "partial_image_b64"):
                    value = item.get(key)
                    if isinstance(value, str):
                        image_b64_lens.append({"event_type": item.get("type"), "field": key, "len": len(value)})
            return {
                "status": resp.status,
                "elapsed_ms": int((time.time() - start) * 1000),
                "content_type": resp.headers.get("content-type", ""),
                "summary": {
                    "event_types": sorted(set(events)),
                    "event_count": len(events),
                    "data_count": data_count,
                    "image_b64_lens": image_b64_lens,
                    "raw_len": len(text),
                },
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            summary = summarize_json(json.loads(text))
        except Exception:
            summary = {"non_json_preview": text[:1000]}
        return {
            "status": exc.code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "content_type": exc.headers.get("content-type", ""),
            "summary": summary,
        }
    except Exception as exc:
        return {
            "status": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "exception": type(exc).__name__,
            "message": str(exc),
        }


def test_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    image_tests = [
        {
            "name": "image_api_output_format_jpeg_compression",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "output_format": "jpeg",
                "output_compression": 45,
            },
            "expectation": "official_supported_should_work",
        },
        {
            "name": "image_api_background_opaque",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "background": "opaque",
            },
            "expectation": "official_supported_should_work",
        },
        {
            "name": "image_api_moderation_low",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "moderation": "low",
            },
            "expectation": "official_supported_should_work",
        },
        {
            "name": "image_api_flexible_size_1536x864",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1536x864",
                "quality": "low",
                "n": 1,
            },
            "expectation": "official_supported_should_work_if_flexible_size_forwarded",
        },
        {
            "name": "image_api_invalid_small_size_512x512",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "512x512",
                "quality": "low",
                "n": 1,
            },
            "expectation": "official_invalid_for_gpt_image_2_should_fail",
        },
        {
            "name": "image_api_background_transparent",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "background": "transparent",
                "output_format": "png",
            },
            "expectation": "official_unsupported_for_gpt_image_2_should_fail",
        },
        {
            "name": "image_api_response_format_url",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "response_format": "url",
            },
            "expectation": "official_dalle_only_should_fail_or_be_ignored",
        },
        {
            "name": "image_api_style_vivid",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "style": "vivid",
            },
            "expectation": "official_dalle3_only_should_fail_or_be_ignored",
        },
        {
            "name": "responses_tool_options_jpeg_compression_background_action",
            "endpoint": "/v1/responses",
            "payload": {
                "model": "gpt-5.4-mini",
                "input": "Generate a simple flat icon of a blue square on a white background. No text.",
                "store": False,
                "tools": [
                    {
                        "type": "image_generation",
                        "quality": "low",
                        "size": "1024x1024",
                        "output_format": "jpeg",
                        "output_compression": 45,
                        "background": "opaque",
                        "action": "generate",
                    }
                ],
            },
            "expectation": "official_tool_options_should_work",
        },
        {
            "name": "responses_tool_background_transparent",
            "endpoint": "/v1/responses",
            "payload": {
                "model": "gpt-5.4-mini",
                "input": "Generate a simple flat icon of a blue square on a transparent background. No text.",
                "store": False,
                "tools": [
                    {
                        "type": "image_generation",
                        "quality": "low",
                        "size": "1024x1024",
                        "output_format": "png",
                        "background": "transparent",
                        "action": "generate",
                    }
                ],
            },
            "expectation": "official_unsupported_for_gpt_image_2_should_fail",
        },
        {
            "name": "responses_tool_action_edit_without_image",
            "endpoint": "/v1/responses",
            "payload": {
                "model": "gpt-5.4-mini",
                "input": "Make the existing image more realistic.",
                "store": False,
                "tools": [{"type": "image_generation", "quality": "low", "size": "1024x1024", "action": "edit"}],
            },
            "expectation": "official_says_edit_without_image_should_error",
        },
    ]
    stream_tests = [
        {
            "name": "image_api_stream_partial_images_1",
            "endpoint": "/v1/images/generations",
            "payload": {
                "model": "gpt-image-2",
                "prompt": PROMPT,
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
                "stream": True,
                "partial_images": 1,
            },
            "expectation": "official_supported_streaming",
        },
        {
            "name": "responses_tool_stream_partial_images_1",
            "endpoint": "/v1/responses",
            "payload": {
                "model": "gpt-5.4-mini",
                "input": "Generate a simple flat icon of a blue square on a white background. No text.",
                "stream": True,
                "store": False,
                "tools": [
                    {
                        "type": "image_generation",
                        "quality": "low",
                        "size": "1024x1024",
                        "partial_images": 1,
                        "action": "generate",
                    }
                ],
            },
            "expectation": "official_supported_tool_streaming",
        },
    ]
    return image_tests, stream_tests


def payload_without_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"prompt", "input"}}


def main() -> int:
    args = parse_args()
    key = read_key(args)
    if not key:
        print("missing API key", file=sys.stderr)
        return 2

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "curl/8.5.0",
    }
    image_tests, stream_tests = test_cases()
    results = []
    for test in image_tests:
        print(f"running {test['name']}...", flush=True)
        result = post_json(args.base_url, headers, test["endpoint"], test["payload"])
        results.append(
            {
                "name": test["name"],
                "endpoint": test["endpoint"],
                "expectation": test["expectation"],
                "payload_without_prompt": payload_without_prompt(test["payload"]),
                "result": result,
            }
        )
    for test in stream_tests:
        print(f"running {test['name']}...", flush=True)
        result = post_stream(args.base_url, headers, test["endpoint"], test["payload"])
        results.append(
            {
                "name": test["name"],
                "endpoint": test["endpoint"],
                "expectation": test["expectation"],
                "payload_without_prompt": payload_without_prompt(test["payload"]),
                "result": result,
            }
        )

    output = {
        "base_url": args.base_url,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "key": "<REDACTED_API_KEY>",
        "note": "Summaries only; base64 image payloads and full API key are intentionally omitted.",
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
