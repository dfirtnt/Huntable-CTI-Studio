# Source Auto-Healing v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the source auto-healing pipeline from a single-shot hourly retry model to a multi-round conversational healing session with audit trail, per-source controls, and UI guardrails.

**Architecture:** The healing service gains an inner retry loop (up to `max_attempts` LLM rounds per session) where each round feeds the previous attempt's failure back to the LLM. A new `HealingEventTable` stores every action the LLM takes. The coordinator no longer manages attempt counting across scans — it dispatches once, and the service handles all retries internally. The Sources page gets per-source "Heal Now" and "Reset" buttons plus a slide-out panel showing healing history.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Celery, Jinja2 templates, Langfuse, PostgreSQL

---

## Design Decisions (from operator Q&A)

| Decision | Choice |
|---|---|
| Dashboard button when healing disabled | Greyed out with tooltip "Enable healing in Settings" |
| LLM disabling sources | **Blocked** — remove `active` from `_MUTABLE_FIELDS` |
| 0-article validation | **Pass** — 0 articles is a valid fetch result |
| Per-source heal button | Yes, on Sources page |
| Reset exhausted flow | Button on Sources page, resets both `healing_exhausted` and `healing_attempts` |
| Retry model | Multi-round within a single session (not across hourly scans) |
| Max attempts meaning | Max LLM rounds within one healing session |
| Cooldown between inner rounds | 30 seconds (hardcoded constant) |
| Audit trail | Both Langfuse traces AND in-app `HealingEventTable` |
| Healing history UI | Slide-out panel on Sources page |

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/database/models.py` | Modify | Add `HealingEventTable` |
| `src/models/healing_event.py` | Create | Pydantic models for healing events |
| `src/database/async_manager.py` | Modify | Add `create_healing_event()`, `get_healing_events()` methods |
| `src/services/source_healing_service.py` | Modify | Multi-round loop, block `active=false`, Langfuse tracing, event logging |
| `src/services/source_healing_coordinator.py` | Modify | Simplify — remove per-scan attempt counting, dispatch once |
| `src/web/routes/sources.py` | Modify | Add `/api/sources/{id}/heal`, `/api/sources/{id}/reset-healing`, `/api/sources/{id}/healing-history` |
| `src/web/routes/actions.py` | No change | Keep 409 guard as server-side safety net; client-side handles UX |
| `src/web/routes/dashboard.py` | Modify | Add `healing_enabled` to error fallback |
| `src/web/templates/dashboard.html` | Modify | Grey-out button + tooltip when disabled |
| `src/web/templates/sources.html` | Modify | Add heal/reset buttons, slide-out panel |
| `scripts/migrate_add_healing_events.py` | Create | Migration script for `healing_events` table |
| `tests/services/test_source_healing_service.py` | Create | Unit tests for healing service |
| `tests/api/test_healing_endpoints.py` | Create | API endpoint tests |

## Security Note

All healing history UI rendering in Task 9 MUST use safe DOM construction methods (textContent, createElement, etc.) rather than string interpolation into markup. The LLM-generated diagnosis text is stored in the database and must be treated as untrusted content. Use textContent for text nodes and build elements programmatically.

---

### Task 1: Add HealingEventTable to database models

**Files:**
- Modify: `src/database/models.py:55-57` (after existing healing fields)
- Create: `src/models/healing_event.py`
- Create: `scripts/migrate_add_healing_events.py`
- Test: `tests/services/test_source_healing_service.py`

- [ ] **Step 1: Write the HealingEvent Pydantic model**

Create `src/models/healing_event.py`:

```python
"""Pydantic models for healing event audit trail."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealingEventCreate(BaseModel):
    """Data for recording a healing event."""

    source_id: int
    round_number: int
    diagnosis: str
    actions_proposed: list[dict[str, Any]]
    actions_applied: list[dict[str, Any]]
    validation_success: bool | None = None
    error_message: str | None = None


class HealingEvent(BaseModel):
    """Complete healing event model."""

    id: int
    source_id: int
    round_number: int
    diagnosis: str
    actions_proposed: list[dict[str, Any]]
    actions_applied: list[dict[str, Any]]
    validation_success: bool | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Add HealingEventTable to models.py**

Add after `SourceCheckTable` (around line 140) in `src/database/models.py`:

```python
class HealingEventTable(Base):
    """Audit trail for AI source healing actions."""

    __tablename__ = "healing_events"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    diagnosis = Column(Text, nullable=False)
    actions_proposed = Column(JSON, nullable=False, default=list)
    actions_applied = Column(JSON, nullable=False, default=list)
    validation_success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)

    source = relationship("SourceTable", backref="healing_events")
```

Also add `HealingEventTable` to the imports in `src/database/async_manager.py` (around line 35-42).

- [ ] **Step 3: Create migration script**

Create `scripts/migrate_add_healing_events.py`:

```python
"""Migration: Add healing_events table for AI healing audit trail."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect

from src.database.manager import DatabaseManager
from src.database.models import HealingEventTable


def migrate():
    db = DatabaseManager()
    engine = db.engine
    inspector = inspect(engine)

    if "healing_events" not in inspector.get_table_names():
        HealingEventTable.__table__.create(engine)
        print("Created healing_events table")
    else:
        print("healing_events table already exists")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 4: Write test for HealingEvent model**

Create `tests/services/test_source_healing_service.py`:

