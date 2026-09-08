#!/usr/bin/env python3
"""Small CLI for Agnes AI text, image, and video generation APIs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "https://apihub.agnes-ai.com"
TEXT_MODEL = "agnes-2.5-flash"
IMAGE_MODEL = "agnes-image-2.5-flash"
VIDEO_MODEL = "agnes-video-2.5-flash"
SIZE_RE = re.compile(r"^[1-9]\d*x[1-9]\d*$")
TIER_RE = re.compile(r"^[1-4]K$")
RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9")


def get_api_key() -> str:
    for name in ("AGNES_API_KEY", "AGNES_API_TOKEN", "APIHUB_AGNES_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value
    raise SystemExit(
        "Missing API key. Set AGNES_API_KEY, AGNES_API_TOKEN, or APIHUB_AGNES_API_KEY."
    )


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed for {path}: {exc}") from exc


def request_text(method: str, path: str, payload: dict[str, Any] | None = None) -> str:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed for {path}: {exc}") from exc


def stream_summary(payload: dict[str, Any]) -> dict[str, Any]:
    raw = request_text("POST", "/v1/chat/completions", payload)
    event_count = 0
    done = False
    content_parts: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            done = True
        elif data:
            event_count += 1
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            try:
                delta = event["choices"][0].get("delta", {})
            except (KeyError, IndexError, TypeError, AttributeError):
                continue
            content = delta.get("content")
            if isinstance(content, str):
                content_parts.append(content)
    return {
        "type": "text-stream",
        "content": "".join(content_parts) or None,
        "events": event_count,
        "done": done,
        "raw_prefix": raw[:200],
    }


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def parse_json_arg(name: str, value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON for {name}: {exc.msg} at position {exc.pos}") from exc


def needs_english_translation(prompt: str) -> bool:
    return any(ord(ch) > 127 for ch in prompt)


def translate_prompt_to_english(prompt: str) -> str:
    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Translate the user's image/video generation prompt into fluent English. "
                    "Preserve all concrete visual details, style words, camera motion, lighting, "
                    "composition constraints, and negative instructions. Return only the English prompt."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 800,
    }
    data = request_json("POST", "/v1/chat/completions", payload)
    try:
        translated = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Prompt translation failed: {json.dumps(data, ensure_ascii=False)}") from exc
    if not translated:
        raise SystemExit("Prompt translation failed: empty translated prompt")
    return translated


def prepare_generation_prompt(prompt: str, translate: bool = True) -> tuple[str, str | None]:
    if translate and needs_english_translation(prompt):
        translated = translate_prompt_to_english(prompt)
        return translated, translated
    return prompt, None


def extract_text_content(data: dict[str, Any]) -> str | None:
    try:
        content = data["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    return content if isinstance(content, str) else None


def output_result(
    result_type: str,
    raw: dict[str, Any],
    *,
    prompt_used: str | None = None,
    translated_prompt: str | None = None,
    urls: list[str] | None = None,
    status: str | None = None,
    next_steps: list[str] | None = None,
    raw_only: bool = False,
) -> None:
    if raw_only:
        print_json(raw)
        return
    summary: dict[str, Any] = {"type": result_type}
    if status:
        summary["status"] = status
    if urls:
        summary["urls"] = urls
    if prompt_used:
        summary["prompt_used"] = prompt_used
    if translated_prompt:
        summary["translated_prompt"] = translated_prompt
    if next_steps:
        summary["next_steps"] = next_steps
    summary["raw"] = raw
    print_json(summary)


def extract_image_urls(data: dict[str, Any]) -> list[str]:
    urls = []
    if isinstance(data.get("url"), str):
        urls.append(data["url"])
    if isinstance(data.get("image_url"), str):
        urls.append(data["image_url"])
    if isinstance(data.get("data"), list):
        for item in data["data"]:
            if isinstance(item, dict):
                for key in ("url", "image_url"):
                    if isinstance(item.get(key), str):
                        urls.append(item[key])
    return urls


def extract_video_urls(data: dict[str, Any]) -> list[str]:
    urls = []
    for key in ("video_url", "url", "remixed_from_video_id"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            urls.append(value)
    if isinstance(data.get("data"), list):
        for item in data["data"]:
            if isinstance(item, dict):
                urls.extend(extract_video_urls(item))
    return list(dict.fromkeys(urls))


def video_lookup_id(data: dict[str, Any]) -> tuple[str | None, str | None]:
    video_id = data.get("video_id")
    if isinstance(video_id, str) and video_id:
        return video_id, "video_id"
    for key in ("task_id", "id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value, "task_id"
    return None, None


def retrieve_video(identifier: str, model_name: str | None = VIDEO_MODEL) -> dict[str, Any]:
    if identifier.startswith("video_"):
        query = {"video_id": identifier}
        if model_name:
            query["model_name"] = model_name
        return request_json("GET", "/agnesapi?" + urllib.parse.urlencode(query))
    return request_json("GET", f"/v1/videos/{urllib.parse.quote(identifier, safe='')}")


def validate_size(value: str | None, name: str = "size") -> None:
    if not value:
        return
    if TIER_RE.match(value):
        return
    if SIZE_RE.match(value):
        return
    raise SystemExit(
        f"Invalid {name}: {value}. Expected a tier such as 1K/2K/3K/4K, or WIDTHxHEIGHT such as 1024x768."
    )


def validate_video_args(args: argparse.Namespace) -> None:
    seconds = getattr(args, "seconds", None)
    if seconds is not None:
        check = str(seconds)
        try:
            n = int(check)
        except ValueError:
            raise SystemExit(f"Invalid --seconds: {seconds!r}. Agnes Video 2.5 Flash expects a string \"4\"-\"12\".")
        if not (4 <= n <= 12):
            raise SystemExit(f"Invalid --seconds: {check}. Agnes Video 2.5 Flash supports \"4\"-\"12\".")
    size = getattr(args, "size", None)
    if size is not None and str(size) != "720P":
        raise SystemExit(f"Invalid --size: {size}. Agnes Video 2.5 Flash only supports \"720P\".")
    images = getattr(args, "images", None) or []
    if len(images) > 5:
        raise SystemExit("Invalid --images: Agnes Video 2.5 Flash supports at most 5 reference images.")
    audios = getattr(args, "audios", None) or []
    if len(audios) > 3:
        raise SystemExit("Invalid --audios: Agnes Video 2.5 Flash supports at most 3 reference audios.")
    n_value = getattr(args, "n", None)
    if n_value is not None and n_value != 1:
        raise SystemExit("Invalid --n: Agnes Video 2.5 Flash only supports n=1.")


def cmd_text(args: argparse.Namespace) -> None:
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.prompt})
    payload: dict[str, Any] = {
        "model": TEXT_MODEL,
        "messages": messages,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    if args.top_p is not None:
        payload["top_p"] = args.top_p
    if args.stream:
        payload["stream"] = True
    if args.tools_json:
        payload["tools"] = parse_json_arg("--tools-json", args.tools_json)
    if args.tool_choice_json:
        payload["tool_choice"] = parse_json_arg("--tool-choice-json", args.tool_choice_json)
    if args.stream:
        print_json(stream_summary(payload))
    else:
        data = request_json("POST", "/v1/chat/completions", payload)
        content = extract_text_content(data)
        wrapped = {
            "type": "text",
            "content": content,
            "raw": data,
        }
        print_json(data if args.raw else wrapped)


def cmd_image(args: argparse.Namespace) -> None:
    validate_size(args.size)
    if args.ratio and args.ratio not in RATIOS:
        raise SystemExit(f"Invalid --ratio: {args.ratio}. Supported values are {', '.join(RATIOS)}.")
    prompt, translated_prompt = prepare_generation_prompt(args.prompt, not args.no_translate_prompt)
    payload: dict[str, Any] = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
    }
    if args.size:
        payload["size"] = args.size
    if args.ratio:
        payload["ratio"] = args.ratio
    if args.image:
        payload["image"] = args.image
    if args.return_base64:
        payload["extra_body"] = {"response_format": "b64_json"}
    else:
        payload["extra_body"] = {"response_format": "url"}
    data = request_json("POST", "/v1/images/generations", payload)
    urls = extract_image_urls(data)
    output_result(
        "image-to-image" if args.image else "text-to-image",
        data,
        prompt_used=prompt,
        translated_prompt=translated_prompt,
        urls=urls,
        raw_only=args.raw,
    )


def video_payload(args: argparse.Namespace) -> dict[str, Any]:
    validate_video_args(args)
    prompt, translated_prompt = prepare_generation_prompt(args.prompt, not args.no_translate_prompt)
    args._prompt_used = prompt
    args._translated_prompt = translated_prompt
    mode = getattr(args, "mode", "text") or "text"
    payload: dict[str, Any] = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "mode": mode,
    }
    for name in ("seconds", "size", "aspect_ratio", "seed", "n"):
        value = getattr(args, name)
        if value is not None:
            payload[name] = value
    if mode == "keyframe":
        media: dict[str, Any] = {}
        if getattr(args, "first_frame", None):
            media["first_frame"] = args.first_frame
        if getattr(args, "last_frame", None):
            media["last_frame"] = args.last_frame
        if not media:
            raise SystemExit("--mode keyframe requires --first-frame and/or --last-frame.")
        payload.update(media)
    elif mode == "reference":
        if getattr(args, "images", None):
            payload["images"] = args.images
        if getattr(args, "audios", None):
            payload["audios"] = args.audios
        if "images" not in payload and "audios" not in payload:
            raise SystemExit("--mode reference requires --images and/or --audios.")
    return payload


def poll_video(identifier: str, timeout: int, interval: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = retrieve_video(identifier)
        if last.get("error"):
            raise SystemExit(f"Video {identifier} returned error: {json.dumps(last, ensure_ascii=False)}")
        status = str(last.get("status", "")).lower()
        progress = last.get("progress")
        if status:
            print(f"video {identifier}: status={status} progress={progress}", file=sys.stderr)
        if status in {"completed", "failed"}:
            return last
        time.sleep(interval)
    raise SystemExit(f"Timed out waiting for video {identifier}. Last response: {json.dumps(last)}")


def cmd_video(args: argparse.Namespace) -> None:
    created = request_json("POST", "/v1/videos", video_payload(args))
    if not args.poll:
        identifier, id_kind = video_lookup_id(created)
        next_steps = []
        if identifier:
            next_steps.append(f"python scripts/agnes_api.py video-get {identifier}")
            next_steps.append(f"python scripts/agnes_api.py video-get {identifier}  # repeat until status is completed")
        output_result(
            "video-task",
            created,
            prompt_used=getattr(args, "_prompt_used", None),
            translated_prompt=getattr(args, "_translated_prompt", None),
            status=str(created.get("status", "")) if created.get("status") is not None else None,
            next_steps=next_steps,
            raw_only=args.raw,
        )
        if id_kind == "task_id":
            print("warning: create response did not include video_id; falling back to legacy task_id lookup", file=sys.stderr)
        return
    identifier, id_kind = video_lookup_id(created)
    if not identifier:
        raise SystemExit(f"Video create response did not include video_id, task_id, or id: {json.dumps(created)}")
    if id_kind == "task_id":
        print("warning: create response did not include video_id; falling back to legacy task_id lookup", file=sys.stderr)
    data = poll_video(identifier, args.timeout, args.interval)
    urls = extract_video_urls(data)
    output_result(
        "video-result",
        data,
        prompt_used=getattr(args, "_prompt_used", None),
        translated_prompt=getattr(args, "_translated_prompt", None),
        urls=urls,
        status=str(data.get("status", "")) if data.get("status") is not None else None,
        raw_only=args.raw,
    )


def cmd_video_get(args: argparse.Namespace) -> None:
    data = retrieve_video(args.identifier, None if args.no_model_name else args.model_name)
    urls = extract_video_urls(data)
    output_result(
        "video-result",
        data,
        urls=urls,
        status=str(data.get("status", "")) if data.get("status") is not None else None,
        next_steps=[] if urls else [f"python scripts/agnes_api.py video-get {args.identifier}"],
        raw_only=args.raw,
    )
    if data.get("error"):
        raise SystemExit(1)


def require_ok(name: str, data: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise SystemExit(f"{name} response missing {missing}: {json.dumps(data)}")
    print(f"{name}: ok")


def require_video_ok(name: str, data: dict[str, Any], completed: bool = False) -> None:
    require_ok(name, data, ("id", "status"))
    if data.get("error"):
        raise SystemExit(f"{name} returned error: {json.dumps(data, ensure_ascii=False)}")
    status = str(data.get("status", "")).lower()
    if status == "failed":
        raise SystemExit(f"{name} failed: {json.dumps(data, ensure_ascii=False)}")
    if completed and status != "completed":
        raise SystemExit(f"{name} did not complete: {json.dumps(data, ensure_ascii=False)}")
    if completed and not extract_video_urls(data):
        raise SystemExit(f"{name} completed without a video URL: {json.dumps(data, ensure_ascii=False)}")


def check_tool_call(name: str, data: dict[str, Any], strict: bool = False) -> None:
    try:
        tool_calls = data["choices"][0]["message"].get("tool_calls")
    except (KeyError, IndexError, TypeError, AttributeError):
        tool_calls = None
    if not tool_calls:
        message = f"{name}: request accepted, but response did not include tool_calls"
        if strict:
            raise SystemExit(f"{message}: {json.dumps(data, ensure_ascii=False)}")
        print(message, file=sys.stderr)
        return
    print(f"{name}: ok")


def extract_image_url(data: dict[str, Any]) -> str:
    candidates = extract_image_urls(data)
    if not candidates:
        raise SystemExit(f"Could not find image URL in response: {json.dumps(data, ensure_ascii=False)}")
    return candidates[0]


def create_video_case(name: str, payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    created = request_json("POST", "/v1/videos", payload)
    require_video_ok(f"{name}-create", created)
    identifier, id_kind = video_lookup_id(created)
    if not identifier:
        raise SystemExit(f"{name}-create response missing video_id/task_id/id: {json.dumps(created, ensure_ascii=False)}")
    if id_kind == "task_id":
        print(f"{name}-create: warning: falling back to legacy task_id lookup", file=sys.stderr)
    retrieved = (
        poll_video(identifier, args.video_timeout, args.video_interval)
        if args.poll_video
        else retrieve_video(identifier)
    )
    require_video_ok(f"{name}-get", retrieved, completed=args.poll_video)
    return {"create": created, "get": retrieved}


VIDEO_CASES = ("text-to-video", "image-to-video", "multi-image", "keyframes")


def cmd_smoke_test(args: argparse.Namespace) -> None:
    validate_size(args.image_size, "image-size")
    validate_video_args(
        argparse.Namespace(
            seconds=args.video_seconds,
            size=args.video_size,
            n=args.video_n,
            images=None,
            audios=None,
        )
    )
    text = request_json(
        "POST",
        "/v1/chat/completions",
        {
            "model": TEXT_MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: Agnes text ok"}],
            "max_tokens": 20,
            "temperature": 0,
        },
    )
    require_ok("text", text, ("choices",))

    text_stream = stream_summary(
        {
            "model": TEXT_MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: Agnes stream ok"}],
            "max_tokens": 20,
            "temperature": 0,
            "stream": True,
        }
    )
    if text_stream["events"] < 1 and not text_stream["done"]:
        raise SystemExit(f"text-stream response did not look like SSE: {json.dumps(text_stream)}")
    print("text-stream: ok")

    text_tools = request_json(
        "POST",
        "/v1/chat/completions",
        {
            "model": TEXT_MODEL,
            "messages": [{"role": "user", "content": "Use the get_test_value tool."}],
            "max_tokens": 128,
            "temperature": 0,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_test_value",
                        "description": "Return a deterministic smoke test value.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "test label"}
                            },
                            "required": ["label"],
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "get_test_value"}},
        },
    )
    check_tool_call("text-tools", text_tools, strict=args.strict_tools)

    image_text = request_json(
        "POST",
        "/v1/images/generations",
        {
            "model": IMAGE_MODEL,
            "prompt": "A simple red square icon centered on a white background",
            "size": args.image_size,
            "extra_body": {"response_format": "url"},
        },
    )
    require_ok("image-text-to-image", image_text, ("data",))
    generated_image_url = extract_image_url(image_text)

    image_edit = None
    edited_image_url = None
    selected_cases = set(args.video_case or [])
    needs_second_image = bool(selected_cases.intersection({"multi-image", "keyframes"}))
    if args.include_image_edit or needs_second_image:
        image_edit = request_json(
            "POST",
            "/v1/images/generations",
            {
                "model": IMAGE_MODEL,
                "prompt": "Turn this into a clean blue square icon while preserving the centered composition",
                "size": args.image_size,
                "image": [generated_image_url],
                "extra_body": {"response_format": "url"},
            },
        )
        require_ok("image-to-image", image_edit, ("data",))
        edited_image_url = extract_image_url(image_edit)

    video_common = {
        "model": VIDEO_MODEL,
    }
    for key, value in (("seconds", args.video_seconds), ("size", args.video_size)):
        if value is not None:
            video_common[key] = value
    video_results = {}
    if "text-to-video" in selected_cases:
        video_results["text_to_video"] = create_video_case(
            "video-text-to-video",
            {
                **video_common,
                "mode": "text",
                "prompt": "A simple cinematic shot of a red square gently moving on a white background",
            },
            args,
        )
    if "image-to-video" in selected_cases:
        video_results["image_to_video"] = create_video_case(
            "video-image-to-video",
            {
                **video_common,
                "mode": "reference",
                "prompt": "Animate the icon with subtle floating motion, stable centered composition",
                "images": [generated_image_url],
            },
            args,
        )
    if "multi-image" in selected_cases:
        if not edited_image_url:
            raise SystemExit("multi-image test requires an edited image URL")
        video_results["multi_image"] = create_video_case(
            "video-multi-image",
            {
                **video_common,
                "mode": "reference",
                "prompt": "Create a smooth transformation from the first icon to the second icon, stable centered composition",
                "images": [generated_image_url, edited_image_url],
            },
            args,
        )
    if "keyframes" in selected_cases:
        if not edited_image_url:
            raise SystemExit("keyframes test requires an edited image URL")
        video_results["keyframes"] = create_video_case(
            "video-keyframes",
            {
                **video_common,
                "mode": "keyframe",
                "prompt": "Create a smooth keyframe transition between the two icons, stable centered composition",
                "first_frame": generated_image_url,
                "last_frame": edited_image_url,
            },
            args,
        )
    print_json(
        {
            "text": text,
            "text_stream": text_stream,
            "text_tools": text_tools,
            "image_text_to_image": image_text,
            "image_to_image": image_edit,
            "video": video_results,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Agnes AI generation APIs.")
    sub = parser.add_subparsers(dest="command", required=True)

    text = sub.add_parser("text", help="Create a chat completion.")
    text.add_argument("--prompt", required=True)
    text.add_argument("--system")
    text.add_argument("--temperature", type=float, default=0.7)
    text.add_argument("--top-p", type=float)
    text.add_argument("--max-tokens", type=int, default=1024)
    text.add_argument("--stream", action="store_true")
    text.add_argument("--tools-json", help="JSON array for OpenAI-compatible tool definitions.")
    text.add_argument("--tool-choice-json", help="JSON object/string for OpenAI-compatible tool_choice.")
    text.add_argument("--raw", action="store_true", help="Print the raw provider response.")
    text.set_defaults(func=cmd_text)

    image = sub.add_parser("image", help="Generate or edit an image with Agnes Image 2.5 Flash.")
    image.add_argument("--prompt", required=True)
    image.add_argument("--size", default="1024x768", help="Output size tier (1K/2K/3K/4K) or WIDTHxHEIGHT such as 1024x768.")
    image.add_argument(
        "--ratio",
        choices=RATIOS,
        help="Aspect ratio combined with a tier-size, e.g. --size 2K --ratio 16:9. Default 1:1.",
    )
    image.add_argument("--image", action="append", help="Input image URL or Data URI. Repeat for multi-image synthesis.")
    image.add_argument("--return-base64", action="store_true", help="Return Base64 data instead of a URL.")
    image.add_argument(
        "--no-translate-prompt",
        action="store_true",
        help="Do not translate non-English prompts before sending to the image API.",
    )
    image.add_argument("--raw", action="store_true", help="Print the raw provider response.")
    image.set_defaults(func=cmd_image)

    video = sub.add_parser("video", help="Create a video task with Agnes Video 2.5 Flash.")
    video.add_argument("--prompt", required=True)
    video.add_argument(
        "--mode",
        choices=("text", "keyframe", "reference"),
        default="text",
        help="Generation mode: text, keyframe (first/last frame), or reference (images/audios).",
    )
    video.add_argument("--seconds", help="Video duration as a string, \"4\"-\"12\". Default \"5\".")
    video.add_argument("--size", help="Only \"720P\" is supported by Agnes Video 2.5 Flash.")
    video.add_argument(
        "--aspect-ratio",
        choices=("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        help="Output aspect ratio. Default 16:9.",
    )
    video.add_argument("--seed", type=int, help="Random seed for reproducibility.")
    video.add_argument("--n", type=int, help="Only 1 is supported.")
    video.add_argument("--first-frame", help="First frame image URL for keyframe mode.")
    video.add_argument("--last-frame", help="Last frame image URL for keyframe mode.")
    video.add_argument(
        "--images",
        action="append",
        help="Reference image URL for reference mode. Repeat up to 5 times.",
    )
    video.add_argument(
        "--audios",
        action="append",
        help="Reference audio URL for reference mode. Repeat up to 3 times.",
    )
    video.add_argument(
        "--no-translate-prompt",
        action="store_true",
        help="Do not translate non-English prompts before sending to the video API.",
    )
    video.add_argument("--poll", action="store_true")
    video.add_argument("--timeout", type=int, default=900)
    video.add_argument("--interval", type=int, default=10)
    video.add_argument("--raw", action="store_true", help="Print the raw provider response.")
    video.set_defaults(func=cmd_video)

    video_get = sub.add_parser("video-get", help="Retrieve a video result by video_id, or by legacy task_id.")
    video_get.add_argument("identifier", help="Prefer video_id. Legacy task_id is still accepted.")
    video_get.add_argument("--model-name", default=VIDEO_MODEL, help="Model name for video_id result lookup.")
    video_get.add_argument("--no-model-name", action="store_true", help="Do not pass model_name for video_id lookup.")
    video_get.add_argument("--raw", action="store_true", help="Print the raw provider response.")
    video_get.set_defaults(func=cmd_video_get)

    smoke = sub.add_parser("smoke-test", help="Run live text, image, and video API tests.")
    smoke.add_argument("--image-size", default="1024x768")
    smoke.add_argument("--video-seconds", default=None, help="Video duration string \"4\"-\"12\".")
    smoke.add_argument("--video-size", default=None, help="Fixed to \"720P\" for Agnes Video 2.5 Flash.")
    smoke.add_argument("--video-n", type=int, default=None, help="Only 1 is supported.")
    smoke.add_argument("--include-image-edit", action="store_true", help="Also test image-to-image editing.")
    smoke.add_argument("--strict-tools", action="store_true", help="Fail if the tool-calling response has no tool_calls.")
    smoke.add_argument("--poll-video", action="store_true")
    smoke.add_argument("--video-timeout", type=int, default=900)
    smoke.add_argument("--video-interval", type=int, default=10)
    smoke.add_argument(
        "--video-case",
        action="append",
        choices=VIDEO_CASES,
        help="Video case to test. Repeat to test multiple cases. Omit to skip video creation.",
    )
    smoke.set_defaults(func=cmd_smoke_test)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
