# meetdown

`meetdown` is a small Python CLI for turning meeting audio into a Markdown transcript.

The CLI sends a local audio or video file to a speech provider, normalizes the
response, and writes a `.md` file with the full text and speaker-by-speaker
transcript when the provider returns speaker information. When `--provider` is
omitted, meetdown uses `MEETDOWN_PROVIDER`, or the only provider with configured
credentials. Recordings longer than a provider's request limit are split
automatically, and each transcript gets a quick quality check for common
speech-recognition hallucinations.

## Install and run

Run it directly with `uvx`; cloning this repository is not required:

```powershell
uvx meetdown meeting.m4a -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key"
```

Use the optional Notion extra when you want meetdown to upload the saved
Markdown file to Notion:

```powershell
uvx "meetdown[notion]" transcribe meeting.m4a -o meeting.md --notion
```

For local development:

```powershell
uv run meetdown meeting.m4a -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key"
```

Set credentials with environment variables:

```powershell
$env:CLOVA_SPEECH_INVOKE_URL="https://your.invoke.url"
$env:CLOVA_SPEECH_SECRET_KEY="your-secret-key"
```

You can also pass them directly:

```powershell
uvx meetdown meeting.m4a -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key"
```

Run `meetdown` without arguments, or use `--help`, to see the command list
without transcribing anything. Use `quickstart` for examples and `defaults` for
the current provider auto-detection status. In interactive terminals, the
defaults view is color-coded by area; set `NO_COLOR=1` to keep plain text
output.

```powershell
uvx meetdown
uvx meetdown --help
uvx meetdown quickstart
uvx meetdown defaults
uvx meetdown transcribe --help
```

Recognition language defaults to `auto`, so meetdown does not force a single
language when audio contains a mix such as English and Korean. Pass
`--language ko-KR`, `--language en-US`, or another provider-supported language
when you want to bias recognition toward one language. CLOVA Speech requires a
concrete language, so meetdown sends `ko-KR` for CLOVA when `--language auto` is
used; aliases such as `ko` and `ko-kr` are normalized to `ko-KR`.

## Python API

Use the top-level package API when you want to call meetdown from Python instead
of shelling out to the CLI:

```python
from meetdown import render_markdown, transcribe_file, write_markdown

response = transcribe_file("meeting.m4a", provider="openai")
markdown = render_markdown(
    response,
    title="Weekly sync",
    source_path="meeting.m4a",
)
write_markdown("meeting.md", markdown)
```

`transcribe_file` uses the same provider resolution rules as the CLI. For more
control, import `resolve_provider_config` and `transcribe_with_provider` from
`meetdown` and keep the provider config in your own application code.

## Notion upload

Notion upload is optional. Install or run meetdown with the `notion` extra, then
set the Notion destination in environment variables:

```powershell
$env:NOTION_TOKEN="secret_..."
$env:NOTION_PARENT_PAGE_ID="your-parent-page-id"
uvx "meetdown[notion]" transcribe meeting.m4a -o meeting.md --notion
```

When `--notion` is used, meetdown checks for the optional dependency,
`NOTION_TOKEN`, and a parent page ID before transcription starts. The Markdown
file is still written first; Notion upload runs only after the local file is
saved. When Notion returns a page URL, meetdown prints it after upload.

You can override the Notion page settings per run:

```powershell
uvx "meetdown[notion]" transcribe meeting.m4a -o meeting.md --notion --notion-parent-page-id "page-id" --notion-title "Weekly sync" --notion-duplicate-strategy timestamp
```

## Providers

If `--provider` is omitted, meetdown uses the provider named in
`MEETDOWN_PROVIDER`. Without it, meetdown picks a provider only when exactly one
provider-specific API key is configured. When several provider keys are present
and no default is set, meetdown stops and lists them instead of guessing:

```powershell
$env:MEETDOWN_PROVIDER="openai"   # clova, openai, or gemini
uvx meetdown meeting.m4a -o meeting.md
```

Pass `--provider` explicitly to override the default for one run, or when you
pass only a generic `--api-key` or `MEETDOWN_API_KEY`.

CLOVA Speech can be selected automatically when you provide a CLOVA Invoke URL
and key:

```powershell
uvx meetdown meeting.m4a -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key"
```

For CLOVA, `--api-url` is the CLOVA Speech Invoke URL from NAVER Cloud Platform.
You may pass either the base Invoke URL or a URL that already ends with
`/recognizer/upload`.

OpenAI and Gemini can be selected automatically from their provider-specific
environment variables. Use `--api-url` when you need to override the provider
endpoint or base URL:

```powershell
$env:OPENAI_API_KEY="your-openai-key"
uvx meetdown meeting.m4a -o meeting.md
uvx meetdown meeting.m4a -o meeting.md --provider openai --api-url "https://api.openai.com/v1"

$env:GEMINI_API_KEY="your-gemini-key"
uvx meetdown meeting.m4a -o meeting.md
```

Use `--model` to override the provider default model. CLOVA does not support
`--model`; the CLOVA Speech model is determined by the Invoke URL/domain.
OpenAI defaults to a diarization-capable transcription model when diarization is
enabled, and to a smaller transcription model when `--no-diarization` is used.
Gemini uses inline audio requests, so larger files are split automatically.

## Chunk long recordings

meetdown checks the selected media length before uploading. When it would come
within 10% of one request's limit, the recording is split automatically:

