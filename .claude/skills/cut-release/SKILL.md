---
name: cut-release
description: >
  Interactive walkthrough for cutting a new release of Huntable CTI Studio.
  Use this skill whenever the user says "cut a release", "ship a release",
  "tag a version", "bump the version", "new release", "do the release",
  "release vX.Y.Z", "ship v5.4.0", "time to release", or otherwise signals
  they want to move code from dev-io to main and publish a tagged GitHub
  Release. Drives scripts/release_cut.py plus the branch unlock/lock dance
  and the tag push that triggers .github/workflows/release.yml, pausing at
  every irreversible step so the operator can confirm.
---

# Cut Release

Walks the operator through the release flow documented in `AGENTS.md`
(sections "Release branch protection" and "Release tagging convention").
Those sections are authoritative; this skill automates the mechanics and
enforces the checkpoints.

## Core invariants

Hold these in mind throughout:

- **`main` is read-only between releases** via GitHub branch protection
  (`lock_branch`, `enforce_admins`, no force push, no deletions). Feature
  work lives on `dev-io`. `main` only moves during release cuts.
- **Canonical tag format is `vMAJOR.MINOR.PATCH` only.** The codename lives
  in the annotated tag *message* and the CHANGELOG heading, never in the
  tag name.
- **`pyproject.toml` `[project].version` is the single source of truth.**
  Everything else mirrors it.
- **Never push silently.** Every network-side-effect step (unlock, push
  dev-io, push tag, relock) gets an explicit operator confirm.

## Phase 1: Gather release parameters

Ask the operator for three things. Confirm all three before touching
anything.

1. **Version** in `MAJOR.MINOR.PATCH` form. Read the current version from
   `pyproject.toml` `[project].version` and help decide the bump type:
   - **Patch** (`5.3.0 -> 5.3.1`): bug fixes only.
   - **Minor** (`5.3.0 -> 5.4.0`): new features, backward compatible.
   - **Major** (`5.3.0 -> 6.0.0`): breaking changes or significant
     architectural shift.

2. **Codename**:
   - **Major bump**: pick a new planetary moon. Show the operator the
     "Available Planetary Moon Names" section in
     `docs/reference/versioning.md`, and exclude names already used in the
     Version History block (historically: Callisto, Ganymede, Kepler,
     Copernicus, Tycho). Good fresh candidates: Triton, Europa, Io, Titan,
     Enceladus.
   - **Minor or patch bump**: reuse the current codename. Read it from the
     first line under `## Current Version` in `docs/reference/versioning.md`.

3. **One-line summary** for the annotated tag message. Short, declarative.
   This goes into `git tag -m` and is what `git log --oneline` shows next
   to the tag. Example: `"SBOM provenance + release automation"`.

This is the last easy exit point. After Phase 3 commits land, backing out
gets fiddly.

## Phase 2: Preflight

Run these checks via Bash. Halt with a clear diagnostic on the first
failure.

```bash
git rev-parse --abbrev-ref HEAD          # must equal: dev-io
git status --porcelain                    # must be empty
git fetch origin dev-io
git rev-parse HEAD                        # must equal the FETCH_HEAD sha
git rev-parse FETCH_HEAD
```

Also check that `docs/CHANGELOG.md` `[Unreleased]` contains real content
(at least one `###` subsection between the `## [Unreleased]` heading and
the next `## [` heading). If `[Unreleased]` is empty, there is nothing to
release -- abort and tell the operator.

`scripts/release_cut.py` repeats these preflight checks, but catching
failures earlier keeps the flow tight.

## Phase 2b: Security Review

Before touching the repo, invoke the built-in security review skill:

```
/security-review
```

This scans the diff between `dev-io` and `main` for common vulnerability
classes (injection, auth gaps, exposed secrets, insecure deserialization,
etc.). Review every finding. You have two options:

- **Fix and commit on dev-io**, then loop back to Phase 2 preflight to
  re-confirm the branch is clean and up-to-date.
- **Accept the risk** with an explicit operator decision. Document the
  accepted risk in a follow-up commit or the CHANGELOG before proceeding.

Do not proceed to Phase 3 until all findings are resolved or explicitly
accepted.

## Phase 3: Run release_cut.py

Execute:

```bash
scripts/release_cut.py <version> <Codename> --summary "<summary>"
```

This does every repo-local edit atomically, does NOT push, and stops
after creating the local commit and annotated tag. Specifically:

- Bumps `pyproject.toml` `[project].version`.
- Rolls `docs/CHANGELOG.md` `[Unreleased]` into a dated
  `[X.Y.Z "Codename"] - YYYY-MM-DD` section, inserting a fresh empty
  `[Unreleased]` above.
