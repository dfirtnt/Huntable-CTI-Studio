---
name: Deprecate mobile features
overview: Deprecate mobile features by disabling them by default via an env flag (ENABLE_MOBILE_UI). No files are deleted; mobile code remains in the repo but does not run unless the flag is set. Tests and docs are updated to reflect the default and how to re-enable.
todos: []
isProject: false
---

# Deprecate/Disable Mobile Features (No Deletions)

## Approach

- **Feature flag:** `ENABLE_MOBILE_UI` (env var). Default: unset / `false` → mobile UI off. Set to `true` to re-enable.
- **No file deletions.** All mobile JS, tests, Docker compose, and scripts stay in the repo. Optional: add a short "DEPRECATED" comment at the top of mobile-only assets.
- **Templates:** Only load mobile script and render mobile nav when the flag is true. Article detail only runs mobile touch/instruction logic when the flag is true.
- **Tests:** Skip mobile-specific tests when `ENABLE_MOBILE_UI` is not true (or document that mobile tests require the flag).

---

## 1. Backend: expose flag to templates

**File:** [src/web/dependencies.py](src/web/dependencies.py)

- Add: `MOBILE_UI_ENABLED = os.getenv("ENABLE_MOBILE_UI", "false").lower() == "true"`.
- Add to Jinja2 globals so every template can use it:
  - `templates.env.globals["mobile_ui_enabled"] = MOBILE_UI_ENABLED`
- Export `MOBILE_UI_ENABLED` in `__all__` if anything else needs it.

No other backend or route changes; template context is enough.

---

## 2. App shell: [src/web/templates/base.html](src/web/templates/base.html)

- **Script:** Include `mobile-simple.js` only when mobile is enabled:
  - `{% if mobile_ui_enabled %}<script src="/static/js/mobile-simple.js"></script>{% endif %}`
- **Hamburger button:** Wrap the whole `<button id="mobile-nav-toggle" ...>...</button>` block in `{% if mobile_ui_enabled %}...{% endif %}`.
- **Mobile menu div:** Wrap the `<div id="mobile-nav-menu" ...>...</div>` block in `{% if mobile_ui_enabled %}...{% endif %}`.
- **Desktop nav visibility:** When mobile is disabled, always show the main nav. Change the main nav container from `class="hidden md:flex ..."` to:
  - `class="{% if mobile_ui_enabled %}hidden md:flex{% else %}flex{% endif %} items-center justify-center gap-8 ..."` (and keep the rest of the classes).

The existing "Mobile nav toggle" script can stay; when the flag is false the toggle/menu elements are absent and the script no-ops (early return when `!toggle || !menu`).

---

## 3. Article detail: [src/web/templates/article_detail.html](src/web/templates/article_detail.html)

- **Global for JS:** Early in the script section (or in the block that runs on load), set a variable so inline JS can branch:
  - `window.MOBILE_UI_ENABLED = {{ 'true' if mobile_ui_enabled else 'false' }};`
- **Call sites:** Guard the two places that call `addMobileModalHandlers(modal, ...)` with:
  - `if (window.MOBILE_UI_ENABLED) addMobileModalHandlers(modal, expandedStart, expandedEnd);` (and the other call with `start, end`).
- **iPhone instructions:** Guard the call to `addiPhoneInstructions()` with:
  - `if (window.MOBILE_UI_ENABLED) addiPhoneInstructions();`

Do not remove the `addMobileModalHandlers` or `addiPhoneInstructions` implementations; they simply are not called when the flag is false. The `#mobile-annotation-instructions` CSS can stay (harmless when the element is not added).

---

## 4. Tests: skip when mobile is disabled

- **pytest.ini / conftest:** Add a skip condition for mobile tests when `ENABLE_MOBILE_UI` is not `true`. For example in [tests/conftest.py](tests/conftest.py) (or in the mobile test module), define:
  - `skip_mobile = not os.getenv("ENABLE_MOBILE_UI", "").lower() == "true"`, and use `@pytest.mark.skipif(skip_mobile, reason="ENABLE_MOBILE_UI not set")` for mobile-only tests.
