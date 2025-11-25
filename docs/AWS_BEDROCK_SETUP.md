# AWS Bedrock Setup Instructions

## Current Status

✅ **Credentials Valid**: Authentication working  
❌ **Model Access**: Blocked by SCP (Service Control Policy)  
❌ **Model Invocation**: Access denied for all tested models

**Account**: `735278610086`  
**User**: `andrew.skatoff.sparx@frit.frb.org`  
**Role**: `AWSReservedSSO_AWSAdministratorAccess_6b884e1977a038dd`

---

## Step 1: Enable Models in AWS Bedrock Console

### Via AWS Console

1. **Navigate to Bedrock Console**
   - Go to: https://console.aws.amazon.com/bedrock/
   - Select region: `us-east-1` (or your preferred region)

2. **Enable Model Access**
   - Click **"Model access"** in left sidebar
   - Click **"Request model access"** or **"Edit"**
   - Select models to enable:
     - ✅ `anthropic.claude-3-5-sonnet-20241022-v2:0` (recommended)
     - ✅ `anthropic.claude-3-5-sonnet-20241022-v1:0`
     - ✅ `anthropic.claude-3-opus-20240229-v1:0`
     - ✅ `anthropic.claude-3-sonnet-20240229-v1:0`
     - ✅ `anthropic.claude-3-haiku-20240307-v1:0` (fastest/cheapest)
   - Click **"Save changes"**
   - Wait 1-2 minutes for activation

### Via AWS CLI

```bash
# Set credentials
export AWS_ACCESS_KEY_ID="ASIA2WMQFG2TC2GT6O33"
export AWS_SECRET_ACCESS_KEY="tewXIFaf6X5r5oVHrjWzTPMwWbDykl9FW/DRii7g"
export AWS_SESSION_TOKEN="IQoJb3JpZ2luX2VjEKn//////////wEaCXVzLWVhc3QtMSJHMEUCIEx6nN9J41HcGj8thklUZeofsBt3mklfB7dGjWbW4nEdAiEAgGQpWNov4FBAJhhidkVEalUzHDM+jbOFHum7WEuZK9cqrgMIchABGgw3MzUyNzg2MTAwODYiDKSiYw335EUEK5FYuCqLA46gH52BUg1YpH817/PuUn74M6+zeXkcamn22w4OEwQFKG3tlDaItuBrGARCnwp/S/P6tYIXYea+MGYmP6RXj1KtaxTM+Uenr5r/+1sBLWJOjDvGK3RipSNOWsLmwrg9OAx7jbTapPcYSSAxvH5ynKYKlvP2bH5tBkeFw6r7ImolIMk8qbmjEpF/SjU17k0QVAL51VPPXDwP5Ptfbsa5EwQd6uuvUtQ5OUiF7ntxMq/rl2lEoRuNShNAKhMxwwpVyZlwb8YbwPdJ3CLtbEx3gmdffHjIrf8wFGk0CDlRZ9KZ+aYSHms2yOV8a9OgcoY55LtgjuLQbn9492fIRP9f8caZeKUgQAjxdye2pSz06KZ9MG9Lh2vLwEqU9TJLqfTFLG+CSZWsupNl+pYNpNipRfmqXwbfPPPHGG5Sw55Zwhnm9Ny99ZIH2+XpJhFw+F4c/Te4nR/sf2ziOo15eQnppwOFnU8irkwwYFwLiDcPdfB00Z9SXBQERYn/sVdMGMDw+6hs1DfSc+5RwFhSMODCl8kGOqQBqbwdvk6aprMH5cphUvrrABWNdzwj4XMAAUP78R7C3VB9qWgyZzFvoSvV0DaMT5TI14cwDI8iGsMBJHyuM8R9P3cXW8Ab3BjlJ+bcXAVSR5JAlvU0x3RRp4ZwRwsfPMx+T/HBZ0tWxjbxmK53p4NN2QeMU1B1s+RozSGKKlj7cPI1Syf9zkaqLMAWgCcihZbZSHZF9PeySwoBqq9ARTTY8nbgSy4="
export AWS_REGION="us-east-1"

# Request model access (requires AWS CLI v2.15+)
aws bedrock put-model-invocation-logging-configuration \
  --region us-east-1 \
  --logging-config '{"textDataDeliveryEnabled":false,"imageDataDeliveryEnabled":false}'

# Note: Model access must be enabled via console - CLI doesn't support it directly
```

