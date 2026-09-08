# Agnes AI API Reference

Base host: `https://apihub.agnes-ai.com`

Authentication: `Authorization: Bearer YOUR_API_KEY`

Content type: `application/json`

## Text

Endpoint: `POST /v1/chat/completions`

Model: `agnes-2.5-flash`

Required:

- `model`: fixed as `agnes-2.5-flash`
- `messages`: OpenAI-compatible chat messages

Optional:

- `temperature`: number
- `top_p`: number
- `max_tokens`: number
- `stream`: boolean
- `tools`: array
- `tool_choice`: string or object
- `chat_template_kwargs`: object, enables Thinking for OpenAI-compatible requests
- `thinking`: object, enables Thinking for Anthropic-compatible requests

The response is OpenAI-compatible and includes `choices[].message.content` and `usage`. Context window is 512K with a 65.5K max output. Messages can combine text and image URLs (`messages[].content[].image_url`) for multimodal understanding.

## Image

Endpoint: `POST /v1/images/generations`

Model: `agnes-image-2.5-flash`

Required:

- `model`: fixed as `agnes-image-2.5-flash`
- `prompt`: text instruction for image generation or editing
- `size`: output size tier such as `1K`, `2K`, `3K`, `4K`, or a legacy exact size such as `1024x768` (unsupported exact sizes may be normalized)

Optional:

- `ratio`: aspect ratio combined with a tier `size`. Supported: `1:1`, `3:4`, `4:3`, `16:9`, `9:16`, `2:3`, `3:2`, `21:9`. Default `1:1`.
- `image`: array of input image URLs or Data URI Base64 for image-to-image or multi-image synthesis
- `return_base64`: boolean, set to return Base64 data for text-to-image
- `extra_body.response_format`: `url` or `b64_json`

For predictable output sizes, combine `size` tier and `ratio`. For example, to produce common 16:9 display material at `1920x1080`/`2560x1440`, request `size: "2K"`, `ratio: "16:9"`, then crop or scale downstream.

Recommended size/ratio pairings (output pixels):

| Ratio | 1K        | 2K        | 3K        | 4K        |
| ----- | --------- | --------- | --------- | --------- |
| 1:1   | 1024x1024 | 2048x2048 | 3072x3072 | 4096x4096 |
| 3:4   | 864x1152  | 1728x2304 | 2592x3456 | 3456x4608 |
| 4:3   | 1152x864  | 2304x1728 | 3456x2592 | 4608x3456 |
| 16:9  | 1312x736  | 2624x1472 | 3936x2208 | 5248x2944 |
| 9:16  | 736x1312  | 1472x2624 | 2208x3936 | 2944x5248 |
| 2:3   | 832x1248  | 1664x2496 | 2496x3744 | 3328x4992 |
| 3:2   | 1248x832  | 2496x1664 | 3744x2496 | 4992x3328 |
| 21:9  | 1568x672  | 3136x1344 | 4704x2016 | 6272x2688 |

URL output is returned at `data[0].url`; Base64 output at `data[0].b64_json`.

Prompt structure:

`[Subject] + [Scene / Environment] + [Style] + [Lighting] + [Composition] + [Quality Requirements]`

For image-to-image, state what should change and what must remain unchanged.

For non-English user prompts, translate to English before sending the request. Preserve visual specifics and constraints.

## Video

Create task endpoint: `POST /v1/videos` (OpenAI Videos compatible)

Recommended result endpoint: `GET /agnesapi?video_id={video_id}&model_name=agnes-video-2.5-flash`

Legacy task endpoint: `GET /v1/videos/{task_id}` (fallback only)

Model: `agnes-video-2.5-flash`

The video API is asynchronous. Create a task, then retrieve or poll by the returned `video_id` plus `model_name=agnes-video-2.5-flash`. This is the recommended polling path for all modes (`text`, `keyframe`, `reference`). A bare `video_id` lookup without `model_name` only works for tasks created with `mode: "text"`.

The script defaults to `video_id + model_name` lookup and falls back to legacy `task_id` only when `video_id` is absent.

Use English prompts for video generation whenever possible. If the user prompt is not English, translate it to English first, preserving subject, action, scene, camera movement, lighting, style, and constraints. For `reference` mode, prompts can use `<Picture N>` and `<Audio N>` placeholders to refer to media.

### Common parameters

| Parameter      | Required | Description                                             |
| -------------- | -------- | ------------------------------------------------------- |
| `model`        | yes      | Fixed as `agnes-video-2.5-flash`.                       |
| `prompt`       | yes      | Video content description.                              |
| `mode`         | yes      | `text`, `keyframe`, or `reference`.                     |
| `seconds`      | no       | Video duration as a string `"4"`–`"12"`, default `"5"`. |
| `size`         | no       | Fixed to `"720P"`; any other value returns HTTP 400.    |
| `aspect_ratio` | no       | Default `16:9`. See aspect ratio table below.           |
| `seed`         | no       | Random seed.                                            |
| `n`            | no       | Only `1` is supported, default `1`.                     |

### Mode-specific parameters

| Parameter     | Type        | Mode          | Note                                               |
| ------------- | ----------- | ------------- | -------------------------------------------------- |
| `first_frame` | string      | keyframe      | First frame image URL; needs `last_frame` or not.  |
| `last_frame`  | string      | keyframe      | Last frame image URL; `first_frame`/`last_frame` at least one. |
| `images`      | string[]    | reference     | Reference image URLs, up to 5.                     |
| `audios`      | string[]    | reference     | Reference audio URLs, up to 3.                     |
| `videos`      | object[]    | reference     | Not supported by Flash; a valid value returns HTTP 400. |

### Mode rules

| mode      | Purpose                  | Required media                          | Disallowed media fields                                     |
| --------- | ------------------------ | --------------------------------------- | ----------------------------------------------------------- |
| `text`    | Text-to-video            | none                                    | `first_frame`, `last_frame`, `images`, `audios`, `videos`   |
| `keyframe`| First/last frame control | `first_frame` and/or `last_frame`       | `images`, `audios`, `videos`                                |
| `reference`| Image or audio reference | `images` or `audios` (at least one)     | `first_frame`, `last_frame`, `videos`                       |

In `reference` mode, `images` and `audios` can be used alone or together. All media URLs must be publicly accessible to the Agnes AI service and remain valid until the task completes.

### Aspect ratio → output pixels

| `size` | `aspect_ratio` | Output pixels |
| -----  | ------------- | ------------- |
| 720P   | 21:9          | 1680x720      |
| 720P   | 16:9          | 1280x704      |
| 720P   | 4:3           | 960x720       |
| 720P   | 1:1           | 720x720       |
| 720P   | 3:4           | 720x960       |
| 720P   | 9:16          | 720x1280      |

### Flash error order

When a request has multiple Flash parameter errors, the API returns the first detected error in the order `size`, `images`, `audios`, `videos`. All such responses are HTTP `400`.

Recommended defaults:

- Duration: `seconds="5"`, `n=1`, `size` fixed at `"720P"`.
- Reproducibility: set `seed`.
- Poll every 1–2 seconds until `status` is `completed` or `failed`.

Common status values:

- `queued`
- `in_progress`
- `completed`
- `failed`

The create response may include both `task_id` and `video_id`. The completed response usually includes a video URL, which may appear as `video_url`, `url`, or `remixed_from_video_id`. Results are free while the current limited-time promotion is active; billing is based on `$0` per second at 720P.

## Error Codes

- `400`: invalid request
- `401`: unauthorized; check API key
- `404`: task not found
- `500`: server error
- `503`: service busy; retry later
