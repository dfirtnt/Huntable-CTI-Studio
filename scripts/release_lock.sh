#!/usr/bin/env bash

# Lock the `main` branch fully read-only between releases.
#
# Applies branch protection that blocks:
#   - direct pushes and PR merges (lock_branch = true)
#   - force-pushes (allow_force_pushes = false)
#   - branch deletion (allow_deletions = false)
# With enforce_admins = true, the protection also applies to repo admins,
# so even `git push --force` from an admin account is rejected.
#
# Requires: gh CLI authenticated with `repo` scope.

set -euo pipefail

REPO=${REPO:-dfirtnt/Huntable-CTI-Studio}
BRANCH=${BRANCH:-main}

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install from https://cli.github.com/" >&2
  exit 1
fi

payload=$(mktemp)
trap 'rm -f "$payload"' EXIT

cat > "$payload" <<'EOF'
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": true,
  "allow_fork_syncing": false
}
EOF

echo "Applying read-only lock to ${REPO}:${BRANCH}..."
gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" \
  --input "$payload" \
  -q '"  lock_branch=" + (.lock_branch.enabled|tostring) +
      "  force_pushes=" + (.allow_force_pushes.enabled|tostring) +
      "  deletions="   + (.allow_deletions.enabled|tostring) +
      "  enforce_admins=" + (.enforce_admins.enabled|tostring)'

echo "Branch $BRANCH is now LOCKED on $REPO."