- **tests/ui/test_mobile_responsiveness_ui.py:** Add a module-level skipif so the whole module is skipped when `ENABLE_MOBILE_UI` is not true (e.g. decorate the class or add a pytestmark).
- **tests/ui/test_ui_flows.py:** For `TestResponsiveDesign`, add the same skipif so `test_mobile_viewport` and `test_tablet_viewport` are skipped when mobile is disabled.
- **tests/ui/test_accessibility_comprehensive_ui.py:** Skip `test_responsive_text_layout` when `ENABLE_MOBILE_UI` is not true.
- **tests/ui/test_dashboard_comprehensive_ui.py:** In `test_chart_responsive_behavior`, either skip the whole test when mobile is disabled or only run the desktop viewport part when disabled (no 375x667).
- **tests/ui/test_rag_chat_ui.py:** In `test_chat_responsive_design`, skip the mobile (and optionally tablet) viewport steps when mobile is disabled, or skip the test.

Recommendation: one shared `skip_mobile` in conftest and use it in all of the above so CI stays green without the flag and mobile tests run only when `ENABLE_MOBILE_UI=true`.

---

## 5. Documentation

- **[docs/development/web-app-testing.md](docs/development/web-app-testing.md):** Add a short note at the top (or in the responsive section) that mobile/responsive testing is deprecated and disabled by default; to run mobile tests or use mobile UI, set `ENABLE_MOBILE_UI=true`. Keep existing responsive/mobile examples as “when mobile is enabled.”
- **CHANGELOG:** Add an entry: mobile UI and related tests are deprecated and disabled by default; set `ENABLE_MOBILE_UI=true` to re-enable.
- **Optional:** In [README](README.md) or a config doc, mention `ENABLE_MOBILE_UI` in the environment variables section.

---

## 6. Optional (non-blocking)

- Add a one-line comment at the top of `mobile-simple.js`, `mobile-annotation-init.js`, `annotation-manager-mobile.js`, and `mobile-enhancement-force.js`: e.g. `/* DEPRECATED: Loaded only when ENABLE_MOBILE_UI=true */`.
- Same for [tests/ui/test_mobile_responsiveness_ui.py](tests/ui/test_mobile_responsiveness_ui.py) and [tests/ui/mobile_playwright_config.py](tests/ui/mobile_playwright_config.py) in the docstring.
- Leave [docker-compose.mobile-simple.yml](docker-compose.mobile-simple.yml) and the mobile scripts in `scripts/` as-is; they remain valid when someone turns the flag on.

---

## Verification

- With `ENABLE_MOBILE_UI` unset or `false`: load dashboard and article detail; main nav is always visible, no hamburger, no mobile script, no mobile modal/iPhone instructions. Run full UI suite; mobile tests are skipped, rest pass.
- With `ENABLE_MOBILE_UI=true`: same as today (hamburger, mobile menu, mobile script, touch handlers and iPhone instructions). Run UI suite with the flag; mobile tests run (fix any that fail due to existing issues).

---

## Summary


| Area                | Action                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------ |
| Backend             | Add `MOBILE_UI_ENABLED` and expose as Jinja2 global `mobile_ui_enabled` in dependencies.py |
| base.html           | Conditional script include, conditional hamburger + mobile menu, conditional nav class     |
| article_detail.html | Set `window.MOBILE_UI_ENABLED`, guard 3 call sites with the flag                           |
| Tests               | Skip mobile/responsive tests when `ENABLE_MOBILE_UI != true` (conftest + skipif)           |
| Docs                | Note deprecation and `ENABLE_MOBILE_UI` in web-app-testing + CHANGELOG                     |
| Files               | No deletions; optional DEPRECATED comments in mobile assets                                |


No new files; only small, localized edits. Re-enabling is a single env var.