```python
"""Tests for source healing service."""

import pytest

from src.models.healing_event import HealingEvent, HealingEventCreate


class TestHealingEventModels:
    """Test HealingEvent Pydantic models."""

    def test_healing_event_create_minimal(self):
        event = HealingEventCreate(
            source_id=1,
            round_number=1,
            diagnosis="Domain redirected",
            actions_proposed=[{"field": "url", "value": "https://new.example.com"}],
            actions_applied=[{"field": "url", "value": "https://new.example.com"}],
        )
        assert event.source_id == 1
        assert event.validation_success is None

    def test_healing_event_create_with_validation(self):
        event = HealingEventCreate(
            source_id=1,
            round_number=2,
            diagnosis="RSS feed moved",
            actions_proposed=[],
            actions_applied=[],
            validation_success=False,
            error_message="Connection refused",
        )
        assert event.validation_success is False
        assert event.error_message == "Connection refused"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestHealingEventModels -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/models/healing_event.py src/database/models.py scripts/migrate_add_healing_events.py tests/services/test_source_healing_service.py
git commit -m "feat: add HealingEventTable for AI healing audit trail"
```

---

### Task 2: Add healing event DB methods to async_manager

**Files:**
- Modify: `src/database/async_manager.py` (imports ~line 35, new methods after `update_source_health` ~line 597)
- Test: `tests/services/test_source_healing_service.py`

- [ ] **Step 1: Write failing test for create_healing_event**

Add to `tests/services/test_source_healing_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.healing_event import HealingEventCreate


class TestHealingEventDBMethods:
    """Test healing event database operations."""

    @pytest.mark.asyncio
    async def test_create_healing_event_constructs_row(self):
        """Verify create_healing_event builds the correct HealingEventTable row."""
        from src.database.async_manager import AsyncDatabaseManager

        db = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

        event_data = HealingEventCreate(
            source_id=42,
            round_number=1,
            diagnosis="Test diagnosis",
            actions_proposed=[{"field": "url", "value": "https://example.com"}],
            actions_applied=[{"field": "url", "value": "https://example.com"}],
            validation_success=True,
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db, "get_session", return_value=mock_session):
            await db.create_healing_event(event_data)

        mock_session.add.assert_called_once()
        added_row = mock_session.add.call_args[0][0]
        assert added_row.source_id == 42
        assert added_row.diagnosis == "Test diagnosis"
        assert added_row.validation_success is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestHealingEventDBMethods -v`
Expected: FAIL with `AttributeError: 'AsyncDatabaseManager' object has no attribute 'create_healing_event'`

- [ ] **Step 3: Implement create_healing_event and get_healing_events**

Add import of `HealingEventTable` to `src/database/async_manager.py` imports (line ~35-42).

Add these methods to `AsyncDatabaseManager` class (after `update_source_health` ~line 597):

```python
    async def create_healing_event(self, event_data) -> None:
        """Record a healing event in the audit trail."""
        from src.database.models import HealingEventTable

        try:
            async with self.get_session() as session:
                row = HealingEventTable(
                    source_id=event_data.source_id,
                    round_number=event_data.round_number,
                    diagnosis=event_data.diagnosis,
                    actions_proposed=event_data.actions_proposed,
                    actions_applied=event_data.actions_applied,
                    validation_success=event_data.validation_success,
                    error_message=event_data.error_message,
                )
                session.add(row)
                await session.commit()
        except Exception:
            logger.exception("Failed to record healing event for source %s", event_data.source_id)

    async def get_healing_events(self, source_id: int, limit: int = 20) -> list:
        """Get recent healing events for a source, newest first."""
        from src.database.models import HealingEventTable
        from src.models.healing_event import HealingEvent

        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(HealingEventTable)
                    .where(HealingEventTable.source_id == source_id)
                    .order_by(HealingEventTable.created_at.desc())
                    .limit(limit)
                )
                rows = result.scalars().all()
                return [HealingEvent.model_validate(r) for r in rows]
        except Exception:
            logger.exception("Failed to get healing events for source %s", source_id)
            return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestHealingEventDBMethods -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/database/async_manager.py tests/services/test_source_healing_service.py
git commit -m "feat: add create_healing_event and get_healing_events to async_manager"
```

---

### Task 3: Block LLM from disabling sources

**Files:**
- Modify: `src/services/source_healing_service.py:25` (`_MUTABLE_FIELDS`)
- Modify: `src/services/source_healing_service.py:54-55` (system prompt)
- Test: `tests/services/test_source_healing_service.py`

- [ ] **Step 1: Write failing test**

Add to `tests/services/test_source_healing_service.py`:

```python
class TestMutableFieldsGuard:
    """Test that the LLM cannot disable sources."""

    def test_active_not_in_mutable_fields(self):
        from src.services.source_healing_service import _MUTABLE_FIELDS

        assert "active" not in _MUTABLE_FIELDS, "LLM must not be allowed to set active=false"

    def test_system_prompt_does_not_mention_active(self):
        from src.services.source_healing_service import SYSTEM_PROMPT

        assert 'Set "active" to false' not in SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestMutableFieldsGuard -v`
Expected: FAIL (active is currently in `_MUTABLE_FIELDS`)

- [ ] **Step 3: Remove active from _MUTABLE_FIELDS and update system prompt**

In `src/services/source_healing_service.py`:

Line 25 — change:
```python
_MUTABLE_FIELDS = {"url", "rss_url", "active", "config"}
```
to:
```python
_MUTABLE_FIELDS = {"url", "rss_url", "config"}
```

Lines 49-56 in SYSTEM_PROMPT — change:
```
- Valid field names: "url", "rss_url", "active", "config".
```
to:
```
- Valid field names: "url", "rss_url", "config".
```

Remove the line about setting `active` to false:
```
- Set "active" to false ONLY if the source appears permanently unreachable (e.g., domain \
does not resolve, returns 404/410 consistently, or the site is clearly defunct).
```
Replace with:
```
- Do NOT set the "active" field. Source activation/deactivation is an operator-only action.
```

