# OpenAI Chat Models Reference

Source: [platform.openai.com/docs/models](https://platform.openai.com/docs/models) (Jan 2025)

## Chat Completions Models (text-in, text-out)

| Model | Context Window | Max Output Tokens | API Params |
|-------|----------------|-------------------|------------|
| **GPT-5 series** | | | |
| gpt-5.2 | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5.2-pro | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5.1 | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5 | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5-mini | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5-nano | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| **GPT-4.1 series** | | | |
| gpt-4.1 | 1,047,576 | 32,768 | `max_tokens`, `temperature` |
| gpt-4.1-mini | 1,047,576 | 32,768 | `max_tokens`, `temperature` |
| gpt-4.1-nano | 1,047,576 | 32,768 | `max_tokens`, `temperature` |
| **Reasoning (o-series)** | | | |
| o3 | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o3-pro | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o3-mini | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o4-mini | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o1 | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o1-pro | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| **GPT-4o series** | | | |
| gpt-4o | 128,000 | 16,384 | `max_tokens`, `temperature` |
| gpt-4o-mini | 128,000 | 16,384 | `max_tokens`, `temperature` |
| **Legacy** | | | |
| gpt-4-turbo | 128,000 | 4,096 | `max_tokens`, `temperature` |
| gpt-4 | 8,192 | 4,096 | `max_tokens`, `temperature` |
| gpt-3.5-turbo | 16,385 | 4,096 | `max_tokens`, `temperature` |

## API Parameter Rules

| Model Family | Token Param | Temperature |
|--------------|-------------|-------------|
| gpt-5.x, o1, o3, o4 | `max_completion_tokens` | Not supported |
| gpt-4.x, gpt-4o, gpt-3.5 | `max_tokens` | Supported |

## Specialized (not Chat Completions)

- **Deep research**: o3-deep-research, o4-mini-deep-research
- **Codex**: gpt-5.2-codex, gpt-5.1-codex, gpt-5-codex
- **Realtime/Audio**: gpt-realtime, gpt-audio, gpt-4o-audio-preview
- **Image**: gpt-image-1.5, gpt-image-1
- **TTS/Transcribe**: gpt-4o-mini-tts, gpt-4o-transcribe
