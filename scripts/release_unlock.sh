#!/usr/bin/env bash

# Unlock the `main` branch so a release merge can land.
#
# `main` is held read-only between releases (see release_lock.sh). Run this
# script to drop the read-only lock, perform the release merge from the
# `europa-*` branch, then run `release_lock.sh` to restore the lock.
#
# This does NOT remove protection. It applies scripts/main_branch_protection.json
# with lock_branch forced false, so the required status checks stay in force
# for the release PR -- the one merge into `main` those checks exist to gate.
# Force-push and deletion stay blocked throughout.
#
# Recovery only: `--allow-force-push` additionally lifts the force-push block,
# for the rollback path in the cut-release skill that resets `main` to the last
# release tag. release_lock.sh re-blocks it.
#
# Requires: gh CLI authenticated with `repo` scope.

set -euo pipefail

REPO=${REPO:-dfirtnt/Huntable-CTI-Studio}
BRANCH=${BRANCH:-main}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROTECTION_JSON=${PROTECTION_JSON:-$SCRIPT_DIR/main_branch_protection.json}
ALLOW_FORCE_PUSH=false

case "${1:-}" in
  "") ;;
  --allow-force-push) ALLOW_FORCE_PUSH=true ;;
  *) echo "Usage: $0 [--allow-force-push]" >&2; exit 2 ;;
esac

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install from https://cli.github.com/" >&2
  exit 1
fi

payload=$(mktemp)
trap 'rm -f "$payload"' EXIT

python3 - "$PROTECTION_JSON" "$ALLOW_FORCE_PUSH" > "$payload" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
data.pop("_comment", None)
data["lock_branch"] = False
data["allow_force_pushes"] = sys.argv[2] == "true"
json.dump(data, sys.stdout)
PYEOF

if [ "$ALLOW_FORCE_PUSH" = true ]; then
  echo "WARNING: lifting the force-push block on ${REPO}:${BRANCH} for recovery. Run release_lock.sh when done." >&2
fi
echo "Dropping read-only lock on ${REPO}:${BRANCH} (required checks stay in force)..."
gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" \
  --input "$payload" \
  -q '"  lock_branch=" + (.lock_branch.enabled|tostring) +
      "  force_pushes=" + (.allow_force_pushes.enabled|tostring) +
      "  deletions="   + (.allow_deletions.enabled|tostring) +
      "  enforce_admins=" + (.enforce_admins.enabled|tostring) +
      "  required_checks=" + (.required_status_checks.contexts|length|tostring)'

echo "Branch $BRANCH is now UNLOCKED on $REPO (PRs merge only with green required checks)."
echo "Run scripts/release_lock.sh after the merge to restore the read-only lock."
