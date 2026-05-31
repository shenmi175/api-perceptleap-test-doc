# PerceptLeap / sub2api API 兼容性与使用说明（中文版）

由于部分用户涉嫌违法调用api，目前已经开启邀请注册
向zmb1227@gmail.com发送邮件经过审批后获取邀请码

- 测试服务：`https://api.perceptleap.com`
- 测试日期：`2026-05-25`
- 测试 Key：`<REDACTED_API_KEY>`（已脱敏，文档中不保存完整密钥）
- 已知部署来源：该平台声称基于 [`Wei-Shaw/sub2api`](https://github.com/Wei-Shaw/sub2api) 搭建
- 对照的 OpenAI 官方文档：
  - [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
  - [Images and vision guide](https://developers.openai.com/api/docs/guides/images-vision)
  - [GPT Image 2 model page](https://developers.openai.com/api/docs/models/gpt-image-2)

本文档记录的是这一次针对 `api.perceptleap.com` 和当前临时 Key 的实测结果。模型列表、账号能力、上游账号池可能变化，所以后续接入前最好重新跑一遍最小测试。

## 1. 总结

当前这个部署不是完整的 OpenAI 官方 API 镜像，但核心能力已经比较可用：文本、流式输出、结构化 JSON、函数调用、图像生成、图像解释都能跑通。

推荐使用的能力和端点如下：

| 能力 | 推荐端点 | 实测状态 |
| --- | --- | --- |
| 获取模型列表 | `GET /v1/models` | 可用 |
| Responses 文本生成 | `POST /v1/responses` | 可用 |
| Chat Completions 文本生成 | `POST /v1/chat/completions` | 可用 |
| Anthropic 风格 Messages | `POST /v1/messages` | 可用 |
| 图像生成：Images API | `POST /v1/images/generations` | 可用，`gpt-image-2`、`gpt-image-1.5`、`gpt-image-1` 均成功 |
| 图像生成：Responses 工具 | `POST /v1/responses` + `tools:[{"type":"image_generation"}]` | 可用，`gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini` 均成功 |
| 图像解释：Responses API | `POST /v1/responses` + `input_image` | 可用，`gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini` 均成功 |
| 图像解释：Chat Completions | `POST /v1/chat/completions` + `image_url` | 可用，`gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini` 均成功 |

需要避免的路径：

| 路径 | 实测现象 |
| --- | --- |
| `/chat/completions` | HTTP 200，但返回的是前端网页 HTML，不是 API JSON |
| `/messages` | HTTP 200，但返回的是前端网页 HTML，不是 API JSON |

结论：实际业务调用时请坚持使用 `/v1/...` 路径。

## 2. 鉴权方式

当前部署支持三种 Key 传法：

```http
Authorization: Bearer $PERCEPTLEAP_API_KEY
x-api-key: $PERCEPTLEAP_API_KEY
x-goog-api-key: $PERCEPTLEAP_API_KEY
```

最推荐用 OpenAI 风格：

```http
Authorization: Bearer $PERCEPTLEAP_API_KEY
```

错误表现：

| 场景 | HTTP 状态码 | 返回体 |
| --- | ---: | --- |
| 未提供 Key | 401 | `{"code":"API_KEY_REQUIRED","message":"..."}` |
| Key 错误 | 401 | `{"code":"INVALID_API_KEY","message":"Invalid API key"}` |

注意：Python 默认 `urllib` 的 `User-Agent` 被 Cloudflare 拦截过，错误为 `Error 1010: browser_signature_banned`。`curl` 正常。自写 HTTP 客户端时建议设置正常的 User-Agent，例如：

```http
User-Agent: curl/8.5.0
```

## 3. 模型列表

`GET /v1/models` 实测返回 42 个模型。和截图相关、或者本次测试用到的模型如下：

| 类型 | 模型 |
| --- | --- |
| 文本 / 视觉主模型 | `gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.2`、`gpt-4.1`、`gpt-4o`、`o3`、`o4-mini` |
| Codex 相关 | `codex-auto-review`、`gpt-5.3-codex`、`gpt-5.3-codex-spark` |
| 图像生成 | `gpt-image-2`、`gpt-image-1.5`、`gpt-image-1` |

重要：你截图里的模型列表和 API 返回的完整列表可能不完全一致，UI 可能有筛选。接入前以 `GET /v1/models` 返回为准。

查询模型列表：

```bash
export PERCEPTLEAP_API_KEY='你的 Key'

curl https://api.perceptleap.com/v1/models \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY"
```

## 4. Responses API：文本生成

Responses API 是 OpenAI 当前推荐的新接口形态，适合文本、多模态输入、工具调用、结构化输出、图像生成工具等场景。

### 4.1 最小文本请求

```bash
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

关键参数说明：

| 参数 | 类型 | 是否建议 | 说明 |
| --- | --- | --- | --- |
| `model` | string | 必填 | 实测 `gpt-5.4-mini`、`gpt-5.4`、`gpt-5.5` 可用 |
| `input` | string 或 array | 必填 | 可以传字符串，也可以传消息数组 |
| `max_output_tokens` | integer | 推荐 | 控制输出 token；Responses API 用这个，不要用 `max_tokens` |
| `store` | boolean | 推荐 | 测试和临时请求建议用 `false` |
| `reasoning` | object | 可选 | `{"effort":"low"}` 实测可用 |
| `temperature` | number | 谨慎 | 请求可接受，但返回中仍显示平台默认 `1.0`，可能被网关忽略或重写 |
| `top_p` | number | 谨慎 | 请求可接受，但返回中仍显示平台默认 `0.98`，可能被网关忽略或重写 |
| `max_tokens` | integer | 不建议 | 在 Responses API 中实测触发过 502，应避免 |

### 4.2 多轮/消息数组输入

```bash
curl https://api.perceptleap.com/v1/responses \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "input": [
      {"role": "user", "content": "Reply with exactly: OK"}
    ],
    "max_output_tokens": 24,
    "store": false
  }'
```

### 4.3 结构化 JSON 输出

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
          "properties": {
            "ok": {"type": "boolean"}
          },
          "required": ["ok"]
        },
        "strict": true
      }
    }
  }'
```

实测返回内容类似：

```json
{"ok": true}
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `text.format.type` | 使用 `json_schema` 开启结构化输出 |
| `text.format.name` | schema 名称 |
| `text.format.schema` | JSON Schema |
| `text.format.strict` | `true` 表示严格匹配 schema |

### 4.4 函数调用 / 工具调用

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
        "properties": {
          "answer": {"type": "string"}
        },
        "required": ["answer"]
      },
      "strict": true
    }],
    "tool_choice": "auto"
  }'
```

实测返回的 `output` 中会包含：

```json
{
  "type": "function_call",
  "name": "record_answer",
  "arguments": "{\"answer\":\"OK\"}"
}
```

### 4.5 流式输出

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

实测 SSE 事件顺序：

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

## 5. Chat Completions API：文本生成

如果你的现有项目使用 OpenAI 旧版 Chat Completions API，当前部署也能兼容。

### 5.1 最小请求

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [
      {"role": "user", "content": "Reply with exactly: OK"}
    ],
    "max_completion_tokens": 24
  }'
```

返回形态是 OpenAI 风格：

```json
{
  "object": "chat.completion",
  "model": "gpt-5.4-mini",
  "choices": [
    {
      "message": {"role": "assistant", "content": "OK"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 22,
    "completion_tokens": 5,
    "total_tokens": 27
  }
}
```

### 5.2 Chat Completions 参数说明

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `model` | string | 模型名，例如 `gpt-5.4-mini` |
| `messages` | array | 对话数组，包含 `role` 和 `content` |
| `max_completion_tokens` | integer | 新参数，推荐使用 |
| `max_tokens` | integer | 旧参数，实测仍可用 |
| `stream` | boolean | 是否使用 SSE 流式输出 |
| `response_format` | object | 可用 `{"type":"json_object"}` |
| `tools` | array | 函数调用工具列表 |
| `tool_choice` | string/object | `auto` 实测可用 |
| `reasoning_effort` | string | `low` 实测可用 |

### 5.3 流式输出

```bash
curl -N https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [
      {"role": "user", "content": "Reply with exactly: OK"}
    ],
    "max_completion_tokens": 24,
    "stream": true
  }'
```

实测返回标准 `chat.completion.chunk`，最后以：

```text
data: [DONE]
```

结束。

### 5.4 JSON 模式

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [
      {"role": "user", "content": "Return JSON: {\"ok\": true}"}
    ],
    "response_format": {"type": "json_object"},
    "max_completion_tokens": 64
  }'
```

### 5.5 函数调用

```bash
curl https://api.perceptleap.com/v1/chat/completions \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [
      {"role": "user", "content": "Call record_answer with answer OK."}
    ],
    "tools": [{
      "type": "function",
      "function": {
        "name": "record_answer",
        "description": "Record a short answer.",
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "answer": {"type": "string"}
          },
          "required": ["answer"]
        }
      }
    }],
    "tool_choice": "auto",
    "max_completion_tokens": 96
  }'
```

返回中会有：

```json
"tool_calls": [
  {
    "type": "function",
    "function": {
      "name": "record_answer",
      "arguments": "{\"answer\":\"OK\"}"
    }
  }
]
```

## 6. Anthropic 风格 Messages API

当前部署支持：

```text
POST /v1/messages
```

示例：

```bash
curl https://api.perceptleap.com/v1/messages \
  -H "Authorization: Bearer $PERCEPTLEAP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [
      {"role": "user", "content": "Reply with exactly: OK"}
    ],
    "max_tokens": 24
  }'
```

实测返回类似 Anthropic Messages：

```json
{
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "OK"}
  ],
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 118,
    "output_tokens": 17
  }
}
```

注意：不要使用 `/messages`，它返回网页 HTML；要使用 `/v1/messages`。

## 7. 图像生成：Images API

OpenAI 官方图像生成接口是：

```text
POST /v1/images/generations
```

官方文档中 `gpt-image-2` 是新的图像生成模型；GPT Image 模型返回 base64 图像数据。当前部署实测可用模型：

| 模型 | 状态 | 返回字段 | 实测耗时 |
| --- | ---: | --- | ---: |
| `gpt-image-2` | 200 | `b64_json`、`revised_prompt` | 13.8 秒 |
| `gpt-image-1.5` | 200 | `b64_json`、`revised_prompt` | 13.2 秒 |
| `gpt-image-1` | 200 | `b64_json`、`revised_prompt` | 14.1 秒 |

### 7.1 最小图像生成请求

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

### 7.2 保存图像到本地

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

### 7.3 图像生成参数说明

官方 OpenAI 文档中，`/v1/images/generations` 的 GPT Image 参数主要分为两类：GPT Image 模型参数，以及 DALL-E 旧模型专用参数。PerceptLeap 当前部署并不是完整 OpenAI 官方 API 镜像，所以要按实测结果使用。

官方基线：

| 参数 | 官方说明 | PerceptLeap 实测结论 |
| --- | --- | --- |
| `model` | 官方 GPT Image 模型包括 `gpt-image-2`、`gpt-image-1.5`、`gpt-image-1`、`gpt-image-1-mini` | 当前模型列表只有 `gpt-image-2`、`gpt-image-1.5`、`gpt-image-1`；没有看到 `gpt-image-1-mini` |
| `prompt` | 必填，图像描述文本 | 可用 |
| `n` | 官方可生成多张，通常 `1` 到 `10`；DALL-E 3 只支持 `1` | 只实测 `1`；多张未测，成本会按图片数增加 |
| `size` | `gpt-image-2` 支持满足约束的灵活尺寸；边长需为 16 的倍数，比例不超过 3:1，总像素需在官方限制内 | `1024x1024` 成功；`1536x864` 成功；`512x512` 失败，返回 502 |
| `quality` | GPT Image 支持 `low`、`medium`、`high`、`auto` | `low` 成功；`medium`、`high`、`auto` 未单独复测 |
| `output_format` | GPT Image 支持 `png`、`jpeg`、`webp` | `jpeg` 成功；默认/`png` 在其它测试中成功；`webp` 未单独复测 |
| `output_compression` | 官方支持 `0` 到 `100`，只对 `jpeg`/`webp` 有意义 | `output_format: "jpeg"` + `output_compression: 45` 成功 |
| `background` | 官方支持 `auto`、`opaque`、`transparent`，但 `gpt-image-2` 当前不支持透明背景 | `opaque` 成功；`transparent` 失败，返回 502 |
| `moderation` | 官方 GPT Image 支持 `auto`、`low` | `low` 成功 |
| `stream` | GPT Image 支持流式图像生成 | `stream: true` 成功 |
| `partial_images` | 官方支持 `0` 到 `3`，需配合 `stream: true` | `partial_images: 1` 成功，收到 `image_generation.partial_image` 和 `image_generation.completed` 事件 |
| `response_format` | 官方当前主要是 DALL-E 2/3 参数；GPT Image 默认返回 base64，不建议对 `gpt-image-2` 使用 | PerceptLeap 对 `gpt-image-2` 接受了 `response_format: "url"`，返回 `data[0].url`，但字段长度约 1,010,350，疑似数据 URL，不是普通公网 URL；不建议依赖 |
| `style` | 官方 DALL-E 3 专用，取值如 `vivid`、`natural` | `gpt-image-2` + `style: "vivid"` 失败，返回 502；不要用于 GPT Image 模型 |
| `user` | 官方可选终端用户标识 | 未测；不是生成效果参数 |

### 7.4 Images API 参数兼容性实测表

测试日期：`2026-05-25`。结果文件：`perceptleap_image_param_compat_results.json`。

| 测试项 | 请求参数重点 | HTTP 状态 | 结论 |
| --- | --- | ---: | --- |
| JPEG 与压缩 | `output_format: "jpeg"`、`output_compression: 45` | 200 | 可用，返回 `b64_json` 和 `revised_prompt` |
| 不透明背景 | `background: "opaque"` | 200 | 可用 |
| 审核等级 | `moderation: "low"` | 200 | 可用 |
| 灵活尺寸 | `size: "1536x864"` | 200 | 可用，说明 PerceptLeap 能转发 `gpt-image-2` 的部分官方灵活尺寸 |
| 过小尺寸 | `size: "512x512"` | 502 | 不可用；对 `gpt-image-2` 也不符合官方尺寸约束 |
| 透明背景 | `background: "transparent"`、`output_format: "png"` | 502 | 不可用；官方也说明 `gpt-image-2` 当前不支持透明背景 |
| URL 返回格式 | `response_format: "url"` | 200 | 可用但不推荐；返回 `url` 字段且长度极大，疑似数据 URL；官方 GPT Image 推荐直接使用 `b64_json` |
| DALL-E 风格参数 | `style: "vivid"` | 502 | 不可用；这是 DALL-E 3 参数，不适用于 `gpt-image-2` |
| Images 流式生成 | `stream: true`、`partial_images: 1` | 200 | 可用，收到 partial 和 completed SSE 事件 |

推荐请求参数：

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

不建议或不可用参数：

| 参数写法 | 原因 | 建议替代 |
| --- | --- | --- |
| `background: "transparent"` | `gpt-image-2` 官方不支持，PerceptLeap 返回 502 | 用 `background: "opaque"` 或省略 |
| `style: "vivid"` / `style: "natural"` | DALL-E 3 专用，PerceptLeap 对 `gpt-image-2` 返回 502 | 通过 prompt 描述风格 |
| `size: "512x512"` | 不符合 `gpt-image-2` 官方尺寸约束，PerceptLeap 返回 502 | 用 `1024x1024`、`1536x1024`、`1024x1536` 或其它合法尺寸 |
| `response_format: "url"` | PerceptLeap 虽然返回 200，但返回内容很长，疑似数据 URL；官方 GPT Image 推荐 base64 | 省略该参数，读取 `data[0].b64_json` |
| `model: "gpt-image-1-mini"` | 官方有该模型，但当前 PerceptLeap 模型列表未暴露 | 用 `gpt-image-2` |
| DALL-E 模型参数组合 | 当前 PerceptLeap 模型列表未见 `dall-e-2`、`dall-e-3` | 使用 GPT Image 参数 |

建议：测试阶段使用 `quality: "low"`、`size: "1024x1024"`、`n: 1`，避免成本和耗时过高。正式接入时优先省略 `response_format`，按 GPT Image 默认返回的 `b64_json` 保存图片。

## 8. 图像生成：Responses API 的 image_generation 工具

除了 `/v1/images/generations`，也可以让 Responses API 调用图像生成工具。

实测可用：

| 主模型 | 状态 | 输出字段 | 实测耗时 |
| --- | ---: | --- | ---: |
| `gpt-5.5` | 200 | `image_generation_call.result` | 15.0 秒 |
| `gpt-5.4` | 200 | `image_generation_call.result` | 15.9 秒 |
| `gpt-5.4-mini` | 200 | `image_generation_call.result` | 14.9 秒 |

请求示例：

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

保存图像：

```bash
curl -s https://api.perceptleap.com/v1/responses \
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
  }' | jq -r '.output[] | select(.type=="image_generation_call") | .result' | head -n1 | base64 --decode > image.jpg
```

与 Images API 的区别：

| 方式 | 适用场景 |
| --- | --- |
| `/v1/images/generations` | 单次根据 prompt 生成图片，最直接 |
| `/v1/responses` + `image_generation` | 对话式、多步骤、多模态流程中生成图片 |

### 8.1 Responses 图像工具参数差异

官方 Responses `image_generation` 工具支持的图像输出参数包括 `size`、`quality`、`output_format`、`output_compression`、`background`、`partial_images`，并额外支持 `action` 控制生成或编辑：`auto`、`generate`、`edit`。

PerceptLeap 实测：

| 测试项 | 参数重点 | HTTP 状态 | 结论 |
| --- | --- | ---: | --- |
| 工具输出参数组合 | `quality: "low"`、`size: "1024x1024"`、`output_format: "jpeg"`、`output_compression: 45`、`background: "opaque"`、`action: "generate"` | 200 | 可用，返回 `image_generation_call.result` |
| 透明背景 | `background: "transparent"`、`output_format: "png"`、`action: "generate"` | 502 | 不可用；与 Images API 一致 |
| 强制编辑但不提供输入图 | `action: "edit"`，请求中没有图片上下文 | 502 | 不可用；官方也说明没有输入图时强制编辑会报错 |
| 工具流式 partial image | 顶层 `stream: true`，工具内 `partial_images: 1` | 200 | 可用，收到 `response.image_generation_call.partial_image` 事件 |

推荐工具参数：

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

注意：Responses 工具返回图片在 `output[]` 中，字段是 `image_generation_call.result`，不是 Images API 的 `data[0].b64_json`。

## 9. 图像解释：Responses API

OpenAI 官方文档中，Responses API 的图像输入使用：

```json
{"type": "input_image", "image_url": "..."}
```

当前部署实测结果：

| 模型 | 状态 | 结果 |
| --- | ---: | --- |
| `gpt-5.5` | 200 | 成功描述图片内容 |
| `gpt-5.4` | 200 | 成功描述图片内容 |
| `gpt-5.4-mini` | 200 | 成功描述图片内容 |
| `gpt-4.1-mini` | 502 | 当前部署失败 |

示例：

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

实测返回文本示例：

```text
A painted portrait of a seated woman in a striped dress.
```

### 9.1 图像解释参数说明

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `input[].role` | string | 通常为 `user` |
| `input[].content[]` | array | 同一条消息中可以混合文本和图片 |
| `type: input_text` | object | 文本问题 |
| `type: input_image` | object | 图片输入 |
| `image_url` | string | 图片 URL；官方也支持 base64 data URL 或 file ID，但本次确认的是远程 URL |
| `detail` | string | `low` 实测可用；官方还有 `high`、`original`、`auto`，具体取决于模型 |
| `max_output_tokens` | integer | 限制回答长度和成本 |

## 10. 图像解释：Chat Completions API

Chat Completions 的图像输入格式和 Responses 不一样，要使用：

```json
{"type": "image_url", "image_url": {"url": "..."}}
```

当前部署实测结果：

| 模型 | 状态 | 结果 |
| --- | ---: | --- |
| `gpt-5.5` | 200 | 成功描述图片内容 |
| `gpt-5.4` | 200 | 成功描述图片内容 |
| `gpt-5.4-mini` | 200 | 成功描述图片内容 |
| `gpt-4.1-mini` | 400 | 返回 `model is not supported when using Codex with a ChatGPT account` |

示例：

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

### 10.1 Responses 和 Chat Completions 的图像输入差异

| API | 文本字段 | 图片字段 |
| --- | --- | --- |
| Responses API | `{"type":"input_text","text":"..."}` | `{"type":"input_image","image_url":"..."}` |
| Chat Completions API | `{"type":"text","text":"..."}` | `{"type":"image_url","image_url":{"url":"..."}}` |

不要混用，否则容易出现看似“模型不支持”或“图片无效”的错误。

## 11. 图像编辑和图像变体

| 端点 | 实测状态 | 说明 |
| --- | ---: | --- |
| `POST /v1/images/edits` | 400 | 路由存在，但本次只做了不完整 JSON 探测，返回 `images[].image_url is required`；还没有成功实测编辑 |
| `POST /v1/images/variations` | 404 | 当前部署不可用 |

因此：图像生成已经确认可用；图像解释已经确认可用；图像编辑暂时只能确认路由存在，不能确认完整可用。

## 12. 与 OpenAI 官方 API 的主要差异

这个部署只兼容 OpenAI API 的一部分，不是完整官方 API。

以下端点实测不可用或未实现：

| OpenAI 官方端点 | 当前状态 |
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

## 13. 错误格式差异

不要假设所有错误都是标准 OpenAI 格式。实测存在多种返回形态：

| 错误来源 | 返回形态 |
| --- | --- |
| 缺少或错误 API key | `{"code":"...","message":"..."}` |
| 请求体 JSON 错误 | `{"error":{"message":"Failed to parse request body","type":"invalid_request_error"}}` |
| 不存在的路由 | 纯文本 `404 page not found` |
| 上游或网关异常 | Cloudflare HTML 或 `error code: 502` |

客户端建议：

1. 先按 HTTP 状态码分类。
2. 再尝试解析 JSON。
3. JSON 解析失败时保留原始文本片段。
4. 对 502/503 做重试或降级，但不要无限重试。

## 14. 推荐接入配置

推荐默认配置：

```text
Base URL: https://api.perceptleap.com/v1
Auth: Authorization: Bearer $PERCEPTLEAP_API_KEY
User-Agent: curl/8.5.0 或你的应用名
```

推荐模型：

| 场景 | 推荐模型 |
| --- | --- |
| 低成本文本测试 | `gpt-5.4-mini` |
| 图像解释 | `gpt-5.4-mini` 或 `gpt-5.4` |
| 图像生成 | `gpt-image-2` |
| Responses 图像生成工具 | `gpt-5.4-mini` + `tools:[{"type":"image_generation"}]` |
| 需要更强能力 | `gpt-5.5` 或 `gpt-5.4` |

参数建议：

| 场景 | 建议 |
| --- | --- |
| Responses 文本 | 用 `max_output_tokens`，不要用 `max_tokens` |
| Chat Completions 文本 | 优先用 `max_completion_tokens` |
| 图像生成测试 | `quality: "low"`、`size: "1024x1024"`、`n: 1`、省略 `response_format` |
| 图像解释测试 | `detail: "low"`、`max_output_tokens: 80` 或 `max_completion_tokens: 80` |
| 临时测试 | `store: false` |

## 15. 可复用测试脚本和结果文件

| 文件 | 说明 |
| --- | --- |
| `perceptleap_probe_results.json` | 主兼容性测试结果 |
| `perceptleap_extra_results.json` | 鉴权、额外参数、retrieve 类接口测试结果 |
| `perceptleap_image_api_curl_results.json` | Images API 图像生成复测结果 |
| `perceptleap_responses_image_tool_curl_results.json` | Responses 图像生成工具复测结果 |
| `perceptleap_image_param_compat_results.json` | 图像生成参数兼容性专项测试结果 |
| `perceptleap_vision_curl_results.json` | 图像解释复测结果 |
| `probe_perceptleap.py` | 可复用 Python 探测脚本 |
| `run_probe_noecho.sh` | 安全读取 API Key 的包装脚本 |

重新运行完整探测：

```bash
./run_probe_noecho.sh
```

脚本会从标准输入读取 API Key，终端不回显 Key，并生成 JSON 和 Markdown 结果。

## 16. 最小可用清单

如果只想快速接入，按这个清单使用：

1. 文本生成：`POST /v1/responses`，模型 `gpt-5.4-mini`。
2. 旧项目兼容：`POST /v1/chat/completions`，模型 `gpt-5.4-mini`。
3. 图像生成：`POST /v1/images/generations`，模型 `gpt-image-2`。
4. 图像解释：`POST /v1/responses`，模型 `gpt-5.4-mini`，图片字段用 `input_image`。
5. 所有路径都带 `/v1`，不要用 `/chat/completions` 或 `/messages`。