| Provider | Limit per request | Automatic chunk length |
| --- | --- | --- |
| OpenAI | 1400 s of audio (diarization models) and 25 MB | 10 minutes |
| Gemini | about 19 MB of inline audio | up to 20 minutes |
| CLOVA Speech | no client-side limit | not split |

If a provider still rejects the whole file as too long or too large, meetdown
retries once in 10-minute chunks. Pass `--chunk-duration` to choose the chunk
length yourself, or `--no-auto-chunk` to send the file as one request. Speaker
labels restart in each chunk, so the same label in two chunks may be two
different people.

The CLI extracts audio chunks with `ffmpeg`, sends each chunk to the selected provider,
shifts segment timestamps back to the original file timeline, and writes one Markdown file.
If your PC does not have system `ffmpeg`, meetdown falls back to the bundled
`imageio-ffmpeg` executable installed with the package. If system `ffprobe` is
missing, meetdown reads duration metadata through ffmpeg instead.

```powershell
uvx meetdown meeting.mp4 -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key" --chunk-duration 10m
```

Accepted duration forms include `600`, `600s`, `10m`, and `1h`. Uploads default
to `--compress smallest`, which extracts audio and uploads a 64 kbps MP3 copy.
Use `--compress lossless` for FLAC or `--compress none` to avoid compression.
When chunking or range extraction is used, `--compress none` creates WAV chunks:

```powershell
uvx meetdown meeting.mp4 -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key" --chunk-duration 10m --compress lossless
uvx meetdown meeting.mp4 -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key" --chunk-duration 10m --compress none
```

You can still force the exact temporary upload format with `--chunk-format mp3`,
`--chunk-format flac`, or `--chunk-format wav`.

You can transcribe only part of the source file. Timestamps in the Markdown stay
on the original media timeline:

```powershell
uvx meetdown meeting.mp4 -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key" --start 10m --end 45m
uvx meetdown meeting.mp4 -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key" --start 00:10:00 --end 00:45:00 --chunk-duration 10m
```

## Offline conversion

If you already have a CLOVA Speech JSON response, convert it without calling the API:

```powershell
uvx meetdown --from-json examples/clova_response.sample.json -o sample.md --title "Sample Meeting"
```

After an API-backed transcription, generated Markdown includes a `Processing options` section
with the provider, model, language, compression, chunking, range, timeout settings, estimated
API cost, and a replay command for the run. The CLI prints the same cost estimate. OpenAI estimates use
provider-reported token usage when available and otherwise use the published estimated
per-minute rate. Gemini estimates use provider-reported modality token usage for the standard
paid tier. CLOVA estimates include base speech recognition at 5 KRW per 15-second request unit;
speaker diarization and other optional feature charges are not included.

Rates are maintained as dated list prices, with the pricing date and source saved alongside the
estimate. Free-tier allowances, credits, taxes, and account-specific adjustments are excluded,
so the provider invoice can differ. Cost is reported as unavailable for unrecognized models,
custom OpenAI or Gemini endpoints, or responses without enough usage metadata. See the official
[OpenAI](https://developers.openai.com/api/docs/pricing),
[Gemini](https://ai.google.dev/gemini-api/docs/pricing), and
[CLOVA](https://www.ncloud.com/product/aiService/clovaSpeech) pricing pages for current rates.

API keys are never written, not even in masked form; the Markdown only records
whether a key was configured. Replay commands use `<...>` placeholders for secret
values; replace them before running the command.

## Quality check

Some speech models loop on a phrase, emit text faster than anyone can speak, or
translate speech into English instead of transcribing it. meetdown scores every
transcript for these patterns without extra API calls and writes the result to
the Markdown metadata, such as `Quality check: poor: 47% suspect; repetition 3`.
`ok` means nothing was flagged, `review` means isolated problems, and `poor`
means a large share of the text is suspect. The Latin-script check runs when
`--language` starts with `ko`. When a transcript is flagged, re-transcribe with
another provider or with `--no-diarization`, and re-transcribe key ranges with
`--start` and `--end` before relying on names, dates, or numbers.

## Automation

Pass `--json` to print one JSON object to stdout when the run ends. Progress
messages move to stderr, so scripts and agents can parse stdout directly:

```powershell
uvx meetdown meeting.m4a -o meeting.md --language ko-KR --json
```

The summary includes the provider and how it was chosen (`option`,
`environment`, or `credentials`), the media duration, chunking (`option`, `auto`,
or `retry`), segment counts, the cost estimate, the quality report, and warnings.
Failures print `{"status": "error", "code": ..., "message": ...}` and exit with
code 1. Codes include `provider_ambiguous` (with `candidates`),
`provider_not_configured`, `provider_invalid_default`,
`provider_credentials_missing`, `provider_limit`, `provider_error`,
`media_error`, `input_not_found`, `notion_error`, and `invalid_option`.

When a provider returns unnamed speakers, meetdown writes speaker placeholders
like `[[SPEAKER_1]]` and `[[SPEAKER_2]]`. These are intentionally easy to find
with Replace All and change to real names after you identify the speakers.

## Initial scope

This project intentionally starts small. It supports one local file, provider-backed
speech recognition, full text output, speaker-segment output, and Markdown file generation.
Summaries, decisions, action items, database storage, web UI, async callbacks, and batch
processing are later extensions.
