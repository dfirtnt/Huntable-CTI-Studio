# LMStudio Integration Guide

## Setup

1. **Start LMStudio**:
   - Open LMStudio
   - Go to Developer tab → Local Server
   - Enable "Serve on local network"
   - Start server (default port: 1234)
   - Load your preferred model

2. **Run CTIScraper with LMStudio**:
```bash
# Start with LMStudio override
docker-compose -f docker-compose.yml -f docker-compose.lmstudio.yml up web

# Or start all services
docker-compose -f docker-compose.yml -f docker-compose.lmstudio.yml up
```

3. **Configure Model Name**:
   - Edit `docker-compose.lmstudio.yml`
   - Set `LMSTUDIO_MODEL` to your loaded model name
   - Example: `LMSTUDIO_MODEL=llama-3.1-8b-instruct`

## API Usage

In the web interface, select `lmstudio` as the LLM provider in chat settings.

## Troubleshooting

- **Connection refused**: Ensure LMStudio server is running and accessible
- **Model not found**: Verify model name matches exactly in LMStudio
- **Timeout errors**: Increase timeout in `_call_lmstudio()` method if needed

## Environment Variables

- `LMSTUDIO_API_URL`: LMStudio API endpoint (default: `http://host.docker.internal:1234/v1`)
- `LMSTUDIO_MODEL`: Model name in LMStudio (default: `local-model`)
