---
name: Agnes2.5
description: Call Agnes AI / Sapiens AI generation APIs for text, image, and video. Use when the user asks to use Agnes models, Agnes Image, Agnes Video, Agnes 2.5 Flash, apihub.agnes-ai.com, or to generate text, images, edit images, create videos, animate images, create keyframe videos, or test Agnes API calls.
---

# Agnes AI Generation

Use this skill to call Agnes text, image, and video generation APIs through `https://apihub.agnes-ai.com`.

## Quick Start

1. Read `references/api.md` when endpoint details, parameters, or response fields are needed.
2. Use `scripts/agnes_api.py` for real API calls instead of rewriting curl by hand.
3. Require an API key in `AGNES_API_KEY`, `AGNES_API_TOKEN`, or `APIHUB_AGNES_API_KEY`. Never print the key.
4. For light live verification, run `smoke-test`; it avoids video creation by default. Add `--include-image-edit` for image-to-image, and add `--video-case <case>` explicitly for video modes. Treat the skill as fully tested only when basic text, text streaming, text tool calling, text-to-image, image-to-image, text-to-video, image-to-video, multi-image video, keyframe video, and video retrieval return successful responses.

## Commands

Text generation:

```bash
python scripts/agnes_api.py text --prompt "Write a concise product tagline for an AI assistant."
```

Streaming text:

```bash
python scripts/agnes_api.py text --prompt "Write a short product intro." --stream
```

Streaming output is normalized and includes aggregated `content`, `events`, `done`, and a short `raw_prefix`.

Image generation:

```bash
python scripts/agnes_api.py image --prompt "A luminous floating city above a misty canyon at sunrise, cinematic realism" --size 2K --ratio 16:9
```

Image-to-image:

```bash
python scripts/agnes_api.py image --prompt "Turn the scene into a rainy cyberpunk night while preserving composition" --image https://example.com/input.png --size 2K --ratio 16:9
```

Multi-image synthesis:

```bash
python scripts/agnes_api.py image --prompt "Merge these two styles into one cohesive scene" --image https://example.com/a.png --image https://example.com/b.png --size 2K --ratio 16:9
```

Text-to-video with polling:

```bash
python scripts/agnes_api.py video --prompt "A cinematic shot of a cat walking on the beach at sunset" --mode text --poll
```

Image-to-video (reference mode):

```bash
python scripts/agnes_api.py video --prompt "Animate subtle camera movement and natural lighting" --mode reference --images https://example.com/image.png --poll
```

Keyframe (first/last frame) video:

```bash
python scripts/agnes_api.py video --prompt "Create a smooth cinematic transition between the two keyframes" --mode keyframe --first-frame https://example.com/a.png --last-frame https://example.com/b.png --poll
```

Multi-image reference video:

```bash
python scripts/agnes_api.py video --prompt "Blend the visual style of these reference images into one cohesive video" --mode reference --images https://example.com/a.png --images https://example.com/b.png --poll
```

Retrieve a video task:

```bash
python scripts/agnes_api.py video-get video_123456
```

Light live smoke test:

```bash
python scripts/agnes_api.py smoke-test
```

Image edit smoke test:

```bash
python scripts/agnes_api.py smoke-test --include-image-edit
```

Single video smoke test:

```bash
python scripts/agnes_api.py smoke-test --video-case text-to-video
```

## Workflow

- Prefer `agnes-2.5-flash` for text chat/completions. It is fully compatible with the old `agnes-2.0-flash` request shape (endpoint, messages, streaming, tools, and image-URL input are unchanged); only the `model` value differs.
- Do not use Agnes Responses API multi-turn function calling for autonomous tool workflows. Live testing showed the provider can return `function_call` with overall `status=completed`, and submitting `function_call_output` with `previous_response_id` may fail. Use this skill's chat completions path for text generation and treat tool-calling as best-effort request-shape compatibility only.
- Prefer `agnes-image-2.5-flash` for text-to-image, image-to-image, multi-image synthesis, and high-information-density image generation. Use tier `--size` (1K/2K/3K/4K) with `--ratio` for predictable output pixels, e.g. `--size 2K --ratio 16:9`. High-density generation is prompt-driven; include subject hierarchy, environment, secondary details, lighting, composition, and quality requirements.
- Prefer `agnes-video-2.5-flash` for text-to-video, keyframe (first/last frame) animation, and reference-based (image/audio) generation. The API is OpenAI Videos compatible. `mode` takes `text`, `keyframe` (uses `--first-frame`/`--last-frame`), or `reference` (uses `--images` up to 5 / `--audios` up to 3). Output `size` is fixed at `"720P"`, chosen via `--aspect-ratio`.
- For image and video generation, convert any non-English user prompt to a fluent English generation prompt before calling the image/video API. English prompts are more stable for Agnes video generation. Preserve concrete visual details, style, lighting, composition, motion, camera instructions, and constraints during translation.
- For videos, remember the API is asynchronous: create a task first, then poll or retrieve by `video_id` with `model_name=agnes-video-2.5-flash`. The script falls back to legacy `task_id` lookup only when `video_id` is absent.
- Agnes Video 2.5 Flash validates requests in this order: `size` (must be `"720P"`), `images` (max 5), `audios` (max 3), `videos` (not supported). `seconds` must be a string `"4"`–`"12"` and `n` is fixed at `1`.
- The video command defaults to `mode=text` and `seconds="5"`. Poll every 1–2 seconds once a task is created.
- Warn the user before costly or long-running live video generation unless they explicitly asked to test or generate video.
- Test video capabilities one at a time with `smoke-test --video-case <case>` to avoid creating many tasks at once. Supported cases are `text-to-video`, `image-to-video`, `multi-image`, and `keyframes`.

## Current Validation Notes

- Confirmed locally: skill metadata validation and Python syntax.
- Confirmed by live API: basic text, streaming text, tool-calling request shape, text-to-image, image-to-image, high-information-density text-to-image, Chinese prompt translation for image/video, completed text-to-video URL retrieval, and completed image-to-video URL retrieval.
- Caveat: Agnes may accept tool-calling request parameters without consistently returning `tool_calls`; use `smoke-test --strict-tools` when strict tool-call validation is required.
- Caveat: Agnes Responses API multi-turn function calling is not reliable for agent tool loops; do not rely on it for Codex/Claude-style automatic tool continuation.
- Supported by the script and smoke-test selector, but not re-run end-to-end in the latest pass: multi-image video and keyframe animation.
- Not yet confirmed end-to-end: completed URL retrieval for every multi-image video and keyframe animation task. A previous text-to-video task returned a provider-side `division by zero` error, so keep video retries visible and report provider errors clearly.

## Output Handling

- Return generated image/video URLs directly by default. Do not download, save, open, or inspect generated media unless the user explicitly asks for a local file or visual inspection.
- For image responses, expect URL-style results when `extra_body.response_format` is `url`.
- For video responses, extract URLs from `video_url`, `url`, or `remixed_from_video_id` when `status` is `completed`.
- For video retrieval, prefer `GET /agnesapi?video_id=...&model_name=agnes-video-2.5-flash`; legacy `GET /v1/videos/{task_id}` remains a fallback.
- If a request fails, report HTTP status and provider error body without exposing the API key.
