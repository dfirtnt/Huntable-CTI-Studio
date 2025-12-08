# Alternative Approaches for Setting LMStudio Context Windows from Docker

## Current Issue
The workflow runs in Docker and cannot directly execute host commands to set LMStudio context windows. The API endpoint returns 503 when trying to set context windows.

## Solution 1: Environment Variable Override (Recommended)
**Status:** ✅ Implemented

Set context window via environment variable without needing to execute commands:

```bash
# In docker-compose.yml or .env
MODEL_CONTEXT_WINDOW_codellama_7b_instruct=10240
MODEL_CONTEXT_WINDOW_mistralai_mistral_7b_instruct_v0_3=10240
```

The workflow will use these values instead of trying to set them dynamically.

**Pros:**
- No Docker/host communication needed
- Works immediately
- Can be configured per model

**Cons:**
- Requires manual configuration
- Doesn't automatically set in LMStudio (still need to load model with correct context)

## Solution 2: Pre-load Models with Correct Context
**Status:** ⚠️ Manual setup required

Load models with correct context length before starting the workflow:

```bash
# On host machine, before starting workflow
./scripts/set_lmstudio_context.sh codellama-7b-instruct 10240
```

Or use the utility script:
```bash
python utils/load_lmstudio_models.py codellama-7b-instruct --context-length 10240
```

**Pros:**
- Models already configured when workflow starts
- No runtime context setting needed
- Reliable

**Cons:**
- Manual step required
- Need to reload if model changes

## Solution 3: File-Based Trigger
**Status:** ✅ Implemented

Docker writes a request file and a host-side watcher executes it:

1. On the host (outside Docker), start the watcher:
   ```bash
   python scripts/host_lmstudio_context_watcher.py
   ```
2. The API/UI creates `scripts/context_requests/<id>.request.json` with `model_name` and `context_length`.
3. The host watcher runs `scripts/set_lmstudio_context.sh <model_name> <context_length>` using the host's `lms` CLI.
4. The watcher writes `scripts/context_requests/<id>.response.json` with success/error details read by the container.

**Pros:**
- Works from Docker without Docker socket exposure
- Asynchronous and deterministic (one request → one response file)
- Keeps host-only execution limited to loading LMStudio models

**Cons:**
- Requires host-side watcher to be running
- Leaves small JSON request/response artifacts (ignored by git)

## Solution 4: Docker Socket Execution (Not Recommended)
**Status:** ❌ Not implemented (security risk)

Use Docker socket to execute commands on host:

```python
subprocess.run([
    "docker", "run", "--rm",
    "--network", "host",
    "-v", "/var/run/docker.sock:/var/run/docker.sock",
    "alpine", "sh", "-c", "lms load ..."
])
```

**Pros:**
- Could work from Docker

**Cons:**
- Security risk (Docker socket access)
- Complex
- Requires Docker socket mounted
- Still needs `lms` CLI in container

## Solution 5: Accept 503 and Provide Instructions (Current)
**Status:** ✅ Current behavior

Workflow attempts to set context window, logs warning with instructions if it fails, and continues.

**Pros:**
- Simple
- No additional infrastructure
- Clear error messages

**Cons:**
- Doesn't actually set context window
- Requires manual intervention

## Solution 6: Change Default to 10k Tokens (Implemented)
**Status:** ✅ Implemented

Changed default context window from 16384 to 10240 (10k) tokens for `codellama-7b-instruct` and `mistralai/mistral-7b-instruct-v0.3`.

**Pros:**
- Lower default reduces context overflow errors
- Works with most model configurations
- Can still be overridden via environment variable

**Cons:**
- May not be optimal for all use cases
- Still need to configure LMStudio with this context length

## Recommended Approach

**For immediate use:**
1. Run the host watcher (Solution 3) to let the container request context changes automatically:
   `python scripts/host_lmstudio_context_watcher.py`
2. Keep Solution 6 defaults (10k) unless overridden.
3. Use environment variable overrides (Solution 1) for fine-tuning.
4. Optionally pre-load models manually (Solution 2) before starting the stack.

**Fallback if watcher unavailable:**
- Accept Solution 5 (manual handling) and rely on pre-configuration until the watcher can run.

## Testing

After changing defaults to 10k:

1. **Verify default changed:**
   ```bash
   docker logs cti_web | grep "Ensuring model.*10240"
   ```

2. **Pre-load model with 10k context:**
   ```bash
   ./scripts/set_lmstudio_context.sh codellama-7b-instruct 10240
   ```

3. **Run workflow and check logs:**
   ```bash
   docker logs cti_web --tail 100 | grep -i "context\|codellama"
   ```

4. **Override via environment variable (if needed):**
   ```bash
   # In docker-compose.yml
   MODEL_CONTEXT_WINDOW_codellama_7b_instruct=16384
   ```


