# PerceptLeap / sub2api API Compatibility and Usage Report

- Base URL: `https://api.perceptleap.com`
- Tested key: `<REDACTED_API_KEY>` (redacted)
- Main test date: `2026-05-25`
- Implementation note: the service is reported to be deployed from [`Wei-Shaw/sub2api`](https://github.com/Wei-Shaw/sub2api)
- Official OpenAI references used:
  - [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
  - [Images and vision guide](https://developers.openai.com/api/docs/guides/images-vision)
  - [GPT Image 2 model page](https://developers.openai.com/api/docs/models/gpt-image-2)

This report records what worked against this specific PerceptLeap deployment and where it differs from the official OpenAI API surface. It is not a guarantee for future keys or deployments; model pools and account capabilities may change.

## Executive Summary

The deployment is usable for text, tools/function calling, structured JSON output, streaming, image generation, and image understanding when requests are shaped correctly.

Recommended stable paths:

| Capability | Recommended endpoint | Status in test |
| --- | --- | --- |
| Model list | `GET /v1/models` | Working |
| Responses text | `POST /v1/responses` | Working |
| Chat Completions text | `POST /v1/chat/completions` | Working |
| Anthropic-style messages | `POST /v1/messages` | Working |
| Image generation, Image API | `POST /v1/images/generations` | Working with `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1` |
| Image generation, Responses tool | `POST /v1/responses` with `tools:[{"type":"image_generation"}]` | Working with `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini` |
| Image understanding, Responses API | `POST /v1/responses` with `input_image` | Working with `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini` |
| Image understanding, Chat Completions | `POST /v1/chat/completions` with `image_url` | Working with `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini` |

Avoid these no-`/v1` aliases for API clients:

| Path | Observed behavior |
| --- | --- |
| `/chat/completions` | HTTP 200 but returns the web UI HTML, not API JSON |
| `/messages` | HTTP 200 but returns the web UI HTML, not API JSON |

## Authentication

The deployment accepts all three tested API key header styles:

```http
Authorization: Bearer $PERCEPTLEAP_API_KEY
x-api-key: $PERCEPTLEAP_API_KEY
x-goog-api-key: $PERCEPTLEAP_API_KEY
```

Observed auth errors:

| Scenario | Status | Body shape |
| --- | ---: | --- |
| Missing key | 401 | `{"code":"API_KEY_REQUIRED","message":"..."}` |
| Invalid key | 401 | `{"code":"INVALID_API_KEY","message":"Invalid API key"}` |

Operational note: Python's default `urllib` user agent was blocked by Cloudflare with `Error 1010: browser_signature_banned`. `curl` worked. If you implement a custom client, set a normal `User-Agent`.

```http
User-Agent: curl/8.5.0
```

## Observed Models

`GET /v1/models` returned 42 models. Relevant models for image and vision tests:

| Category | Models observed |
| --- | --- |
| Mainline / text / vision | `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.2`, `gpt-4.1`, `gpt-4o`, `o3`, `o4-mini` |
| Codex | `codex-auto-review`, `gpt-5.3-codex`, `gpt-5.3-codex-spark` |
| Image generation | `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1` |

The screenshot-provided model list and the API model list may differ depending on UI filtering and account selection. Always use `GET /v1/models` for the active key.

## Text: Responses API

Use this as the preferred modern API for text, structured output, tools, streaming, and multimodal inputs.

### Minimal Text Request

```bash
export PERCEPTLEAP_API_KEY='REDACTED'

curl https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": "Reply with exactly: OK",
    "max_output_tokens": 24,
    "store": false
  }'
```

Important request parameters:

| Parameter | Type | Notes from test |
| --- | --- | --- |
| `model` | string | `gpt-5.4-mini`, `gpt-5.4`, `gpt-5.5` worked |
| `input` | string or array | Plain string and message-array input both worked |
| `max_output_tokens` | integer | Accepted; response may still echo `max_output_tokens: null` |
| `store` | boolean | Accepted; use `false` for transient testing |
| `reasoning` | object | `{"effort":"low"}` worked and was reflected in response |
| `temperature`, `top_p` | number | Accepted, but observed response still showed platform defaults `temperature: 1.0`, `top_p: 0.98`; treat as possibly ignored/rewritten |
| `max_tokens` | integer | Do not use with Responses; it triggered a 502 in one test |

### Structured JSON Output

```bash
curl https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": "Return JSON with one field ok set to true.",
    "max_output_tokens": 64,
    "store": false,
    "text": {
      "format": {
        "type": "json_schema",
        "name": "ok_result",
        "schema": {
          "type": "object",
          "additionalProperties": false,
          "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"]
        },
        "strict": true
      }
    }
  }'
```

Observed output included valid JSON text such as:

```json
{"ok": true}
```

### Function Tool Calling

```bash
curl https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": "Call the record_answer tool with answer OK.",
    "max_output_tokens": 96,
    "store": false,
    "tools": [{
      "type": "function",
      "name": "record_answer",
      "description": "Record a short answer.",
      "parameters": {
        "type": "object",
        "additionalProperties": false,
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"]
      },
      "strict": true
    }],
    "tool_choice": "auto"
  }'
```

Observed output contained a `function_call` item with `arguments: "{\"answer\":\"OK\"}"`.

### Streaming

```bash
curl -N https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": "Reply with exactly: OK",
    "max_output_tokens": 24,
    "stream": true,
    "store": false
  }'
```

Observed SSE events:

```text
response.created
response.in_progress
response.output_item.added
response.content_part.added
response.output_text.delta
response.output_text.done
response.content_part.done
response.output_item.done
response.completed
```

## Text: Chat Completions API

`/v1/chat/completions` works and returns OpenAI-style `chat.completion` objects.

### Minimal Chat Request

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_completion_tokens": 24
  }'
```

Observed response shape:

```json
{
  "id": "resp_...",
  "object": "chat.completion",
  "model": "gpt-5.4-mini",
  "choices": [
    {"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}
  ],
  "usage": {"prompt_tokens": 22, "completion_tokens": 5, "total_tokens": 27}
}
```

### Chat Streaming

```bash
curl -N https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_completion_tokens": 24,
    "stream": true
  }'
```

Observed stream chunks were standard `chat.completion.chunk` objects followed by `data: [DONE]`.

### Chat JSON Mode

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Return JSON: {\"ok\": true}"}],
    "response_format": {"type": "json_object"},
    "max_completion_tokens": 64
  }'
```

### Chat Function Calling

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Call record_answer with answer OK."}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "record_answer",
        "description": "Record a short answer.",
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "properties": {"answer": {"type": "string"}},
          "required": ["answer"]
        }
      }
    }],
    "tool_choice": "auto",
    "max_completion_tokens": 96
  }'
