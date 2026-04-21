# Authentication

## Overview

Huntable CTI Studio implements API key authentication for administrative operations that could impact system integrity.

## Protected Endpoints

The following endpoints require authentication via the `X-API-Key` header:

### Backup & Restore Operations
- `POST /api/backup/create` - Create system backup
- `POST /api/backup/restore` - Restore from backup
- `POST /api/backup/restore-from-file` - Restore from uploaded file
- `POST /api/backup/cron` - Configure backup cron jobs
- `DELETE /api/backup/cron` - Remove backup cron jobs

## Configuration

### 1. Generate API Key

Generate a secure API key:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### 2. Set Environment Variable

Add to your `.env` file:

```bash
ADMIN_API_KEY=your_generated_api_key_here
```

**Important**: Keep this key secure. Anyone with this key can perform destructive operations like restoring backups.

### 3. Restart Application

Restart the application for the change to take effect:

```bash
docker-compose restart web
```

## Usage

### API Requests

Include the API key in the `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/api/backup/create \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"backup_type": "full"}'
```

### Python Requests

```python
import requests

headers = {
    "X-API-Key": "your_api_key_here",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://localhost:8000/api/backup/create",
    headers=headers,
    json={"backup_type": "full"}
)
```

### JavaScript/Fetch

```javascript
const response = await fetch('http://localhost:8000/api/backup/create', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your_api_key_here',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ backup_type: 'full' })
});
```

## Error Responses

### 401 Unauthorized
API key is missing:

```json
{
  "detail": "API key required. Provide X-API-Key header."
}
```

### 403 Forbidden
API key is invalid:

```json
{
  "detail": "Invalid API key"
}
```

### 500 Internal Server Error
Server misconfiguration (ADMIN_API_KEY not set):

```json
{
  "detail": "Server authentication not configured"
}
```

## Security Best Practices

1. **Keep API keys secret** - Never commit API keys to version control
2. **Rotate regularly** - Change API keys periodically
3. **Use HTTPS** - Always use HTTPS in production to prevent key interception
4. **Restrict network access** - Use firewall rules to limit who can reach admin endpoints
5. **Monitor usage** - Log and alert on admin API usage
6. **Unique keys per environment** - Use different API keys for dev/staging/production

## Rotating API Keys

1. Generate a new API key
2. Update `ADMIN_API_KEY` in `.env`
3. Restart the application
4. Update all clients to use the new key
5. Verify old key no longer works

## Troubleshooting

### "Server authentication not configured"

The `ADMIN_API_KEY` environment variable is not set. Set it in your `.env` file and restart the application.

### "Invalid API key"

The provided API key doesn't match the server's configured key. Verify:
- The key is correct
- There are no extra spaces or newlines
- The environment variable is loaded correctly

### "API key required"

The `X-API-Key` header is missing from the request. Add it to your request headers.
