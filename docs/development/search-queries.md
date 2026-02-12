# Search Queries

This document provides example search queries and documentation for the boolean search implementation in Huntable CTI Studio.

## Boolean Search Syntax

The search system supports boolean operators for complex queries:

- **AND**: Both terms must be present (e.g., `ransomware AND encryption`)
- **OR**: Either term must be present (e.g., `malware OR trojan`)
- **NOT**: Exclude term (e.g., `exploit NOT patched`)
- **Parentheses**: Group expressions (e.g., `(ransomware OR malware) AND windows`)
- **Quotes**: Exact phrase match (e.g., `"remote code execution"`)

## Example Windows Threat Queries

### Malware Indicators

```
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

```
("createremotethread" OR "virtualallocex" OR "writeprocessmemory") AND "injection"
```

### Registry Manipulation

```
("HKEY_LOCAL_MACHINE" OR "HKLM" OR "HKEY_CURRENT_USER" OR "HKCU") AND 
("CurrentVersion\\Run" OR "RunOnce" OR "RunServices")
```

### Network Activity

```
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
1. Put most specific/rare terms first
2. Use AND to narrow results
3. Use OR to broaden results
4. Group related terms with parentheses
5. Use NOT sparingly (expensive operation)

## Advanced Patterns

### File System Operations
```
(".tmp" OR ".temp" OR "\\temp\\") AND ("write" OR "create" OR "modify")
```

### Credential Access
```
("lsass" OR "sam" OR "ntds.dit" OR "credential" OR "password") AND 
("dump" OR "extract" OR "steal")
```

### Lateral Movement
```
("psexec" OR "wmi" OR "dcom" OR "rdp" OR "smb") AND 
("lateral" OR "movement" OR "propagation")
```

### Data Staging
```
("rar" OR "zip" OR "7z" OR "archive") AND 
("staging" OR "compress" OR "prepare")
```

## Search Implementation Notes

The boolean search parser handles:
- Operator precedence (NOT > AND > OR)
- Parenthetical grouping
- Quoted phrase matching
- Mixed operators in complex expressions

See `src/utils/search_parser.py` for implementation details.

---

_Last updated: February 2025_