```

Observed `choices[0].message.tool_calls` with function arguments.

## Anthropic-Style Messages

`POST /v1/messages` worked and returned an Anthropic-like shape.

```bash
curl https://api.perceptleap.com/v1/messages \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_tokens": 24
  }'
```

Observed response shape:

```json
{
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "OK"}],
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 118, "output_tokens": 17}
}
```

## Image Generation: Image API

The official OpenAI Image API path is:

```text
POST /v1/images/generations
```

Official docs indicate `gpt-image-2` is the latest GPT Image model, and GPT Image models return base64 image data. This deployment worked with these models:

| Model | Status | Returned keys | Test latency |
| --- | ---: | --- | ---: |
| `gpt-image-2` | 200 | `b64_json`, `revised_prompt` | 13.8s |
| `gpt-image-1.5` | 200 | `b64_json`, `revised_prompt` | 13.2s |
| `gpt-image-1` | 200 | `b64_json`, `revised_prompt` | 14.1s |

### Minimal Image Generation

```bash
curl https://api.perceptleap.com/v1/images/generations \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "A single blue square icon on a white background.",
    "n": 1,
    "size": "1024x1024",
    "quality": "low",
    "output_format": "jpeg"
  }'
```

Save returned base64 to a file:

```bash
curl -s https://api.perceptleap.com/v1/images/generations \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "A single blue square icon on a white background.",
    "n": 1,
    "size": "1024x1024",
    "quality": "low",
    "output_format": "jpeg"
  }' | jq -r '.data[0].b64_json' | base64 --decode > image.jpg
