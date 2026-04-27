# Recovery scenarios for cut-release

Read the failing step's error message first. Jump to the matching section
below.

## release_cut.py failed mid-run

The script computes all edits in memory and writes atomically at the end,
so in practice either all four files change or none of them do. If the
script failed before the commit:

1. `git status` to see which files were modified.
2. `git diff` to see exactly what was changed.
3. Two recovery paths:
   - **Back out entirely**: `git restore .` discards every modification.
   - **Fix and retry**: Edit the offending file, then rerun. The script
     refuses to double-cut (it looks for an existing `[X.Y.Z ...]`
     heading in the CHANGELOG and stops if found), so a failed run
     followed by a successful run on the same version does not corrupt
     the CHANGELOG.

Common root causes:

- **`[Unreleased]` empty** -- nothing to release. Check you are on the
  right branch and the intended work has actually merged to dev-io.
- **`versioning.md` Current Version block does not match the regex** --
  the file has drifted from the canonical three-line shape
  (`**vX.Y.Z "Codename"** - Current stable release`,
  `... Previous stable release`, `... Earlier stable release`). Fix it
  manually to match and rerun.
- **Tag already exists locally** -- `git tag -d vX.Y.Z` to clear, then
  rerun the script.

## Tag pushed but release.yml rejected it

Symptoms: tag is on origin, no GitHub Release was created, Actions
workflow shows a red X on the `verify` or `release` job.

1. Read the failed step's log on GitHub Actions.
2. The typical cause is a `pyproject.toml` / CHANGELOG / tag mismatch.
   Fix the offending file on dev-io (do NOT amend the release commit;
   create a follow-up commit).
3. If `main` is already relocked, run `scripts/release_unlock.sh` before
   attempting to push fixes through.
4. Push dev-io, open a small fixup PR to main, merge it.
5. Delete the bad tag locally and on origin:

   ```bash
   git tag -d vX.Y.Z
   git push origin :refs/tags/vX.Y.Z
   ```

6. Recreate the tag on the new merged commit on main:

   ```bash
   git checkout main
   git pull
   git tag -a vX.Y.Z -m "Codename (X.Y line) -- <summary>"
   git push origin vX.Y.Z
   ```

7. The workflow re-runs. If it passes, the Release is created.
8. `scripts/release_lock.sh` to restore protection.

## Commit accidentally landed on main outside the flow

This is a policy violation per `AGENTS.md`. Recovery is destructive
because it rewrites shared history, and MUST have explicit operator
confirmation -- it is outside the Autonomy Envelope.

1. Identify the stray commit:

   ```bash
   git fetch origin
   LATEST_TAG=$(git describe --tags --abbrev=0 origin/main)
   git log --oneline origin/main ^"$LATEST_TAG"
   ```

2. Cherry-pick it to dev-io so the work is not lost:

   ```bash
   git checkout dev-io
   git pull origin dev-io
   git cherry-pick <sha>
   git push origin dev-io
   ```

3. **Confirm with operator explicitly** before the destructive step.
4. Reset main to the last release tag and force-push:

   ```bash
   scripts/release_unlock.sh
   git checkout main
   git reset --hard "$LATEST_TAG"
   git push origin main --force-with-lease
   scripts/release_lock.sh
   ```

`--force-with-lease` (not `--force`) refuses the push if someone else has
moved origin/main since the last fetch -- a small extra safety against
concurrent drift.

## Need to yank a published release

If a release is defective and must be withdrawn:

```bash
gh release delete vX.Y.Z --yes
git push origin :refs/tags/vX.Y.Z
git tag -d vX.Y.Z
```

Delete the GitHub Release object (not just the tag). Deleting only the
tag leaves the Release orphaned in the UI.

Consider whether a fresh patch version (`vX.Y.Z` where Z is incremented)
is safer than reusing the yanked version. Consumers may have cached the
tag, and re-pushing the same tag ref to point at a different commit is
confusing at best and breaks signature chains at worst.
