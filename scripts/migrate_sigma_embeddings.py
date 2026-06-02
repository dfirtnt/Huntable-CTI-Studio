#!/usr/bin/env python3
"""
DEPRECATED (2026-06-02): superseded and non-functional. Do not use.

This was a one-off migration that re-indexed SIGMA rules with per-section
embeddings (title/description/tags/logsource/detection_structure/detection_fields)
via the LMStudio embedding client. It is obsolete on every axis:

- The per-section embedding columns it wrote (`title_embedding`,
  `description_embedding`, `tags_embedding`, `detection_structure_embedding`,
  `detection_fields_embedding`) were dropped from `sigma_rules` on 2026-06-01 —
  only `embedding` (whole-rule) and `logsource_embedding` (combined "signature")
  are scored now.
- It read section keys (`logsource`/`detection_structure`/`detection_fields`)
  that `create_section_embeddings_text` no longer returns, so it raised KeyError.
- It used the deprecated LMStudio embedding path rather than the current
  e5-base-v2 `EmbeddingService`.

Use the live CLI instead:

    ./run_cli.sh sigma index-embeddings

The original implementation is preserved in git history (pre-2026-06-02) if a
historical reference is ever needed.
"""

import sys


def main() -> None:
    sys.stderr.write(
        "DEPRECATED: scripts/migrate_sigma_embeddings.py is superseded and non-functional "
        "(it targets removed per-section embedding columns). "
        "Use: ./run_cli.sh sigma index-embeddings\n"
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