```

### Image API Parameter Compatibility

Official OpenAI docs split image-generation parameters between GPT Image models and older DALL-E model-specific options. This PerceptLeap deployment should be treated as a GPT Image-compatible surface with a few gateway differences.

| Parameter | Official OpenAI behavior | PerceptLeap result |
| --- | --- | --- |
| `model` | GPT Image models include `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini` | Exposed image models were `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1`; `gpt-image-1-mini` was not in the model list |
| `prompt` | Required text prompt | Working |
| `n` | Multiple images are supported by official image generation APIs, with DALL-E 3 limited to `1` | Only `1` was tested here; multi-image requests were not tested to avoid extra cost |
| `size` | `gpt-image-2` supports flexible valid resolutions with documented constraints | `1024x1024` worked; `1536x864` worked; `512x512` failed with 502 |
| `quality` | GPT Image supports `low`, `medium`, `high`, `auto` | `low` worked; `medium`, `high`, and `auto` were not separately retested |
| `output_format` | GPT Image supports `png`, `jpeg`, `webp` | `jpeg` worked; default/PNG worked in other tests; `webp` was not separately retested |
| `output_compression` | Officially `0` to `100`, meaningful for `jpeg`/`webp` | `output_format: "jpeg"` plus `output_compression: 45` worked |
| `background` | `auto`, `opaque`, `transparent`; `gpt-image-2` currently does not support transparent backgrounds | `opaque` worked; `transparent` failed with 502 |
| `moderation` | GPT Image supports `auto` and `low` | `low` worked |
| `stream` | Image streaming is supported | `stream: true` worked |
| `partial_images` | `0` to `3` with streaming | `partial_images: 1` worked, with `image_generation.partial_image` and `image_generation.completed` events |
| `response_format` | DALL-E 2/3-oriented parameter; GPT Image normally returns base64 image data | PerceptLeap accepted `response_format: "url"` for `gpt-image-2`, but returned a very large `url` field, likely a data URL; do not rely on it |
| `style` | DALL-E 3-only parameter such as `vivid`/`natural` | `gpt-image-2` plus `style: "vivid"` failed with 502 |
| `user` | Optional end-user identifier | Not tested; not an image rendering control |

Parameter-specific test results from `perceptleap_image_param_compat_results.json`:

| Test | Key parameters | Status | Conclusion |
| --- | --- | ---: | --- |
| JPEG plus compression | `output_format: "jpeg"`, `output_compression: 45` | 200 | Working; returned `b64_json` and `revised_prompt` |
| Opaque background | `background: "opaque"` | 200 | Working |
| Low moderation | `moderation: "low"` | 200 | Working |
| Flexible size | `size: "1536x864"` | 200 | Working; this confirms forwarding of at least one flexible `gpt-image-2` size |
| Too-small size | `size: "512x512"` | 502 | Not usable for `gpt-image-2` |
| Transparent background | `background: "transparent"`, `output_format: "png"` | 502 | Not usable; official docs also state `gpt-image-2` does not support transparent backgrounds |
| URL response format | `response_format: "url"` | 200 | Accepted by PerceptLeap, but not recommended for GPT Image clients |
| DALL-E style parameter | `style: "vivid"` | 502 | Not usable with `gpt-image-2` |
| Image API streaming | `stream: true`, `partial_images: 1` | 200 | Working |

Recommended Image API body:

```json
{
  "model": "gpt-image-2",
  "prompt": "A single blue square icon on a white background.",
  "n": 1,
  "size": "1024x1024",
  "quality": "low",
  "output_format": "jpeg",
  "output_compression": 45,
  "background": "opaque",
  "moderation": "auto"
}
```

Avoid or treat as incompatible:

| Parameter shape | Reason | Safer alternative |
| --- | --- | --- |
| `background: "transparent"` | Officially unsupported by `gpt-image-2`; PerceptLeap returned 502 | Use `background: "opaque"` or omit it |
| `style: "vivid"` / `style: "natural"` | DALL-E 3-only | Describe style in the prompt |
| `size: "512x512"` | Invalid for `gpt-image-2` constraints; PerceptLeap returned 502 | Use `1024x1024`, `1536x1024`, `1024x1536`, or another valid flexible size |
| `response_format: "url"` | PerceptLeap accepted it but returned a very large field; GPT Image clients should consume base64 | Omit it and read `data[0].b64_json` |
| `model: "gpt-image-1-mini"` | Official model but not exposed by this deployment | Use `gpt-image-2` |
| DALL-E model-specific parameter sets | `dall-e-2`/`dall-e-3` were not observed in this model list | Use GPT Image parameters |

## Image Generation: Responses Tool

The Responses API can call an image generation tool.

Tested working models:

| Mainline model | Status | Output item | Test latency |
| --- | ---: | --- | ---: |
| `gpt-5.5` | 200 | `image_generation_call.result` | 15.0s |
| `gpt-5.4` | 200 | `image_generation_call.result` | 15.9s |
| `gpt-5.4-mini` | 200 | `image_generation_call.result` | 14.9s |

```bash
curl https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": "Generate a single blue square icon on a white background.",
    "tools": [{
      "type": "image_generation",
      "quality": "low",
      "size": "1024x1024",
      "output_format": "jpeg"
    }],
    "store": false
  }'
