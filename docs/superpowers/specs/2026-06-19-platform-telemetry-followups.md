# Platform Telemetry Follow-ups

Created during phase-one implementation so future platform work is not lost after the
initial Linux/process-generation slice ships.

## Tracked Follow-ups

1. Linux persistence extraction
   - Capability: Linux persistence artifacts.
   - Examples: cron, systemd timers, SSH authorized keys, shell profiles,
     PAM/sudoers, and related persistence locations.
   - Reason deferred: phase one only routes existing extractors by platform capability.

2. macOS Sigma generation
   - Capability: macOS Sigma generation from platform/logsource-ready observables.
   - Reason deferred: phase one keeps macOS observables display-only until rule quality
     and logsource mapping are separately designed.

3. Behavior-family deduplication
   - Capability: cross-platform similarity grouping for behaviorally equivalent rules.
   - Reason deferred: phase one keeps existing platform-specific Sigma canonicalization
     intact and does not weaken duplicate detection semantics.

4. Linux extractor quality review
   - Capability: decide whether shared CmdlineExtract and ProcTreeExtract remain
     sufficient for Linux after reviewed rule volume exists.
   - Reason deferred: phase one needs reviewed Linux output before splitting prompts or
     agents is justified.

5. Backend-specific Sigma tuning
   - Capability: tune Linux/macOS Sigma output for Sysmon for Linux, auditd, Elastic,
     Splunk, CrowdStrike, Defender, or osquery.
   - Reason deferred: phase one targets backend-neutral Sigma first.

6. Review queue platform/logsource filters
   - Capability: filter queued Sigma rules by platform and logsource.
   - Reason deferred: phase one adds only per-rule platform badges, with no reporting or
     filtering beyond per-execution UI.

7. Aggregate platform coverage reporting
   - Capability: reporting over platform coverage, skips, generated rules, and reviewer
     outcomes.
   - Reason deferred: phase one explicitly excludes reporting beyond per-execution UI.

## Promotion Criteria

- Promote Linux persistence extraction if multiple Linux articles contain persistence
  artifacts that current extractors can only surface as generic command/process evidence.
- Split shared command/process prompts only if reviewed Linux rules show materially
  worse edit rate or false-positive behavior than Windows.
- Design behavior-family dedupe only after reviewers repeatedly mark Windows and Linux
  rules as equivalent behavior expressed through different telemetry.
- Add review queue filters only after the platform badge produces enough queue volume
  that reviewers need filtering to work efficiently.
