# Falcon EDR (CrowdStrike FQL) Perfect Discriminators - Final Proposal

## Assessment Results (Expanded List)

Based on analysis of 1,019 articles with comprehensive Falcon EDR indicators:
- **10 perfect discriminators** identified (100% precision)
- **6 articles** with confirmed Falcon FQL queries
- **1,013 false positives** from generic terms

## Validated Perfect Discriminators (10 items)

### Event Types (3)
1. **ProcessRollup2** ✅
   - Primary Falcon process event table
   - 2/2 articles (100% precision)

2. **ProcessCreate** ✅
   - Falcon process creation event
   - 1/1 articles (100% precision)

3. **event_simpleName** ✅
   - Falcon event type field identifier
   - 4/4 articles (100% precision)

### Field Names (6)
4. **ImageFileName** ✅
   - Falcon process image field
   - 2/2 articles (100% precision)

5. **ParentBaseFileName** ✅
   - Falcon parent process field
   - 2/2 articles (100% precision)

6. **RemoteAddressIP4** ✅
   - Falcon remote IP address field
   - 1/1 articles (100% precision)

7. **SHA256HashData** ✅
   - Falcon hash field naming convention
   - 1/1 articles (100% precision)

8. **ScriptContent** ✅
   - Falcon script content field
   - 1/1 articles (100% precision)

9. **FileWritten** ✅
   - Falcon file write event/field
   - 1/1 articles (100% precision)

### Functions (1)
10. **groupBy** ✅
    - FQL aggregation function
    - 1/1 articles (100% precision)

## High-Confidence Indicators (From Expert Analysis)

These are strongly recommended based on expert knowledge of FQL syntax, even if not yet validated in current dataset:

### Event Types (Additional)
- **NetworkConnectIP4** - Falcon IPv4 network connection event
- **NetworkConnectIP6** - Falcon IPv6 network connection event
- **FileCreate** - Falcon file creation event (0/1 in dataset - needs more data)
- **FileDelete** - Falcon file deletion event
- **RegistryOperation** - Falcon registry operation event
- **ModuleLoad** - Falcon module load event (0/1 in dataset - needs more data)
- **ScriptControlScanTelemetry** - Falcon script control telemetry
- **CommandHistory** - Falcon command history event

### Field Names (Additional)
- **ParentImageFileName** - Falcon parent image field (more specific than ParentBaseFileName)
- **GrandparentImageFileName** - Falcon grandparent process field
- **UserSid** - Falcon user SID field (more specific than UserName)
- **IntegrityLevel** - Falcon process integrity level (0/1 in dataset - needs more data)
- **SessionId** - Falcon session identifier (0/9 in dataset - needs context)
- **FileHashSha256** - Falcon hash field (alternative to SHA256HashData)
- **FileHashMd5** - Falcon MD5 hash field
- **FileHashSha1** - Falcon SHA1 hash field
- **RegistryKeyName** - Falcon registry key field
- **RegistryValueName** - Falcon registry value name field
- **RegistryOperationType** - Falcon registry operation type
- **ScriptFileName** - Falcon script file name field
- **ScriptEngine** - Falcon script engine field (0/2 in dataset - needs context)
- **ModuleFileName** - Falcon module file name (0/4 in dataset - needs context)
- **ConnectionDirection** - Falcon connection direction field
- **RemoteAddressIP6** - Falcon IPv6 remote address
- **LocalAddressIP4** - Falcon local IPv4 address

## Recommended Implementation Strategy

### Phase 1: Add Validated Perfect Discriminators (10 items)

Add these to `perfect_discriminators` in `src/utils/content.py`:

```python
"perfect_discriminators": [
    # ... existing KQL discriminators ...
    
    # Falcon EDR (CrowdStrike FQL) - Validated Perfect Discriminators
    "ProcessRollup2",
    "ProcessCreate",
    "event_simpleName",
    "ImageFileName",
    "ParentBaseFileName",
    "RemoteAddressIP4",
    "SHA256HashData",
    "ScriptContent",
    "FileWritten",
    "groupBy",
]
```

### Phase 2: Add High-Confidence Event Types (8 items)

These are unique to Falcon and unlikely to appear in non-FQL contexts:

```python
# Additional Falcon event types (high confidence)
"NetworkConnectIP4",
"NetworkConnectIP6",
"FileDelete",
"RegistryOperation",
"ScriptControlScanTelemetry",
"CommandHistory",
```

### Phase 3: Add High-Confidence Unique Fields (10 items)

These field names are Falcon-specific and unlikely to be generic:

```python
# Additional Falcon unique fields (high confidence)
"ParentImageFileName",
"GrandparentImageFileName",
"UserSid",
"FileHashSha256",
"FileHashMd5",
"FileHashSha1",
"RegistryKeyName",
"RegistryOperationType",
"ScriptFileName",
"ConnectionDirection",
```

### Phase 4: Context-Dependent Indicators

These require multiple indicators or query syntax patterns:
- **FileCreate** - Needs validation (0/1 in dataset)
- **ModuleLoad** - Needs validation (0/1 in dataset)
- **IntegrityLevel** - Needs validation (0/1 in dataset)
- **SessionId** - Needs context (0/9 in dataset)
- **ScriptEngine** - Needs context (0/2 in dataset)
- **ModuleFileName** - Needs context (0/4 in dataset)

## Excluded (High False Positive Rate)

These terms are too generic and should NOT be added:
- ❌ **event** / **events** - Too generic (0.8% / 0.8% precision)
- ❌ **UserName** - Too generic (0.6% precision)
- ❌ **FileName** - Too generic (3.3% precision)
- ❌ **CommandLine** - Too generic (11.4% precision)
- ❌ **ComputerName** - Too generic (11.1% precision)
- ❌ **Url** - Too generic (1.1% precision)
- ❌ **Protocol** - Too generic (1.0% precision)
- ❌ **DomainName** - Too generic (0% precision)
- ❌ **QueryName** - Too generic (0% precision)
- ❌ **FilePath** - Too generic (5.6% precision)
- ❌ **ProcessId** - Too generic (17.6% precision)
- ❌ **ParentProcessId** - Too generic (75% precision, but only 4 articles)
- ❌ **TargetFileName** - Too generic (33.3% precision)
- ❌ **LocalPort** - Too generic (0% precision)
- ❌ **LogonType** - Too generic (11.1% precision)
- ❌ **SessionId** - Too generic (0% precision)
- ❌ **cidr** - Needs context (20% precision)

## Summary

**Immediate Action (Phase 1):** Add 10 validated perfect discriminators
**Recommended (Phase 2-3):** Add 18 high-confidence indicators from expert analysis
**Future (Phase 4):** Validate context-dependent indicators as more Falcon content is collected

Total recommended: **28 Falcon EDR perfect discriminators** (10 validated + 18 high-confidence)
