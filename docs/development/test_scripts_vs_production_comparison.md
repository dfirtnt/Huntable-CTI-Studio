# Test Scripts vs Production Code Comparison

## Key Difference: Reasoning Control Implementation

### Test Scripts (`scripts/test_nothink.py`, etc.)

**Direct API calls** - Bypass the application's LLMService layer:

```python
# Test script approach
payload = {
    "model": model,
    "messages": [...],
    "chat_template_kwargs": {"enable_thinking": False}  # Direct API parameter
    # OR
    # "/nothink\n\n" + user_message  # Direct prompt modification
}
response = requests.post(lmstudio_url, json=payload)
```

**Characteristics:**
- Direct HTTP calls to LMStudio
- Manual payload construction
- Direct control over API parameters
- No abstraction layer
- Tests reasoning control in isolation

### Production Code (`src/services/llm_service.py`)

**Uses LLMService abstraction** - Goes through application layers:

```python
# Production code approach
result = await llm_service.run_extraction_agent(
    agent_name="CmdlineExtract",
    content=article.content,
    ...
)
# Which calls:
# → request_chat()
# → _post_lmstudio_chat()
# → HTTP request to LMStudio
```

**Current State:**
- **NO reasoning control implemented** in `request_chat()` or `_post_lmstudio_chat()`
- Payload is built without `chat_template_kwargs`
- User messages are NOT prefixed with `/nothink`
- Relies on prompt instructions only: "If you are a reasoning model, put reasoning BEFORE the JSON"

## The Gap

**Test scripts prove `/nothink` works** (6/8 Qwen models, 17/24 overall)

**Production code does NOT use `/nothink`** - it's missing the implementation!

## What Needs to Be Done

To apply the test script findings to production:

1. **Add `/nothink` to user prompts** in `run_extraction_agent()`:
   ```python
   user_prompt = "/nothink\n\n" + user_prompt
   ```

2. **OR add reasoning control to `request_chat()`**:
   ```python
   if provider == "lmstudio":
       payload = {...}
       # Add reasoning control
       if model_is_qwen:
           payload["chat_template_kwargs"] = {"enable_thinking": False}
       else:
           payload["reasoning"] = "low"
   ```

## Recommendation

Based on test results showing `/nothink` is more effective:
- **Implement `/nothink` in user prompts** (simpler, more effective)
- Add it in `run_extraction_agent()` when constructing `user_prompt`
- This matches the test script approach that proved successful