- Shifts `docs/reference/versioning.md` Current/Previous/Earlier labels
  and inserts a Version History stub entry (with TODO markers for the
  operator to fill in later).
- Updates the version line in `README.md`.
- Runs `scripts/verify_release_tag.py vX.Y.Z` as a pre-flight guard.
- Commits as `release: vX.Y.Z "Codename"`.
- Creates annotated tag `vX.Y.Z` with the operator's summary.

If the script fails, read the error first before retrying. Common causes:

- `[Unreleased]` empty.
- `versioning.md` Current Version block does not match the canonical
  three-line shape.
- Tag already exists locally (`git tag -d vX.Y.Z` to clear, then rerun).

If edits are on disk but commit did not happen, `git diff` to review and
`git restore .` to back out cleanly.

## Phase 4: Review the commit and tag

Show the operator:

```bash
git show HEAD --stat
git show vX.Y.Z
```

Ask for explicit approval to continue. This is the last cheap-exit point.
Backing out at this stage:

```bash
git tag -d vX.Y.Z
git reset --hard HEAD~1
```

Things to look at before approving:

- `pyproject.toml` version matches the intended target.
- `docs/CHANGELOG.md` has the new dated section and a fresh empty
  `[Unreleased]`.
- `docs/reference/versioning.md` Current Version block shifted correctly,
  and a new Version History entry exists. The operator may want to fill in
  the Significance / Features TODOs on a follow-up commit before merging
  to main. Do not amend the release commit on the operator's behalf.

## Phase 5: Unlock main

```bash
scripts/release_unlock.sh
```

Removes branch protection on `main`. From this point on, `main` is
write-enabled and you should move through the remaining phases without
long pauses. Do not leave `main` unlocked overnight.

## Phase 6: Push dev-io and open PR

```bash
git push origin dev-io
```

Direct the operator to open a PR manually on GitHub:

- Base: `main`
- Compare: `dev-io`
- Title: `release: vX.Y.Z "Codename"` (match the commit subject)

Wait for the operator to report the PR is open. Then wait for all CI
checks to go green. If CI fails, stop -- fix on dev-io, push a follow-up
commit, re-check. Do not merge with red CI.

## Phase 7: Merge the PR

The operator merges the PR on GitHub using a **merge commit** (not squash,
not rebase). Reason: the annotated tag points at a specific commit SHA.
Squash would rewrite that SHA out of existence and detach the tag from
main.

Wait for the operator to confirm the PR is merged. Optionally update
local main:

```bash
git fetch origin
```

## Phase 8: Push the tag

```bash
git push origin vX.Y.Z
```

This triggers `.github/workflows/release.yml`, which:

1. Re-runs `scripts/verify_release_tag.py` against the pushed tag.
2. Extracts the `[X.Y.Z]` section from `docs/CHANGELOG.md` via
   `scripts/extract_changelog_section.py`.
3. Creates a GitHub Release titled `vX.Y.Z "Codename"` with the CHANGELOG
   section as the body.

Give the operator the Actions URL and wait for the workflow to complete:

```
https://github.com/dfirtnt/Huntable-CTI-Studio/actions
```

If the workflow fails, see `references/recovery.md` section "Tag pushed
but release.yml rejected it". Do not proceed to Phase 9 until the Release
is published.

## Phase 9: Relock main

```bash
scripts/release_lock.sh
```

Restores the read-only lock on `main`. The release flow is complete.

## Phase 10: Sanity checks

Walk the operator through these:

- GitHub Release visible at
  `https://github.com/dfirtnt/Huntable-CTI-Studio/releases/tag/vX.Y.Z`.
- Release notes body matches the `[X.Y.Z]` CHANGELOG section.
- Release title includes the codename.
- Tag visible remotely: `git ls-remote --tags origin | grep vX.Y.Z`.
- `main` is locked: a test push (`git push origin main --force-with-lease`
  from a scratch branch) must be rejected. Skip this if the operator does
  not want to exercise it.

## Recovery and special cases

See `references/recovery.md` for:

- `release_cut.py` failed mid-run.
- Tag pushed but release.yml rejected it.
- Commit accidentally landed on main outside the flow.
- Need to yank a published release.

## Scope limitations

This skill covers standard patch / minor / major releases. Release
candidates (`vX.Y.Z-rc.N` on a `release/vMAJOR` branch) need additional
steps beyond this walkthrough. See `AGENTS.md` "Release tagging convention"
for the RC pattern. RC flow is not yet covered here -- when you hit that
case, walk through manually and consider extending this skill.
