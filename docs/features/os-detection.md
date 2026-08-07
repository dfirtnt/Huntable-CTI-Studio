# Platform Detection (OS Detection)

Automated operating-system / platform detection for threat-intelligence articles using
**deterministic entity-driven classification** — no embedding model.

## Overview

Platform Detection identifies the target operating system(s) in a CTI article. It runs as
**Step 0** in the agentic workflow and provides *platform context* that routes the rest of the
pipeline (it is no longer a hard non-Windows gate).

**Workflow behavior (platform-aware routing):**
- The detected platform(s) drive extractor routing — Windows-only extractors
  (`RegistryExtract`/`ServicesExtract`/`ScheduledTasksExtract`) are skipped on non-Windows evidence.
- Linux command/process evidence generates backend-neutral Sigma; mixed articles produce
  separate per-platform/logsource rule groups; macOS-only articles generate no Sigma (by design).
- Multi-platform articles are supported (multi-label verdict).

## Detection Method

Deterministic, explainable, and free (no LLM, no embedding model) for the common case:

1. **Entity/keyword registry scan** (primary): `PlatformClassifier` scores the article against the
   platform-tagged entries of the faceted keyword registry (`config/keyword_registry.yaml`),
   using weighted evidence with **margin-based** confidence and an evidence floor (thin signal →
   `Unknown`, never a guess). Multi-label by design.
2. **ATT&CK technique reinforcement**: cited ATT&CK techniques (`config/attack_technique_platforms.json`)
   *reinforce* platforms the registry already evidenced — they never originate a verdict.
3. **Windows-keyword safety net**: a deterministic Windows-keyword count rescues thin-evidence
   Windows content before falling through to `Unknown`.
4. **LLM adjudication** (`src/services/platform_adjudicator.py`): narrows only the
   low-confidence / `Unknown` tail (the configured small model, e.g. gpt-4o-mini), using the
   operator-configurable `OSDetectionAgent` prompt as its system message (strict-JSON output
   contract enforced separately, so prompt edits can't break parsing).

The earlier embedding/BERT classifier was measured non-discriminative for non-Windows content and
**retired** (2026-06-19); the OS-detection embedding model config was removed (2026-06-22). See
`docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md`.

### Computed at scoring time, consumed in the workflow

The deterministic verdict is computed **once at ingest scoring time** (`build_os_classification`,
stored in `article_metadata["os_classification"]`) and the workflow's `os_detection_node`
**consumes that precomputed verdict** instead of re-scanning; articles ingested before this
(go-forward) fall back to a fresh registry scan. The LLM-adjudication tail and ATT&CK
reinforcement run on top of the deterministic verdict either way.

## OS Labels

| Label | Indicators |
|---|---|
| `Windows` | PowerShell, registry paths (`hklm`), Event IDs, `lsass`, WMI, Windows file paths |
| `Linux` | `systemd`/`systemctl`, package managers (`apt`, `yum`), `/etc/`, `/dev/shm`, `memfd_create`, `chattr +i` |
| `MacOS` | `osascript`, `do shell script`, `launchctl`, `LaunchAgents`/`LaunchDaemons`, `dscl`, `.plist` |
| `multiple` | Multiple operating systems detected (multi-label) |
| `Unknown` | Insufficient signal to claim a platform |

## Configuration

Platform Detection is **deterministic** — there is no model to configure. The Workflow Config UI
shows only an informational label for Platform Detection; the OS selection checkboxes and the
former embedding-model dropdown were both removed (2026-06-22). Detection is always multi-platform
and the checkboxes were never wired to the detector. The underlying config key
`OSDetectionAgent_selected_os` is retained in the schema but is no longer user-settable via the UI.

## Storage

| Location | Contents |
|---|---|
| `articles.article_metadata["os_classification"]` | Verdict computed at scoring time (operating_system, platforms_detected, confidence, method, similarities, evidence) |
| `agentic_workflow_executions.error_log["os_detection_result"]` | Per-execution Platform Detection trace (`detected_os`, `platforms_detected`, `detection_method`, `confidence`, `similarities`, `max_similarity`, `probabilities`) |

## API Endpoint

`POST /api/articles/{article_id}/detect-os` runs Platform Detection on a single article.

| Code | Condition |
|---|---|
| `422 no_huntable_content` | Content filter found no huntable chunks; LLM is not called |
| `404` | Article ID does not exist |

## Programmatic Usage

```python
from src.services.os_detection_service import OSDetectionService

service = OSDetectionService()  # deterministic; no model name needed
result = await service.detect_os(article_content)
# {"operating_system": "Windows", "confidence": "high", "method": "kb_scoring",
#  "platforms_detected": ["Windows"], "similarities": {...}, "evidence": {...}}
```

The registry-sourced classifier is also available directly:

```python
from src.utils.keyword_registry import project_platform, build_os_classification
verdict = project_platform(content)            # PlatformClassification
record = build_os_classification(content)      # compact dict stored in article_metadata
```

## Performance

- Registry/keyword scan: < 5 ms (no model load).
- LLM adjudication: only on the low-confidence/Unknown tail.

## Related Files

- `src/services/os_detection_service.py` — `detect_os` (entity-driven)
- `src/services/platform_classifier.py` — `PlatformClassifier` engine (entries = registry platform vocabulary)
- `src/utils/keyword_registry.py` — `project_platform` / `build_os_classification`; the faceted registry is the single platform vocabulary
- `src/services/attack_platform_signal.py` + `config/attack_technique_platforms.json` — ATT&CK reinforcement
- `src/services/platform_adjudicator.py` — LLM adjudication for the low-confidence tail

_Last updated: 2026-07-06_