```

Save the generated image:

```bash
curl -s https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": "Generate a single blue square icon on a white background.",
    "tools": [{"type":"image_generation","quality":"low","size":"1024x1024","output_format":"jpeg"}],
    "store": false
  }' | jq -r '.output[] | select(.type=="image_generation_call") | .result' | head -n1 | base64 --decode > image.jpg
```

### Responses Image Tool Parameter Compatibility

Official Responses image generation tool options include `size`, `quality`, `output_format`, `output_compression`, `background`, `partial_images`, and `action`. `action` can be `auto`, `generate`, or `edit`.

| Test | Key parameters | Status | Conclusion |
| --- | --- | ---: | --- |
| Combined tool options | `quality: "low"`, `size: "1024x1024"`, `output_format: "jpeg"`, `output_compression: 45`, `background: "opaque"`, `action: "generate"` | 200 | Working; returned `image_generation_call.result` |
| Transparent background | `background: "transparent"`, `output_format: "png"`, `action: "generate"` | 502 | Not usable |
| Forced edit without input image | `action: "edit"` without image context | 502 | Not usable; official docs also say forced edit needs an image in context |
| Tool streaming | top-level `stream: true`, tool `partial_images: 1` | 200 | Working; received `response.image_generation_call.partial_image` events |

Recommended tool object:

```json
{
  "type": "image_generation",
  "quality": "low",
  "size": "1024x1024",
  "output_format": "jpeg",
  "output_compression": 45,
  "background": "opaque",
  "action": "generate"
}
```

The Responses tool returns image data in `output[]` items where `type` is `image_generation_call`; the base64 image is in `result`, not `data[0].b64_json`.

## Image Understanding: Responses API

Official OpenAI docs support image inputs through `input_image` in the Responses API. This deployment worked with remote image URLs.

Test image URL used:

```text
https://api.nga.gov/iiif/a2e6da57-3cd1-4235-b20e-95dcaefed6c8/full/!800,800/0/default.jpg
```

Tested results:

| Model | Status | Result |
| --- | ---: | --- |
| `gpt-5.5` | 200 | Described a portrait painting |
| `gpt-5.4` | 200 | Described a portrait painting |
| `gpt-5.4-mini` | 200 | Described a portrait painting |
| `gpt-4.1-mini` | 502 | Failed on this deployment |

```bash
curl https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": [{
      "role": "user",
      "content": [
        {"type": "input_text", "text": "What is in this image? Answer briefly."},
        {
          "type": "input_image",
          "image_url": "https://api.nga.gov/iiif/a2e6da57-3cd1-4235-b20e-95dcaefed6c8/full/!800,800/0/default.jpg",
          "detail": "low"
        }
      ]
    }],
    "max_output_tokens": 80,
    "store": false
  }'
