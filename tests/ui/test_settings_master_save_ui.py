"""
Regression test: the master 'Save Settings' button at the bottom of /settings
must persist every field that each per-card save button would persist.

Specifically guards against the bug where the master save silently omitted
SOURCE_HEALING_ENABLED from its payload, so users unchecked the box, clicked
the big bottom button, got a success toast, and then saw the checkbox revert
on refresh because the value was never sent to the server.

This test edits two sections (Source Auto-Healing and the Auto-Trigger Hunt
Score Threshold) and clicks ONLY the master #saveSettings button -- never the
per-card buttons -- then reloads and asserts both values persisted.
"""

import os

import pytest
from playwright.sync_api import Page


def _base_url():
    return os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")


def _expand_all_panels(page: Page) -> None:
    """Open every collapsible panel so form inputs are interactable."""
    page.evaluate(
        """() => {
            document.querySelectorAll('[data-collapsible-panel]').forEach(h => {
                const id = h.dataset.collapsiblePanel;
                const content = document.getElementById(id + '-content');
                if (content) content.classList.remove('hidden');
            });
        }"""
    )


def _read_state(page: Page) -> dict:
    return page.evaluate(
        """() => ({
            healing: document.getElementById('sourceHealingEnabled').checked,
            threshold: document.getElementById('autoTriggerHuntScoreThreshold').value,
        })"""
    )


def _wait_for_settings_hydrated(page: Page) -> None:
    """Wait for loadSettings() to finish all async fetches (body gets data-settings-hydrated)."""
    page.wait_for_function(
        "() => document.body.dataset.settingsHydrated === 'true'",
        timeout=15000,
    )


@pytest.mark.ui
class TestSettingsMasterSavePersistence:
    """The master Save button must persist every field across every section."""

    def test_master_save_persists_healing_checkbox_and_threshold(self, fresh_page: Page):
        """Edit two sections, click only #saveSettings, reload, assert persistence."""
        base_url = _base_url()
        page = fresh_page

        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")
        _wait_for_settings_hydrated(page)
        _expand_all_panels(page)

        original = _read_state(page)

        # Flip both values.
        target_healing = not original["healing"]
        original_threshold = float(original["threshold"])
        target_threshold = 73 if original_threshold != 73 else 64

        page.evaluate(
            """([newThreshold]) => {
                const thr = document.getElementById('autoTriggerHuntScoreThreshold');
                thr.value = String(newThreshold);
                thr.dispatchEvent(new Event('input', {bubbles:true}));
                thr.dispatchEvent(new Event('change', {bubbles:true}));
            }""",
            [target_threshold],
        )
        # Click the checkbox via DOM label-click path (matches real user click).
        checkbox = page.locator("#sourceHealingEnabled")
        checkbox.click()

        assert _read_state(page) == {
            "healing": target_healing,
            "threshold": str(target_threshold),
        }, "Pre-save UI state did not match the requested changes"

        # THE KEY ASSERTION: click ONLY the bottom master Save button.
        # Do not click per-card save buttons. If the master save forgets any field,
        # this test will catch it on reload.
        page.locator("#saveSettings").click()

        # Give async PUTs a beat to finish.
        page.wait_for_timeout(1500)

        # Full page reload -- this is the Cmd+R the user does.
        page.reload()
        page.wait_for_load_state("load")
        _wait_for_settings_hydrated(page)
        _expand_all_panels(page)

        after = _read_state(page)

        try:
            assert after["healing"] == target_healing, (
                f"Source Auto-Healing checkbox reverted after master save + reload: "
                f"expected {target_healing}, got {after['healing']}. "
                f"Master Save likely omitted SOURCE_HEALING_ENABLED from its payload."
            )
            assert float(after["threshold"]) == float(target_threshold), (
                f"Auto-trigger hunt score threshold reverted after master save + reload: "
                f"expected {target_threshold}, got {after['threshold']}."
            )
        finally:
            # Restore original state regardless of assertion result, via master save.
            page.evaluate(
                """([origHealing, origThreshold]) => {
                    const thr = document.getElementById('autoTriggerHuntScoreThreshold');
                    thr.value = String(origThreshold);
                    thr.dispatchEvent(new Event('input', {bubbles:true}));
                    thr.dispatchEvent(new Event('change', {bubbles:true}));
                    const cb = document.getElementById('sourceHealingEnabled');
                    if (cb.checked !== origHealing) cb.click();
                }""",
                [original["healing"], original_threshold],
            )
            page.locator("#saveSettings").click()
            page.wait_for_timeout(1500)
