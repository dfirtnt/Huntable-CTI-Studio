# Search Queries

This document provides example search queries and documentation for the boolean search implementation in Huntable CTI Studio.

## Boolean Search Syntax

The search system supports boolean operators for complex queries:

- **AND**: Both terms must be present (e.g., `ransomware AND encryption`)
- **OR**: Either term must be present (e.g., `malware OR trojan`)
- **NOT**: Exclude term (e.g., `exploit NOT patched`)
- **Parentheses**: Not functionally supported for grouping; `(` and `)` are silently stripped from the query
- **Quotes**: Exact phrase match (e.g., `"remote code execution"`)

<!-- AUDIT: Accuracy (High) -- verified against src/utils/search_parser.py by running BooleanSearchParser directly: when every term in a query is quoted, AND is silently ignored. Quoted terms are extracted and assigned operator="DEFAULT" *before* the AND/OR scan runs, so a visible "AND" between quoted groups never attaches to anything. Once 2+ terms end up DEFAULT, parse_query's step 6 converts them ALL to OR. Confirmed: `("createremotethread" OR "virtualallocex" OR "writeprocessmemory") AND "injection"` matches an article containing only "createremotethread" and NOT "injection" -- i.e. it behaves as a 4-way OR, not (A OR B OR C) AND D. Every fully-quoted "AND of OR-groups" example below (Process Injection Patterns, Registry Manipulation, Network Activity, and everything under Advanced Patterns) has this problem. To force a real AND, mix at least one unquoted bare word with the AND keyword, e.g. `"createremotethread" OR "virtualallocex" OR "writeprocessmemory" AND injection` (unquoted `injection`), and verify behavior before relying on it. -->
<!-- AUDIT: Candidate for deletion -- if this is a known limitation rather than a bug to fix, consider replacing the affected examples below with syntax that actually AND-narrows results, or removing the AND framing from these examples entirely. -->


## Example Windows Threat Queries

### Malware Indicators

```text
"rundll32" OR "comspec" OR "msiexec" OR "wmic" OR "iex" OR "findstr" OR 
"hkey" OR "hklm" OR "appdata" OR "programdata" OR 
"\\temp\\" OR 
"powershell.exe" OR 
"wbem" OR 
"==" OR 
"c:\\windows\\" OR 
".bat" OR 
".ps1" OR  
".lnk" OR 
"D:\\" OR 
".vhdx" OR 
".iso" OR 
"<Command>" OR 
"\\pipe\\" OR 
"MZ" OR 
"svchost" OR 
"::" OR 
"-accepteula" OR 
"lsass.exe" OR 
"%WINDIR%" OR 
"[.]" OR 
"%wintmp%"
```

### Process Injection Patterns

```text
("createremotethread" OR "virtualallocex" OR "writeprocessmemory") AND "injection"
```

### Registry Manipulation

```text
("HKEY_LOCAL_MACHINE" OR "HKLM" OR "HKEY_CURRENT_USER" OR "HKCU") AND 
("CurrentVersion\\Run" OR "RunOnce" OR "RunServices")
```

### Network Activity

```text
("connect" OR "socket" OR "wininet" OR "urlmon") AND 
("C2" OR "command and control" OR "exfiltration")
```

## Search Tips

### Case Sensitivity
Searches are case-insensitive by default. No need to provide multiple case variations.

### Escaping
- Backslashes in paths should be escaped: `c:\\windows\\`
- Special characters may need quotes: `"[.]"`

### Query Optimization
1. Put the most specific or rarest terms first.
2. Use AND to narrow results.
3. Use OR to broaden results.
4. Use NOT sparingly; it is the more expensive operation.

<!-- AUDIT: Accuracy -- removed "group related terms with parentheses" (previously item 4): this directly contradicted the "Boolean Search Syntax" section above, which states parentheses are stripped and not parsed as grouping. Confirmed against src/utils/search_parser.py: term_pattern excludes "(" and ")", and evaluate_article has no grouping logic. -->

## Advanced Patterns

### File System Operations
```text
(".tmp" OR ".temp" OR "\\temp\\") AND ("write" OR "create" OR "modify")
```

### Credential Access
```text
("lsass" OR "sam" OR "ntds.dit" OR "credential" OR "password") AND 
("dump" OR "extract" OR "steal")
```

### Lateral Movement
```text
("psexec" OR "wmi" OR "dcom" OR "rdp" OR "smb") AND 
("lateral" OR "movement" OR "propagation")
```

### Data Staging
```text
("rar" OR "zip" OR "7z" OR "archive") AND 
("staging" OR "compress" OR "prepare")
```

## Search Implementation Notes

The boolean search parser handles:
- NOT terms as an exclusion filter, checked before AND/OR
- Quoted phrase matching
- Mixed AND/OR terms, evaluated as `all(AND terms) and any(OR terms)` -- there is no real expression-tree precedence, so this is not equivalent to standard boolean grouping (see the AND/quoting caveat above)

Parentheses are stripped rather than parsed as grouping (see note above); do not rely on
them to control evaluation order.

See `src/utils/search_parser.py` for implementation details.

---

_Last updated: 2026-07-03_
_Last reviewed: 2026-09-01_
