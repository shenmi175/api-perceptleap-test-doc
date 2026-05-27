#!/usr/bin/env python3
"""Probe PerceptLeap audio endpoint compatibility without storing audio bodies."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://api.perceptleap.com"
AUDIO_FILE = Path("/tmp/perceptleap_alloy.wav")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-stdin", action="store_true")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--audio-file", default=str(AUDIO_FILE))
    parser.add_argument("--out", default="perceptleap_audio_probe_results.json")
    return parser.parse_args()


def read_key(args: argparse.Namespace) -> str:
    if args.key_stdin:
        if sys.stdin.isatty():
            return getpass.getpass("PerceptLeap API key: ").strip()
        return sys.stdin.readline().strip()
    return os.environ.get("PERCEPTLEAP_API_KEY", "").strip()


def parse_body(raw: bytes, content_type: str) -> dict[str, Any]:
    text_types = ("application/json", "text/", "application/problem+json")
    is_text = any(part in content_type for part in text_types)
    if is_text:
        text = raw.decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
            summary: dict[str, Any] = {"kind": "json", "keys": list(body.keys()) if isinstance(body, dict) else None}
            if isinstance(body, dict):
                if "error" in body:
                    summary["error"] = body["error"]
                if "text" in body:
                    summary["text_preview"] = str(body["text"])[:200]
                if "choices" in body:
                    choices = []
                    for choice in body.get("choices") or []:
                        message = choice.get("message", {}) if isinstance(choice, dict) else {}
                        item = {
                            "finish_reason": choice.get("finish_reason"),
                            "message_keys": list(message.keys()) if isinstance(message, dict) else None,
                        }
                        audio = message.get("audio") if isinstance(message, dict) else None
                        if isinstance(audio, dict):
                            item["audio_keys"] = list(audio.keys())
                            data = audio.get("data")
                            if isinstance(data, str):
                                item["audio_data_len"] = len(data)
                        content = message.get("content") if isinstance(message, dict) else None
                        if content is not None:
                            item["content_preview"] = str(content)[:200]
                        choices.append(item)
                    summary["choices_summary"] = choices
            return summary
        except Exception:
            return {"kind": "text", "text_preview": text[:500], "text_len": len(text)}
    return {
        "kind": "binary",
        "byte_len": len(raw),
        "magic_hex": raw[:16].hex(),
    }


def request_json(base_url: str, key: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "curl/8.5.0",
    }
    req = urllib.request.Request(base_url + endpoint, data=body, headers=headers, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return {
                "status": resp.status,
                "elapsed_ms": int((time.time() - start) * 1000),
                "content_type": resp.headers.get("content-type", ""),
                "summary": parse_body(raw, resp.headers.get("content-type", "")),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return {
            "status": exc.code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "content_type": exc.headers.get("content-type", ""),
            "summary": parse_body(raw, exc.headers.get("content-type", "")),
        }
    except Exception as exc:
        return {
            "status": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "exception": type(exc).__name__,
            "message": str(exc),
        }


def multipart_body(fields: dict[str, str], file_field: str, file_path: Path, file_type: str) -> tuple[bytes, str]:
    boundary = "----codex-audio-probe-" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
            f"Content-Type: {file_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def request_multipart(
    base_url: str,
    key: str,
    endpoint: str,
    fields: dict[str, str],
    file_path: Path,
) -> dict[str, Any]:
    body, content_type = multipart_body(fields, "file", file_path, "audio/wav")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": content_type,
        "User-Agent": "curl/8.5.0",
    }
    req = urllib.request.Request(base_url + endpoint, data=body, headers=headers, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return {
                "status": resp.status,
                "elapsed_ms": int((time.time() - start) * 1000),
                "content_type": resp.headers.get("content-type", ""),
                "summary": parse_body(raw, resp.headers.get("content-type", "")),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return {
            "status": exc.code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "content_type": exc.headers.get("content-type", ""),
            "summary": parse_body(raw, exc.headers.get("content-type", "")),
        }
    except Exception as exc:
        return {
            "status": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "exception": type(exc).__name__,
            "message": str(exc),
        }


def main() -> int:
    args = parse_args()
    key = read_key(args)
    if not key:
        print("missing API key", file=sys.stderr)
        return 2
    audio_file = Path(args.audio_file)
    if not audio_file.exists():
        print(f"missing audio file: {audio_file}", file=sys.stderr)
        return 2

    audio_b64 = base64.b64encode(audio_file.read_bytes()).decode("ascii")
    tests: list[dict[str, Any]] = [
        {
            "name": "tts_gpt_4o_mini_tts",
            "kind": "json",
            "endpoint": "/v1/audio/speech",
            "purpose": "TTS official model",
            "payload": {
                "model": "gpt-4o-mini-tts",
                "voice": "alloy",
                "input": "Hello. This is a short audio test.",
                "response_format": "mp3",
            },
        },
        {
            "name": "tts_tts_1",
            "kind": "json",
            "endpoint": "/v1/audio/speech",
            "purpose": "TTS legacy official model",
            "payload": {
                "model": "tts-1",
                "voice": "alloy",
                "input": "Hello. This is a short audio test.",
                "response_format": "mp3",
            },
        },
        {
            "name": "tts_gpt_4o_audio_preview_wrong_endpoint",
            "kind": "json",
            "endpoint": "/v1/audio/speech",
            "purpose": "Listed audio preview model used as TTS",
            "payload": {
                "model": "gpt-4o-audio-preview",
                "voice": "alloy",
                "input": "Hello. This is a short audio test.",
                "response_format": "mp3",
            },
        },
        {
            "name": "asr_whisper_1",
            "kind": "multipart",
            "endpoint": "/v1/audio/transcriptions",
            "purpose": "ASR official legacy model",
            "fields": {"model": "whisper-1", "response_format": "json"},
        },
        {
            "name": "asr_gpt_4o_transcribe",
            "kind": "multipart",
            "endpoint": "/v1/audio/transcriptions",
            "purpose": "ASR official model",
            "fields": {"model": "gpt-4o-transcribe", "response_format": "json"},
        },
        {
            "name": "asr_gpt_4o_mini_transcribe",
            "kind": "multipart",
            "endpoint": "/v1/audio/transcriptions",
            "purpose": "ASR official mini model",
            "fields": {"model": "gpt-4o-mini-transcribe", "response_format": "json"},
        },
        {
            "name": "asr_gpt_4o_audio_preview_wrong_endpoint",
            "kind": "multipart",
            "endpoint": "/v1/audio/transcriptions",
            "purpose": "Listed audio preview model used as ASR",
            "fields": {"model": "gpt-4o-audio-preview", "response_format": "json"},
        },
        {
            "name": "chat_audio_preview_text_only",
            "kind": "json",
            "endpoint": "/v1/chat/completions",
            "purpose": "Audio preview model as chat text model",
            "payload": {
                "model": "gpt-4o-audio-preview",
                "messages": [{"role": "user", "content": "Reply with exactly OK."}],
                "max_tokens": 16,
            },
        },
        {
            "name": "chat_audio_preview_audio_output",
            "kind": "json",
            "endpoint": "/v1/chat/completions",
            "purpose": "Audio preview model with audio output",
            "payload": {
                "model": "gpt-4o-audio-preview",
                "modalities": ["text", "audio"],
                "audio": {"voice": "alloy", "format": "wav"},
                "messages": [{"role": "user", "content": "Say OK once."}],
                "max_tokens": 32,
            },
        },
        {
            "name": "chat_audio_preview_audio_input_text_output",
            "kind": "json",
            "endpoint": "/v1/chat/completions",
            "purpose": "Audio preview model with audio input, text output",
            "payload": {
                "model": "gpt-4o-audio-preview",
                "modalities": ["text"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this audio briefly."},
                            {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                        ],
                    }
                ],
                "max_tokens": 64,
            },
        },
        {
            "name": "realtime_client_secret_gpt_4o_realtime_preview",
            "kind": "json",
            "endpoint": "/v1/realtime/client_secrets",
            "purpose": "Realtime model session token creation",
            "payload": {"session": {"type": "realtime", "model": "gpt-4o-realtime-preview"}},
        },
    ]

    results = []
    for test in tests:
        print(f"running {test['name']}...", flush=True)
        if test["kind"] == "multipart":
            result = request_multipart(args.base_url, key, test["endpoint"], test["fields"], audio_file)
            request_summary = {"fields": test["fields"], "audio_file": str(audio_file), "audio_bytes": audio_file.stat().st_size}
        else:
            result = request_json(args.base_url, key, test["endpoint"], test["payload"])
            request_summary = {
                key_: value
                for key_, value in test["payload"].items()
                if key_ not in {"messages", "input"}
            }
        results.append(
            {
                "name": test["name"],
                "endpoint": test["endpoint"],
                "purpose": test["purpose"],
                "request_summary": request_summary,
                "result": result,
            }
        )

    output = {
        "base_url": args.base_url,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "key": "<REDACTED_API_KEY>",
        "note": "Summaries only; generated/returned audio bytes, uploaded audio body, chat audio base64, and full key are not stored.",
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
