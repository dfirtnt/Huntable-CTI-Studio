#!/usr/bin/env bash

# Lock the `main` branch fully read-only between releases.
#
# Applies scripts/main_branch_protection.json with lock_branch forced true:
#   - direct pushes and PR merges blocked (lock_branch = true)
#   - force-pushes (allow_force_pushes = false)
#   - branch deletion (allow_deletions = false)
#   - required status checks kept on the branch, so release_unlock.sh can
#     drop the lock without dropping the CI gates
# With enforce_admins = true, the protection also applies to repo admins,
# so even `git push --force` from an admin account is rejected.
#
# Requires: gh CLI authenticated with `repo` scope.

set -euo pipefail

REPO=${REPO:-dfirtnt/Huntable-CTI-Studio}
BRANCH=${BRANCH:-main}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROTECTION_JSON=${PROTECTION_JSON:-$SCRIPT_DIR/main_branch_protection.json}

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install from https://cli.github.com/" >&2
  exit 1
fi

payload=$(mktemp)
trap 'rm -f "$payload"' EXIT

python3 - "$PROTECTION_JSON" > "$payload" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
data.pop("_comment", None)
data["lock_branch"] = True
json.dump(data, sys.stdout)
PYEOF

echo "Applying read-only lock to ${REPO}:${BRANCH}..."
gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" \
  --input "$payload" \
  -q '"  lock_branch=" + (.lock_branch.enabled|tostring) +
      "  force_pushes=" + (.allow_force_pushes.enabled|tostring) +
      "  deletions="   + (.allow_deletions.enabled|tostring) +
      "  enforce_admins=" + (.enforce_admins.enabled|tostring) +
      "  required_checks=" + (.required_status_checks.contexts|length|tostring)'

echo "Branch $BRANCH is now LOCKED on $REPO."
