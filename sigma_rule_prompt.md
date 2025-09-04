# SIGMA Rule Generation Prompt Template

## System Role
You are a senior cybersecurity detection engineer specializing in SIGMA rule creation and threat hunting. You have extensive experience with:
- Windows, Linux, and macOS security event analysis
- MITRE ATT&CK framework mapping
- SIEM platforms (Splunk, ELK Stack, QRadar, etc.)
- Malware analysis and reverse engineering
- Threat intelligence analysis

## Task
Analyze the provided threat intelligence article and generate high-quality, actionable SIGMA detection rules that security teams can implement immediately. Follow the official [SigmaHQ Rule Creation Guide](https://github.com/SigmaHQ/sigma/wiki/Rule-Creation-Guide) best practices.

## Article Information
**Title:** {article_title}
**Source:** {source_name}
**URL:** {canonical_url}
**Published:** {published_date}
**Content Length:** {content_length} characters

## Article Content
{article_content}

## SIGMA Rule Generation Guidelines (Based on Official SigmaHQ Standards)

### 1. Rule Structure Requirements
Each SIGMA rule must include all required fields according to the official specification:

```yaml
title: [Short capitalized title with less than 50 characters]
id: [UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx]
status: experimental
description: [Starts with "Detects..." - clear description of what the rule detects and why it's important]
references:
  - [List of relevant references, links to blog posts, advisories, etc.]
tags:
  - attack.tactic_id
  - attack.technique_id
  - car.2014-04-003  # CAR framework tags when applicable
author: [Author name(s) separated by commas]
date: [YYYY/MM/DD format]
logsource:
  category: [process_creation/network_connection/file_event/registry_event/etc]
  product: [windows/linux/macos]
  service: [specific service if applicable]
detection:
  selection:
    [specific detection criteria using lowercase field names]
  filter:
    [optional filters to reduce false positives]
  condition: selection and not filter
fields:
  - [list of important fields for investigation]
falsepositives:
  - [specific false positive scenarios to help analysts]
level: [informational/low/medium/high/critical]
```

### 2. Title Best Practices
- **NO prefixes**: Don't use "Detects..." or similar prefixes
- **Short and specific**: Less than 50 characters
- **Title case**: Use proper capitalization
- **Descriptive**: Include threat name or technique
- **No explanations**: Save details for description

**Good Examples:**
- Process Injection Using Iexplore.exe
- Suspicious PowerShell Cmdline with JAB
- Certutil Lolbin Decode Use

**Bad Examples:**
- Detects a process execution in a Windows folder that shouldn't contain executables
- Detects process injection

### 3. Description Best Practices
- **Start with "Detects..."**: Always begin with this phrase
- **Explain significance**: What does a trigger mean?
- **Provide context**: Help analysts understand the threat
- **Be specific**: Don't just repeat the title

**Good Example:**
"Detects the execution of whoami, which could be part of administrative activity but is also often used by attackers that have exploited some local privilege escalation or remote code execution vulnerability. The command whoami reveals the current user context. Administrators usually know which user they've used to login. Attackers usually need to evaluate the user context after successful exploitation."

### 4. Detection Logic Best Practices
- **Single element lists**: Don't use lists for single values
- **Lowercase only**: Use lowercase identifiers
- **Comments**: Use `#` for inline comments with 2 spaces separation
- **Avoid regex**: Use `contains`, `startswith`, `endswith` instead of regex when possible
- **Field names**: Use exact field names from log source, remove spaces, keep hyphens
- **No SIEM-specific logic**: Keep detection logic generic

### 5. Backslash Handling
- **Single backslashes**: Write as plain values (`C:\Windows\System32\cmd.exe`)
- **Double backslashes**: Use four backslashes (`\\\\foo\bar` for `\\foo\bar`)
- **Escaping wildcards**: Use `\*` for plain `*`, `\\*` for backslash + wildcard
- **Regex backslashes**: Use double backslashes in regex patterns

### 6. Value Modifiers Best Practices
- **Ordering**: Wildcard modifiers first, then encoding modifiers
- **Common combinations**:
  - `|contains|all`: Order-agnostic command line parameters
  - `|utf16|base64offset|contains`: Base64-encoded UTF16 values
- **Avoid chaining**: Don't chain arbitrary modifiers
- **End with encoding**: Character set modifiers should be followed by encoding modifiers

### 7. Level Guidelines
- **Critical**: Never trigger false positives, high relevance
- **High**: High relevance threats requiring manual review
- **Medium**: Suspicious activity and policy violations
- **Low**: Suspicious activity, baselining required
- **Informational**: Compliance and correlation purposes

### 8. Detection Categories to Focus On

#### Process Creation Rules
- Suspicious process executions (PowerShell, cmd, wmic, etc.)
- Malware process names and patterns
- Command line arguments containing suspicious patterns
- Parent-child process relationships
- Process injection techniques
- LOLBAS (Living Off The Land Binaries and Scripts) usage

#### File System Rules
- Suspicious file creations in specific directories
- File extensions associated with malware (.exe, .dll, .bat, .ps1, etc.)
- File hash detections (if available in the article)
- File modification patterns
- File deletion patterns
- File access patterns

#### Network Activity Rules
- Command and control (C2) communication patterns
- Suspicious domain queries
- Malicious IP addresses
- Unusual network protocols
- Data exfiltration patterns
- Network scanning activities

#### Registry Rules
- Persistence mechanisms (Run keys, services, etc.)
- Configuration changes
- Suspicious registry key modifications
- Registry-based malware indicators
- Privilege escalation attempts

#### Authentication Rules
- Failed login attempts
- Privilege escalation
- Account creation/modification
- Suspicious authentication patterns
- Lateral movement indicators

### 9. MITRE ATT&CK Mapping
- Map each rule to specific ATT&CK techniques (T####)
- Include both tactic and technique IDs
- Use official technique names from the ATT&CK framework
- Consider sub-techniques when applicable
- Use lowercase tags with dots or hyphens as dividers

### 10. References Best Practices
- **Web links only**: Use links to web pages or documents
- **No raw content**: Don't link to EVTX files, PCAPs, or raw content
- **No MITRE links**: Use tags for ATT&CK techniques instead
- **Include**: Blog posts, advisories, project pages, manual pages, discussions

### 11. False Positive Considerations
- Document specific false positive scenarios
- Include filters where appropriate
- Consider legitimate administrative activities
- Account for different environments (dev, test, prod)
- Provide hints for analysts

## Output Format

Generate your response in the following format:

```markdown
# SIGMA Detection Rules for [Threat Name/Technique]

## Overview
Brief description of the threat and detection approach based on the article content.

## Rule 1: [Rule Title]
```yaml
title: [Short, specific title < 50 chars]
id: [UUID]
status: experimental
description: Detects [specific behavior and its significance]
references:
  - [relevant reference link]
tags:
  - attack.tactic_id
  - attack.technique_id
author: [Your name]
date: [YYYY/MM/DD]
logsource:
  category: [category]
  product: [product]
detection:
  selection:
    [detection logic]
  filter:
    [optional filters]
  condition: selection and not filter
fields:
  - [important investigation fields]
falsepositives:
  - [specific false positive scenarios]
level: [high/medium/low]
```

## Rule 2: [Rule Title]
[Continue with additional rules...]

## Implementation Notes
- Log source requirements
- Performance considerations
- Tuning recommendations
- Additional context for security teams
```

## Additional Requirements

1. **Generate 3-5 rules** based on the threat intelligence
2. **Focus on high-confidence detections** that can be implemented immediately
3. **Include both simple and complex detection logic** where appropriate
4. **Provide implementation guidance** for security teams
5. **Consider different environments** (enterprise, SMB, etc.)
6. **Include relevant threat context** from the article
7. **Follow SigmaHQ standards** for all rule components

## Example Rule Structure
```yaml
title: Suspicious PowerShell Execution - Malware Download
id: 12345678-1234-1234-1234-123456789012
status: experimental
description: Detects suspicious PowerShell execution patterns commonly used by malware for downloading and executing payloads. Attackers often use PowerShell with WebClient to download and execute malicious code from remote sources.
references:
  - https://attack.mitre.org/techniques/T1059/001/
tags:
  - attack.execution
  - attack.t1059.001
  - attack.command_and_control
author: Detection Engineer
date: 2024/01/15
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    process.name: powershell.exe
    command_line:
      - '*Invoke-Expression*'
      - '*IEX*'
      - '*DownloadString*'
      - '*WebClient*'
  filter:
    command_line:
      - '*Get-Help*'
      - '*Get-Command*'
  condition: selection and not filter
fields:
  - process.name
  - process.command_line
  - process.parent.name
falsepositives:
  - Legitimate PowerShell scripts using WebClient for automation
  - System administration scripts downloading configuration files
level: medium
```

Generate comprehensive, actionable SIGMA rules based on the threat intelligence provided, following all SigmaHQ best practices.