---

## Step 2: Resolve SCP Restrictions

### Current SCP Blocking:
- `bedrock:ListFoundationModels` - Explicit deny
- `bedrock:InvokeModel` - Access denied (may be SCP or IAM policy)

### Required Actions:

1. **Contact AWS Administrator** to update SCP:
   - Request exception for Bedrock model access
   - Account: `735278610086`
   - Required permissions:
     ```
     bedrock:InvokeModel
     bedrock:InvokeModelWithResponseStream
     bedrock:ListFoundationModels (optional, for discovery)
     ```

2. **Verify IAM Permissions**:
   - Check role: `AWSReservedSSO_AWSAdministratorAccess_6b884e1977a038dd`
   - Ensure Bedrock permissions are attached
   - Policy example:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": [
             "bedrock:InvokeModel",
             "bedrock:InvokeModelWithResponseStream"
           ],
           "Resource": "arn:aws:bedrock:us-east-1::foundation-model/*"
         }
       ]
     }
     ```

---

## Step 3: Test After Configuration

### Run Test Script

```bash
cd /Users/starlord/CTIScraper
source venv-bedrock-test/bin/activate

export AWS_ACCESS_KEY_ID="ASIA2WMQFG2TC2GT6O33"
export AWS_SECRET_ACCESS_KEY="tewXIFaf6X5r5oVHrjWzTPMwWbDykl9FW/DRii7g"
export AWS_SESSION_TOKEN="<YOUR_SESSION_TOKEN>"
export AWS_REGION="us-east-1"

python utils/temp/test_aws_bedrock.py
```

### Expected Success Output

```
✅ Found X available models
✅ anthropic.claude-3-5-sonnet-20241022-v2:0 - INVOCATION SUCCESSFUL!
```

---

## Step 4: Integration with CTIScraper

### Environment Variables

Add to `.env`:

```bash
# AWS Bedrock Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_SESSION_TOKEN=your_session_token  # If using temporary credentials
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### Python Dependencies

```bash
pip install boto3
```

### Usage Example

```python
import boto3
import json

bedrock_runtime = boto3.client(
    'bedrock-runtime',
    region_name='us-east-1'
)

response = bedrock_runtime.invoke_model(
    modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": "Hello"}]
    }),
    contentType='application/json',
    accept='application/json'
)

result = json.loads(response['body'].read())
print(result['content'][0]['text'])
```

---

## Troubleshooting

### Error: AccessDeniedException
- **Cause**: SCP or IAM policy blocking access
- **Fix**: Request SCP exception or update IAM policy

### Error: ValidationException - Model not available
- **Cause**: Model not enabled in console
- **Fix**: Enable model in Bedrock console → Model access

### Error: Region mismatch
- **Cause**: Model not available in selected region
- **Fix**: Use `us-east-1` or `us-west-2` (most models available)

### Session Token Expired
- **Cause**: Temporary credentials expired (typically 1 hour)
- **Fix**: Refresh credentials via AWS SSO or CLI

---

## Quick Reference

| Action | Console URL | CLI Command |
|--------|-------------|-------------|
| Enable Models | https://console.aws.amazon.com/bedrock/ → Model access | N/A (console only) |
| Test Credentials | N/A | `python utils/temp/test_aws_bedrock.py` |
| List Models | https://console.aws.amazon.com/bedrock/ → Model access | `aws bedrock list-foundation-models` |

---

## Next Steps

1. ✅ Enable models in AWS Bedrock console
2. ✅ Request SCP exception for Bedrock access
3. ✅ Verify IAM permissions
4. ✅ Run test script to confirm access
5. ✅ Integrate Bedrock into CTIScraper workflow