```

Useful parameters:

| Parameter | Type | Notes |
| --- | --- | --- |
| `input[].content[].type` | string | Use `input_text` and `input_image` for Responses API |
| `image_url` | string | Fully qualified URL or data URL per official docs; remote URL was confirmed working |
| `detail` | string | `low` worked; official docs define `low`, `high`, `original`, `auto` depending on model |
| `max_output_tokens` | integer | Use to cap text response cost |

## Image Understanding: Chat Completions API

The Chat Completions image input shape differs from Responses. Use `type: "image_url"`.

Tested results:

| Model | Status | Result |
| --- | ---: | --- |
| `gpt-5.5` | 200 | Described a portrait painting |
| `gpt-5.4` | 200 | Described a portrait painting |
| `gpt-5.4-mini` | 200 | Described a portrait painting |
| `gpt-4.1-mini` | 400 | Not supported with this Codex/ChatGPT account path |

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "What is in this image? Answer briefly."},
        {
          "type": "image_url",
          "image_url": {
            "url": "https://api.nga.gov/iiif/a2e6da57-3cd1-4235-b20e-95dcaefed6c8/full/!800,800/0/default.jpg",
            "detail": "low"
          }
        }
      ]
    }],
    "max_completion_tokens": 80
  }'
```

## Image Edits and Variations

| Endpoint | Observed status | Notes |
| --- | ---: | --- |
| `POST /v1/images/edits` | 400 with JSON probe | Route exists, but the test body was intentionally incomplete and returned `images[].image_url is required`; no successful edit was performed |
| `POST /v1/images/variations` | 404 | Not available on this deployment |

Do not treat image editing as verified until a proper edit request is tested with the deployment's expected payload shape.

## Unsupported or Not Implemented OpenAI Endpoints

These official OpenAI endpoints returned `404 page not found` in this deployment:

| Endpoint | Status |
| --- | ---: |
| `GET /v1/models/{model}` | 404 |
| `GET /v1/files` | 404 |
| `GET /v1/batches` | 404 |
| `GET /v1/assistants` | 404 |
| `GET /v1/threads` | 404 |
| `GET /v1/vector_stores` | 404 |
| `POST /v1/embeddings` | 404 |
| `POST /v1/moderations` | 404 |
| `POST /v1/audio/speech` | 404 |
| `POST /v1/audio/transcriptions` | 404 |
| `GET /v1/fine_tuning/jobs` | 404 |
| `GET /v1/responses/{id}` | 404 |
| `GET /v1/chat/completions/{id}` | 404 |

## Error Format Differences

The deployment does not always return official OpenAI error shapes.

Observed examples:

| Error source | Shape |
| --- | --- |
| Missing/invalid API key | `{"code":"...","message":"..."}` |
| Invalid JSON body | `{"error":{"message":"Failed to parse request body","type":"invalid_request_error"}}` |
| Unknown route | plain text `404 page not found` |
| Some upstream failures | Cloudflare HTML or plain `error code: 502` |

Client code should not assume every failure is parseable as OpenAI-style JSON.

## Recommended Client Defaults

Use these defaults for lower-risk integration:

- Base URL: `https://api.perceptleap.com/v1`
- Always include `/v1` in API paths.
- Prefer `Authorization: Bearer $PERCEPTLEAP_API_KEY`.
- Set `User-Agent` if using a low-level HTTP client.
- Use `gpt-5.4-mini` for inexpensive text/vision testing.
- Use `gpt-image-2` for image generation unless you specifically need `gpt-image-1.5` or `gpt-image-1` comparison.
- For Responses API, use `max_output_tokens`, not `max_tokens`.
- For Chat Completions, `max_completion_tokens` and legacy `max_tokens` both worked in testing.
- For image testing, start with `quality: "low"`, `size: "1024x1024"`, `n: 1`, and omit `response_format`.

## Test Artifact Files

| File | Purpose |
| --- | --- |
| `perceptleap_probe_results.json` | Main endpoint probe result summary |
| `perceptleap_extra_results.json` | Extra auth and parameter probe results |
| `perceptleap_image_api_curl_results.json` | Image API generation retest results |
| `perceptleap_responses_image_tool_curl_results.json` | Responses image generation tool retest results |
| `perceptleap_image_param_compat_results.json` | Focused image-generation parameter compatibility results |
| `perceptleap_vision_curl_results.json` | Vision/image understanding retest results |
| `probe_perceptleap.py` | Reusable Python probe script |
| `run_probe_noecho.sh` | Wrapper that reads the API key without terminal echo |