Also remove the dead `elif field == "active"` branch in `_apply_actions` (~line 361-362) since the `_MUTABLE_FIELDS` guard now blocks `active` before it reaches this code:

```python
                elif field == "active" and isinstance(value, bool):
                    update_kwargs["active"] = value
```

Delete these two lines entirely.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestMutableFieldsGuard -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/source_healing_service.py tests/services/test_source_healing_service.py
git commit -m "fix: block LLM from disabling sources via active=false"
```

---

### Task 4: Refactor healing service to multi-round with audit logging

This is the core change. The service's `_run_inner` method becomes a loop of up to `max_attempts` rounds. Each round feeds the previous round's failure context to the LLM.

**Files:**
- Modify: `src/services/source_healing_service.py` (entire `_run_inner` method, add `_RETRY_DELAY_SECONDS` constant, add Langfuse tracing)
- Test: `tests/services/test_source_healing_service.py`

- [ ] **Step 1: Write failing test for multi-round behavior**

Add to `tests/services/test_source_healing_service.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestMultiRoundHealing:
    """Test multi-round healing loop behavior."""

    @pytest.mark.asyncio
    async def test_stops_after_successful_validation(self):
        """Service should stop retrying after a successful round."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        config = SourceHealingConfig(enabled=True, max_attempts=3)
        service = SourceHealingService(config)

        # Mock all pipeline stages
        snapshot = {"id": 1, "name": "Test", "url": "https://test.com", "rss_url": None,
                    "active": True, "config": {}, "consecutive_failures": 5,
                    "last_check": None, "last_success": None}

        with patch.object(service, "_get_source_snapshot", return_value=snapshot), \
             patch.object(service, "_get_error_history", return_value=[]), \
             patch.object(service, "_probe_urls", return_value=[]), \
             patch.object(service, "_analyze_with_llm", return_value={
                 "diagnosis": "Fixed URL",
                 "actions": [{"field": "url", "value": "https://fixed.com"}],
             }), \
             patch.object(service, "_apply_actions", return_value=[{"field": "url", "value": "https://fixed.com"}]), \
             patch.object(service, "_validate_fix", return_value=True), \
             patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls:

            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            await service._run_inner(1)

            # Should only call LLM once since first round succeeded
            service._analyze_with_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_validation_failure(self):
        """Service should retry with failure context when validation fails."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService, _RETRY_DELAY_SECONDS

        config = SourceHealingConfig(enabled=True, max_attempts=3)
        service = SourceHealingService(config)

        snapshot = {"id": 1, "name": "Test", "url": "https://test.com", "rss_url": None,
                    "active": True, "config": {}, "consecutive_failures": 5,
                    "last_check": None, "last_success": None}

        # First round: fail validation. Second round: succeed.
        validate_results = [False, True]
        validate_iter = iter(validate_results)

        with patch.object(service, "_get_source_snapshot", return_value=snapshot), \
             patch.object(service, "_get_error_history", return_value=[]), \
             patch.object(service, "_probe_urls", return_value=[]), \
             patch.object(service, "_analyze_with_llm", return_value={
                 "diagnosis": "Try this",
                 "actions": [{"field": "url", "value": "https://attempt.com"}],
             }), \
             patch.object(service, "_apply_actions", return_value=[{"field": "url", "value": "https://attempt.com"}]), \
             patch.object(service, "_validate_fix", side_effect=lambda *a: next(validate_iter)), \
             patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls, \
             patch("src.services.source_healing_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            await service._run_inner(1)

            # Should have called LLM twice (two rounds)
            assert service._analyze_with_llm.call_count == 2
            # Should have slept between rounds
            mock_sleep.assert_called_once_with(_RETRY_DELAY_SECONDS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestMultiRoundHealing -v`
Expected: FAIL

- [ ] **Step 3: Implement multi-round healing loop**

In `src/services/source_healing_service.py`, add at the top (after imports):

```python
import asyncio
```

Add constant after `_MUTABLE_FIELDS`:

```python
_RETRY_DELAY_SECONDS = 30
```

Replace `_run_inner` method with:

```python
    async def _run_inner(self, source_id: int) -> None:
        db = AsyncDatabaseManager()

        # 1. Gather context (once — shared across rounds)
        source_snapshot = await self._get_source_snapshot(db, source_id)
        if source_snapshot is None:
            logger.warning("[AutoHeal] Source %s not found, skipping", source_id)
            return

        error_history = await self._get_error_history(db, source_id)
        previous_attempts: list[dict] = []

        for round_num in range(1, self.config.max_attempts + 1):
            logger.info(
                "[AutoHeal] Source '%s' (id=%s) — round %d/%d",
                source_snapshot.get("name", "?"), source_id,
                round_num, self.config.max_attempts,
            )

            # 2. Probe URLs (re-probe each round — state may have changed)
            probe_results = await self._probe_urls(source_snapshot)

            # 3. Ask LLM (include previous attempt context if retrying)
            proposed_actions = await self._analyze_with_llm(
                source_snapshot, error_history, probe_results,
                previous_attempts=previous_attempts,
            )

            # 4. Apply actions
            applied = await self._apply_actions(db, source_id, proposed_actions, source_snapshot)

            # 5. Validate
            fix_validated: bool | None = None
            if applied:
                fix_validated = await self._validate_fix(db, source_id)

            # 6. Record audit event
            from src.models.healing_event import HealingEventCreate

            event = HealingEventCreate(
                source_id=source_id,
                round_number=round_num,
                diagnosis=proposed_actions.get("diagnosis", "N/A") if isinstance(proposed_actions, dict) else "N/A",
                actions_proposed=proposed_actions.get("actions", []) if isinstance(proposed_actions, dict) else [],
                actions_applied=applied,
                validation_success=fix_validated,
            )
            await db.create_healing_event(event)

            # 7. Decide: stop or retry
            if fix_validated is True:
                logger.info("[AutoHeal] Source '%s' healed on round %d", source_snapshot.get("name", "?"), round_num)
                return

            if not applied:
                logger.info("[AutoHeal] No actions applied for source '%s', stopping", source_snapshot.get("name", "?"))
                break

            # Record this attempt for next round's LLM context
            previous_attempts.append({
                "round": round_num,
                "diagnosis": proposed_actions.get("diagnosis", "N/A") if isinstance(proposed_actions, dict) else "N/A",
                "actions_applied": applied,
                "validation_result": "FAIL" if fix_validated is False else "NO_CHANGE",
            })

            # Re-read source snapshot (it was modified by _apply_actions)
            source_snapshot = await self._get_source_snapshot(db, source_id)
            if source_snapshot is None:
                break

            # Wait before next round
            if round_num < self.config.max_attempts:
                await asyncio.sleep(_RETRY_DELAY_SECONDS)

        # All rounds exhausted — mark source as healing_exhausted
        logger.warning(
            "[AutoHeal] Source '%s' (id=%s) exhausted %d healing rounds",
            source_snapshot.get("name", "?") if source_snapshot else "?",
            source_id, self.config.max_attempts,
        )
        try:
            await db.update_source(source_id, SourceUpdate(healing_exhausted=True))
        except Exception:
            logger.exception("[AutoHeal] Failed to mark source %s as healing_exhausted", source_id)
```

- [ ] **Step 4: Update _analyze_with_llm to accept previous_attempts**

Change the signature:

```python
    async def _analyze_with_llm(
        self, source_snapshot: dict, error_history: list[dict], probe_results: list[dict],
        previous_attempts: list[dict] | None = None,
    ) -> dict:
```

And update `_build_user_prompt` to accept and append previous attempts:

```python
    @staticmethod
    def _build_user_prompt(
        source_snapshot: dict, error_history: list[dict], probe_results: list[dict],
        previous_attempts: list[dict] | None = None,
    ) -> str:
```

At the end of `_build_user_prompt`, before the final instruction, add:

```python
        if previous_attempts:
            parts.append("")
            parts.append("## Previous Healing Attempts (this session)")
            for attempt in previous_attempts:
                parts.append(
                    f"- Round {attempt['round']}: diagnosis=\"{attempt['diagnosis']}\" "
                    f"actions={json.dumps(attempt['actions_applied'])} "
                    f"result={attempt['validation_result']}"
                )
            parts.append("")
            parts.append(
                "Your previous fix did not work. Propose a DIFFERENT approach. "
                "Do not repeat the same actions."
            )
```

Pass `previous_attempts` through from `_analyze_with_llm` to `_build_user_prompt`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_source_healing_service.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/services/source_healing_service.py tests/services/test_source_healing_service.py
git commit -m "feat: multi-round healing with context carry-forward and audit logging"
```

---

### Task 5: Simplify the healing coordinator

The coordinator no longer manages attempt counting. It dispatches once per qualifying source (active, above threshold, not exhausted). The service handles all retries internally.

**Files:**
- Modify: `src/services/source_healing_coordinator.py`
- Test: `tests/services/test_source_healing_service.py`

- [ ] **Step 1: Write test for simplified coordinator**

Add to `tests/services/test_source_healing_service.py`:

```python
class TestHealingCoordinator:
    """Test the simplified healing coordinator."""

    @pytest.mark.asyncio
    async def test_dispatches_without_incrementing_attempts(self):
        """Coordinator should dispatch tasks without managing attempt counters."""
        from unittest.mock import AsyncMock, patch, MagicMock
        from src.services.source_healing_coordinator import scan_and_trigger_healing
        from src.services.source_healing_config import SourceHealingConfig

        mock_source = MagicMock()
        mock_source.id = 1
        mock_source.name = "TestSource"
        mock_source.consecutive_failures = 10
        mock_source.healing_attempts = 0

        mock_config = SourceHealingConfig(enabled=True, threshold=5, max_attempts=3)

        with patch("src.services.source_healing_coordinator.SourceHealingConfig.load", return_value=mock_config), \
             patch("src.services.source_healing_coordinator.AsyncDatabaseManager") as mock_db_cls, \
             patch("src.worker.celery_app.heal_source") as mock_task:

            mock_db = AsyncMock()
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_source]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.get_session.return_value = mock_session
            mock_db_cls.return_value = mock_db

            await scan_and_trigger_healing()

            # Should dispatch task
            mock_task.delay.assert_called_once_with(1)
            # Should NOT call update_source (no attempt counter increment)
            mock_db.update_source.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestHealingCoordinator -v`
Expected: FAIL (coordinator still increments attempts)

- [ ] **Step 3: Simplify coordinator**

Replace `src/services/source_healing_coordinator.py` content:

```python
"""Periodic coordinator that scans for sources needing AI healing and dispatches tasks."""

import logging

from sqlalchemy import select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import SourceTable
from src.services.source_healing_config import SourceHealingConfig

logger = logging.getLogger(__name__)


async def scan_and_trigger_healing() -> None:
    """Find all sources above the failure threshold and dispatch healing tasks.

    Called by the check_sources_for_healing Celery beat task on a configurable
    schedule. For each qualifying source (active, above threshold, not exhausted),
    dispatches a single heal_source task. The service handles multi-round retries
    internally.
    """
    config = SourceHealingConfig.load()

    if not config.enabled:
        logger.debug("[AutoHeal] Auto-healing is disabled, skipping scan")
        return

    db = AsyncDatabaseManager()
    try:
        async with db.get_session() as session:
            result = await session.execute(
                select(SourceTable).where(
                    SourceTable.consecutive_failures >= config.threshold,
                    SourceTable.active == True,  # noqa: E712
                    SourceTable.healing_exhausted == False,  # noqa: E712
                )
            )
            sources = result.scalars().all()
    except Exception:
        logger.exception("[AutoHeal] Failed to query sources for healing scan")
        return

    if not sources:
        logger.debug("[AutoHeal] No sources above threshold (%d), nothing to heal", config.threshold)
        return

    logger.info(
        "[AutoHeal] Found %d source(s) with consecutive_failures >= %d",
        len(sources), config.threshold,
    )

    from src.worker.celery_app import heal_source

    for source in sources:
        logger.info(
            "[AutoHeal] Dispatching heal task for source '%s' (id=%s), failures=%d",
            source.name, source.id, source.consecutive_failures,
        )
        try:
            heal_source.delay(source.id)
        except Exception:
            logger.exception("[AutoHeal] Failed to dispatch heal task for source %s", source.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_source_healing_service.py::TestHealingCoordinator -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/source_healing_coordinator.py tests/services/test_source_healing_service.py
git commit -m "refactor: simplify coordinator — service owns retry loop"
```

---

### Task 6: Add Langfuse tracing to healing LLM calls

**Files:**
- Modify: `src/services/source_healing_service.py:219-268` (`_analyze_with_llm`)

- [ ] **Step 1: Add Langfuse tracing around the LLM call**

In `_analyze_with_llm`, wrap the `llm.request_chat` call with `trace_llm_call`:

```python
        from src.utils.langfuse_client import trace_llm_call, log_llm_completion, log_llm_error

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            with trace_llm_call(
                name="source_healing",
                model=self.config.model,
                session_id=f"healing_source_{source_snapshot.get('id')}",
                metadata={
                    "source_id": source_snapshot.get("id"),
                    "source_name": source_snapshot.get("name"),
                    "messages": messages,
                },
            ) as generation:
                response = await llm.request_chat(
                    provider=self.config.provider,
                    model_name=self.config.model,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.0,
                    timeout=45.0,
                    failure_context="SourceHealingAgent",
                )

                content = response.get("content", "")
                result = self._parse_llm_response(content)

                log_llm_completion(generation, messages, content)
                return result

        except Exception:
            logger.exception("[AutoHeal] LLM call failed for source %s", source_snapshot.get("id"))
            return {"diagnosis": "LLM call failed", "actions": []}
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/services/test_source_healing_service.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/services/source_healing_service.py
git commit -m "feat: add Langfuse tracing to healing LLM calls"
```

---

### Task 7: Fix dashboard button — greyed out with tooltip when disabled

**Files:**
- Modify: `src/web/templates/dashboard.html:608-616` (button HTML), `~881` (JS visibility), `~949-970` (triggerAIHealing function)
- Modify: `src/web/routes/dashboard.py:278-290` (error fallback)
- Test: Browser verification

- [ ] **Step 1: Update button HTML to support disabled/tooltip state**

In `src/web/templates/dashboard.html`, replace the button HTML (~line 608-616):

```html
            <button id="ai-heal-btn" class="action-btn" style="--btn-clr: #a78bfa; display:none; margin-top:0.6rem;"
                    onclick="triggerAIHealing(this)"
                    data-healing-enabled="false">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" opacity="0.3"/>
                    <path d="M9 12l2 2 4-4"/>
                    <path d="M12 6v1M12 17v1M6 12h1M17 12h1"/>
                </svg>
                Trigger AI Self-Healing
            </button>
```

- [ ] **Step 2: Update JS visibility logic**

Replace the AI Heal Button section (~line 877-882):

```javascript
            // ── AI Heal Button ──
            const healBtn = document.getElementById('ai-heal-btn');
            if (healBtn) {
                const hasFailures = Array.isArray(data.failing_sources) && data.failing_sources.length > 0;
                healBtn.style.display = hasFailures ? 'flex' : 'none';
                healBtn.dataset.healingEnabled = data.healing_enabled ? 'true' : 'false';
                if (!data.healing_enabled) {
                    healBtn.style.opacity = '0.45';
                    healBtn.style.cursor = 'not-allowed';
                    healBtn.title = 'Enable Source Auto-Healing in Settings to use this feature';
                } else {
                    healBtn.style.opacity = '';
                    healBtn.style.cursor = '';
                    healBtn.title = '';
                }
            }
```

- [ ] **Step 3: Update triggerAIHealing to check disabled state**

Replace the `triggerAIHealing` function (~line 949-970):

```javascript
    async function triggerAIHealing(btn) {
        if (btn.dataset.healingEnabled !== 'true') {
            return; // tooltip handles the messaging
        }
        const original = btn.textContent;
        const originalHTML = btn.cloneNode(true);
        btn.disabled = true;
        btn.textContent = 'Dispatching\u2026';
        try {
            const res = await fetch('/api/actions/trigger-healing', { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                btn.textContent = 'Healing Dispatched';
                btn.style.setProperty('--btn-clr', 'var(--d-green)');
                setTimeout(() => { btn.replaceWith(originalHTML); }, 4000);
            } else {
                btn.textContent = data.detail || 'Error';
                btn.style.setProperty('--btn-clr', 'var(--d-red)');
                setTimeout(() => { btn.replaceWith(originalHTML); }, 4000);
            }
        } catch (err) {
            btn.textContent = original;
            btn.style.setProperty('--btn-clr', '#a78bfa');
            btn.disabled = false;
        }
    }
```

- [ ] **Step 4: Add healing_enabled to error fallback in dashboard.py**

In `src/web/routes/dashboard.py`, add to the error return dict (~line 278-290):

```python
            "healing_enabled": False,
```

Add it after `"stats": {...}`.

- [ ] **Step 5: Browser verification**

Open the dashboard in the browser and verify:
1. The "Trigger AI Self-Healing" button is visible when there are failing sources
2. The button appears greyed out (opacity 0.45) when healing is disabled
3. Hovering shows the tooltip "Enable Source Auto-Healing in Settings to use this feature"
4. Clicking the greyed-out button does nothing

- [ ] **Step 6: Commit**

```bash
git add src/web/templates/dashboard.html src/web/routes/dashboard.py
git commit -m "fix: dashboard heal button greyed out with tooltip when disabled"
```

---

### Task 8: Add per-source healing API endpoints

**Files:**
- Modify: `src/web/routes/sources.py` (add 3 new endpoints)
- Create: `tests/api/test_healing_endpoints.py`

- [ ] **Step 1: Write failing tests for new endpoints**

Create `tests/api/test_healing_endpoints.py`:

```python
"""Tests for source healing API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestHealEndpoint:
    """Test POST /api/sources/{id}/heal"""

    @pytest.mark.asyncio
    async def test_heal_returns_404_for_missing_source(self):
        from src.web.routes.sources import api_heal_source
        from fastapi import HTTPException

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_heal_source(999)
            assert exc_info.value.status_code == 404


class TestResetHealingEndpoint:
    """Test POST /api/sources/{id}/reset-healing"""

    @pytest.mark.asyncio
    async def test_reset_clears_healing_flags(self):
        from src.web.routes.sources import api_reset_healing

        mock_source = MagicMock()
        mock_source.id = 1
        mock_source.name = "Test"

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=mock_source)
            mock_db.update_source = AsyncMock(return_value=mock_source)

            result = await api_reset_healing(1)

            assert result["success"] is True
            # Verify update was called with correct reset values
            update_call = mock_db.update_source.call_args
            update_data = update_call[0][1]
            assert update_data.healing_exhausted is False
            assert update_data.healing_attempts == 0


class TestHealingHistoryEndpoint:
    """Test GET /api/sources/{id}/healing-history"""

    @pytest.mark.asyncio
    async def test_returns_healing_events(self):
        from src.web.routes.sources import api_healing_history

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=MagicMock())
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert result["events"] == []
            mock_db.get_healing_events.assert_called_once_with(1, limit=50)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_healing_endpoints.py -v`
Expected: FAIL (endpoints don't exist)

- [ ] **Step 3: Implement the three endpoints**

Add to `src/web/routes/sources.py`:

```python
@router.post("/{source_id}/heal")
async def api_heal_source(source_id: int):
    """Trigger AI healing for a single source."""
    source = await async_db_manager.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    from src.services.source_healing_config import SourceHealingConfig

    config = SourceHealingConfig.load()
    if not config.enabled:
        raise HTTPException(status_code=409, detail="Source auto-healing is disabled in settings.")

    try:
        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")

        task = celery_app.send_task(
            "src.worker.celery_app.heal_source",
            args=[source_id],
            queue="maintenance",
        )

        return {
            "success": True,
            "message": f"Healing dispatched for source '{source.name}'",
            "task_id": task.id,
        }
    except Exception as exc:
        logger.error("API heal source error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{source_id}/reset-healing")
async def api_reset_healing(source_id: int):
    """Reset healing_exhausted and healing_attempts for a source."""
    source = await async_db_manager.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        update_data = SourceUpdate(healing_exhausted=False, healing_attempts=0)
        await async_db_manager.update_source(source_id, update_data)

        return {
            "success": True,
            "message": f"Healing reset for source '{source.name}'",
        }
    except Exception as exc:
        logger.error("API reset healing error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{source_id}/healing-history")
async def api_healing_history(source_id: int):
    """Get healing event audit trail for a source."""
    source = await async_db_manager.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        events = await async_db_manager.get_healing_events(source_id, limit=50)
        return {
            "source_id": source_id,
            "source_name": source.name,
            "events": [e.model_dump(mode="json") for e in events],
        }
    except Exception as exc:
        logger.error("API healing history error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_healing_endpoints.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/sources.py tests/api/test_healing_endpoints.py
git commit -m "feat: add per-source heal, reset-healing, and healing-history endpoints"
```

---

### Task 9: Add heal/reset buttons and slide-out panel to Sources page

**Files:**
- Modify: `src/web/templates/sources.html`

**SECURITY NOTE:** All DOM rendering of healing event data MUST use safe DOM construction (createElement, textContent) — never string interpolation. The LLM diagnosis text is untrusted.

- [ ] **Step 1: Add CSS for heal button, reset button, and slide-out panel**

Add these styles inside the existing `<style>` block (before `</style>` ~line 155):

```css
/* Heal / Reset buttons */
.btn-heal {
  display:inline-flex; align-items:center; gap:0.3rem;
  padding:0.33rem 0.7rem; background:rgba(167,139,250,0.2); color:#c4b5fd;
  border:1px solid rgba(167,139,250,0.3); border-radius:6px; font-size:0.73rem; font-weight:600;
  cursor:pointer; font-family:inherit; transition:background 0.15s, border-color 0.15s;
}
.btn-heal:hover:not(:disabled) { background:rgba(167,139,250,0.35); border-color:rgba(167,139,250,0.5); }
.btn-heal:disabled { opacity:0.4; cursor:not-allowed; }
.btn-heal.btn-reset { background:rgba(234,179,8,0.15); color:#fde047; border-color:rgba(234,179,8,0.25); }
.btn-heal.btn-reset:hover:not(:disabled) { background:rgba(234,179,8,0.3); border-color:rgba(234,179,8,0.4); }

/* Healing exhausted badge */
.heal-exhausted-badge {
  display:inline-flex; align-items:center; gap:0.2rem;
  padding:0.1rem 0.4rem; border-radius:999px; font-size:0.62rem; font-weight:600;
  background:rgba(239,68,68,0.2); color:#fca5a5; border:1px solid rgba(239,68,68,0.3);
}

/* Slide-out panel */
.healing-panel-overlay {
  display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:300;
}
.healing-panel-overlay.open { display:block; }
.healing-panel {
  position:fixed; top:0; right:-480px; width:480px; max-width:90vw; height:100vh;
  background:var(--mlops-card-bg); border-left:1px solid var(--mlops-card-border);
  box-shadow:-8px 0 32px rgba(0,0,0,0.4); z-index:301;
  transition:right 0.25s ease; overflow-y:auto;
}
.healing-panel.open { right:0; }
.healing-panel-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:1rem 1.2rem; border-bottom:1px solid var(--border-muted);
  position:sticky; top:0; background:var(--mlops-card-bg); z-index:1;
}
.healing-panel-title { font-size:1rem; font-weight:600; color:var(--text-primary); }
.healing-panel-close {
  background:none; border:none; color:var(--text-muted-slate); cursor:pointer;
  font-size:1.2rem; padding:0.3rem;
}
.healing-panel-close:hover { color:var(--text-primary); }
.healing-panel-body { padding:1rem 1.2rem; }
.heal-event {
  padding:0.75rem; margin-bottom:0.6rem; border-radius:8px;
  border:1px solid var(--border-muted); background:var(--panel-bg-3,#141c30);
}
.heal-event-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem; }
.heal-event-round { font-size:0.72rem; font-weight:600; color:var(--purple-light); }
.heal-event-time { font-size:0.68rem; color:var(--text-muted-slate); }
.heal-event-diagnosis { font-size:0.78rem; color:var(--text-secondary); margin-bottom:0.3rem; }
.heal-event-actions { font-size:0.72rem; color:var(--text-muted-slate); }
.heal-event-result {
  display:inline-flex; padding:0.1rem 0.4rem; border-radius:999px;
  font-size:0.65rem; font-weight:600;
}
.heal-event-result.pass { background:rgba(34,197,94,0.2); color:#86efac; }
.heal-event-result.fail { background:rgba(239,68,68,0.2); color:#fca5a5; }
.heal-event-result.pending { background:rgba(71,85,105,0.4); color:var(--text-muted-slate); }
```

- [ ] **Step 2: Add heal/reset buttons to source card actions**

In the source card's `.card-actions` div (~line 337-352), add heal/reset buttons after the Collect Now button and before the overflow menu:

```html
            <div class="card-actions">
                <button onclick="collectFromSource({{ source.id }})"
                        class="btn-collect"
                        {% if not source.active %}disabled{% endif %}
                        aria-label="Collect articles from {{ source.name }}">
                    Collect Now
                </button>
                {% if source.consecutive_failures and source.consecutive_failures >= 3 %}
                <button onclick="healSource({{ source.id }})"
                        class="btn-heal"
                        aria-label="Heal {{ source.name }}">
                    Heal
                </button>
                {% endif %}
                {% if source.healing_exhausted %}
                <button onclick="resetHealing({{ source.id }})"
                        class="btn-heal btn-reset"
                        aria-label="Reset healing for {{ source.name }}">
                    Reset
                </button>
                <span class="heal-exhausted-badge">NEEDS ATTENTION</span>
                {% endif %}
                <button onclick="openHealingHistory({{ source.id }}, '{{ source.name|e }}')"
                        class="btn-heal" style="background:transparent; border-color:var(--border-muted); color:var(--text-muted-slate);"
                        aria-label="View healing history for {{ source.name }}">
                    History
                </button>
                <div class="overflow-wrap">
                    <button class="btn-overflow" onclick="toggleOverflow(this)" title="More actions" aria-label="More actions for {{ source.name }}">...</button>
                    <div class="src-dropdown">
                        <button class="dd-item" onclick="openSourceConfig({{ source.id }}, {{ source.lookback_days }}, {{ source.check_frequency // 60 }}, {{ source.config.min_content_length if source.config and source.config.min_content_length else 200 }})">Configure</button>
                        <button class="dd-item" onclick="toggleSourceStatus({{ source.id }})">Toggle Status</button>
                        <button class="dd-item" onclick="showSourceStats({{ source.id }})">Stats</button>
                    </div>
                </div>
            </div>
```

- [ ] **Step 3: Add slide-out panel HTML**

Add before the closing `</div><!-- /container -->` (~line 421):

```html
<!-- Healing History Slide-Out Panel -->
<div id="healingPanelOverlay" class="healing-panel-overlay" onclick="closeHealingPanel()"></div>
<div id="healingPanel" class="healing-panel">
    <div class="healing-panel-header">
        <span class="healing-panel-title" id="healingPanelTitle">Healing History</span>
        <button class="healing-panel-close" onclick="closeHealingPanel()" aria-label="Close">&times;</button>
    </div>
    <div class="healing-panel-body" id="healingPanelBody">
        <div style="color:var(--text-muted-slate); font-size:0.85rem;">Loading...</div>
    </div>
</div>
```

- [ ] **Step 4: Add JavaScript functions for heal, reset, and history panel**

Add to the `<script>` block. **All DOM rendering MUST use safe construction (createElement/textContent) — no string interpolation of data into markup.**

```javascript
// ── Per-source healing ──
async function healSource(sourceId) {
    try {
        showLoadingModal('Healing Source', 'Dispatching AI healing...');
        const response = await fetch('/api/sources/' + sourceId + '/heal', { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            showModal('Healing Dispatched', 'AI healing has been dispatched for this source. Check the healing history panel for results.');
        } else {
            showModal('Healing Failed', result.detail || 'Unknown error');
        }
    } catch (error) {
        showModal('Healing Error', 'Error: ' + error.message);
    }
}

async function resetHealing(sourceId) {
    try {
        showLoadingModal('Resetting Healing', 'Clearing exhausted state...');
        const response = await fetch('/api/sources/' + sourceId + '/reset-healing', { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
            showModal('Healing Reset', 'Healing state has been reset. The source is eligible for healing again.');
            setTimeout(function() { window.location.reload(); }, 1500);
        } else {
            showModal('Reset Failed', result.detail || 'Unknown error');
        }
    } catch (error) {
        showModal('Reset Error', 'Error: ' + error.message);
    }
}

async function openHealingHistory(sourceId, sourceName) {
    var overlay = document.getElementById('healingPanelOverlay');
    var panel = document.getElementById('healingPanel');
    var title = document.getElementById('healingPanelTitle');
    var body = document.getElementById('healingPanelBody');

    title.textContent = 'Healing History \u2014 ' + sourceName;
    body.textContent = 'Loading...';
    overlay.classList.add('open');
    panel.classList.add('open');

    try {
        var response = await fetch('/api/sources/' + sourceId + '/healing-history');
        var data = await response.json();

        if (!response.ok) {
            body.textContent = 'Failed to load history';
            return;
        }

        body.textContent = '';

        if (!data.events || data.events.length === 0) {
            body.textContent = 'No healing events recorded yet.';
            return;
        }

        data.events.forEach(function(ev) {
            var card = document.createElement('div');
            card.className = 'heal-event';

            var header = document.createElement('div');
            header.className = 'heal-event-header';

            var roundEl = document.createElement('span');
            roundEl.className = 'heal-event-round';
            roundEl.textContent = 'Round ' + ev.round_number;
            header.appendChild(roundEl);

            var resultCls = ev.validation_success === true ? 'pass'
                          : ev.validation_success === false ? 'fail' : 'pending';
            var resultLabel = ev.validation_success === true ? 'PASS'
                            : ev.validation_success === false ? 'FAIL' : 'N/A';
            var resultEl = document.createElement('span');
            resultEl.className = 'heal-event-result ' + resultCls;
            resultEl.textContent = resultLabel;
            header.appendChild(resultEl);

            card.appendChild(header);

            var diagEl = document.createElement('div');
            diagEl.className = 'heal-event-diagnosis';
            diagEl.textContent = ev.diagnosis;
            card.appendChild(diagEl);

            var actionsEl = document.createElement('div');
            actionsEl.className = 'heal-event-actions';
            if (ev.actions_applied.length > 0) {
                ev.actions_applied.forEach(function(a) {
                    var line = document.createElement('div');
                    var fieldCode = document.createElement('code');
                    fieldCode.textContent = a.field;
                    line.appendChild(fieldCode);
                    line.appendChild(document.createTextNode(' \u2192 ' + JSON.stringify(a.value)));
                    actionsEl.appendChild(line);
                });
            } else {
                actionsEl.textContent = 'No actions applied';
            }
            card.appendChild(actionsEl);

            var timeEl = document.createElement('div');
            timeEl.className = 'heal-event-time';
            timeEl.textContent = new Date(ev.created_at).toLocaleString();
            card.appendChild(timeEl);

            body.appendChild(card);
        });

    } catch (error) {
        body.textContent = 'Error: ' + error.message;
    }
}

function closeHealingPanel() {
    document.getElementById('healingPanelOverlay').classList.remove('open');
    document.getElementById('healingPanel').classList.remove('open');
}
```

- [ ] **Step 5: Browser verification**

Open the Sources page and verify:
1. Sources with 3+ failures show a "Heal" button
2. Sources with `healing_exhausted=true` show "Reset" button and "NEEDS ATTENTION" badge
3. All sources show a "History" button
4. Clicking "Heal" dispatches a task (or shows the 409 if healing is disabled)
5. Clicking "Reset" clears the exhausted state and reloads
6. Clicking "History" opens the slide-out panel with healing events (safe DOM rendering, no XSS)

- [ ] **Step 6: Commit**

```bash
git add src/web/templates/sources.html
git commit -m "feat: add heal/reset buttons and healing history panel to Sources page"
```

---

### Task 10: Run the migration and verify end-to-end

**Files:**
- Run: `scripts/migrate_add_healing_events.py`

- [ ] **Step 1: Run migration**

```bash
python scripts/migrate_add_healing_events.py
```

Expected: "Created healing_events table"

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/services/test_source_healing_service.py tests/api/test_healing_endpoints.py -v
```

Expected: ALL PASS

- [ ] **Step 3: Verify the app starts**

```bash
# Start the web app and verify no import errors
python -c "from src.web.routes.sources import router; print('Sources router OK')"
python -c "from src.services.source_healing_service import SourceHealingService; print('Healing service OK')"
python -c "from src.database.models import HealingEventTable; print('HealingEventTable OK')"
```

Expected: All print OK

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify source healing v2 integration"
```
