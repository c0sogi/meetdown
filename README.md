# meetdown

`meetdown` is a small Python CLI for turning meeting audio into a Markdown transcript.

The CLI sends a local audio or video file to a speech provider, normalizes the
response, and writes a `.md` file with the full text and speaker-by-speaker
transcript when the provider returns speaker information. When `--provider` is
omitted, meetdown auto-detects the provider from configured provider-specific
credentials.

## Install and run

Run it directly with `uvx`; cloning this repository is not required:

```powershell
uvx meetdown meeting.m4a -o meeting.md --api-url "https://your.invoke.url" --api-key "your-secret-key"
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

Run `meetdown` without arguments, or use `--help`, to see the current defaults
and provider auto-detection status without transcribing anything. In interactive
terminals, the defaults are color-coded by area; set `NO_COLOR=1` to keep plain
text output.

```powershell
uvx meetdown
uvx meetdown --help
```

Recognition language defaults to `auto`, so meetdown does not force a single
language when audio contains a mix such as English and Korean. Pass
`--language ko-KR`, `--language en-US`, or another provider-supported language
when you want to bias recognition toward one language.

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

## Providers

If `--provider` is omitted, meetdown picks a provider only when exactly one
provider-specific API key is configured. Pass `--provider` explicitly when more
than one provider key is present, or when you pass only a generic `--api-key` or
`MEETDOWN_API_KEY`.

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
uvx meetdown meeting.m4a -o meeting.md --chunk-duration 10m
uvx meetdown meeting.m4a -o meeting.md --provider openai --api-url "https://api.openai.com/v1"

$env:GEMINI_API_KEY="your-gemini-key"
uvx meetdown meeting.m4a -o meeting.md --chunk-duration 10m
```

Use `--model` to override the provider default model. CLOVA does not support
`--model`; the CLOVA Speech model is determined by the Invoke URL/domain.
OpenAI defaults to a diarization-capable transcription model when diarization is
enabled, and to a smaller transcription model when `--no-diarization` is used.
Gemini uses inline audio requests, so use `--chunk-duration` for larger files.

## Chunk long recordings

Use `--chunk-duration` when a recording is too long for one sync upload. The
CLI extracts audio chunks with `ffmpeg`, sends each chunk to the selected provider,
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

Generated Markdown includes a `Processing options` section with the provider, model, language,
compression, chunking, range, timeout settings, and a replay command for the run.
Raw API keys are never written. They are stored only in masked form, such as
`sk-p********7890`. Replay commands use `<...>` placeholders for secret values;
replace them before running the command.

When a provider returns unnamed speakers, meetdown writes speaker placeholders
like `[[SPEAKER_1]]` and `[[SPEAKER_2]]`. These are intentionally easy to find
with Replace All and change to real names after you identify the speakers.

## Initial scope

This project intentionally starts small. It supports one local file, provider-backed
speech recognition, full text output, speaker-segment output, and Markdown file generation.
Summaries, decisions, action items, database storage, web UI, async callbacks, and batch
processing are later extensions.
