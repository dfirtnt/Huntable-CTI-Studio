# Falcon EDR (CrowdStrike FQL) Perfect Discriminators

## Assessment Results

Based on analysis of 857 articles containing potential Falcon EDR indicators:
- **8 perfect discriminators** identified (100% precision)
- **8 articles** with confirmed Falcon FQL queries
- **849 false positives** from generic terms

## Proposed Perfect Discriminators

### Event Types (FQL-Specific)
These are unique to Falcon's FQL query language:

1. **ProcessRollup2** ✅ (2/2 articles - perfect)
   - Primary process event table in Falcon
   - Distinct from generic "process" terminology

2. **event_simpleName** ✅ (4/4 articles - perfect)
   - Falcon-specific field for event type identification
   - Unique syntax pattern

3. **FileWritten** ✅ (1/1 articles - perfect)
   - Falcon event type for file write operations
   - More specific than generic "file" terms

### Field Names (Falcon-Specific)
These field names are unique to Falcon's data model:

4. **ImageFileName** ✅ (2/2 articles - perfect)
   - Falcon-specific field (vs generic "filename" or "image")
   - Distinct from Windows "ImageFile" terminology

5. **ParentBaseFileName** ✅ (2/2 articles - perfect)
   - Falcon-specific parent process field
   - More specific than generic "parent" terms

6. **SHA256HashData** ✅ (1/1 articles - perfect)
   - Falcon's specific hash field naming convention
   - Distinct from generic "SHA256" or "hash" terms

7. **RemoteAddressIP4** ✅ (1/1 articles - perfect)
   - Falcon-specific IP address field
   - More specific than generic "IP" or "address" terms

### Functions/Operators (FQL-Specific)

8. **groupBy** ✅ (1/1 articles - perfect)
   - FQL aggregation function
   - Note: May need case-insensitive matching

## Additional High-Confidence Indicators (Not Perfect, But Strong)

### Event Types
- **NetworkConnect** - Falcon network connection event (needs validation)
- **DnsRequest** - Falcon DNS query event (needs validation)
- **UserLogon** - Falcon user logon event (needs validation)
- **UserLogoff** - Falcon user logoff event (needs validation)
- **RegKeyCreated** - Falcon registry key creation (needs validation)
- **RegKeyDeleted** - Falcon registry key deletion (needs validation)
- **RegValueSet** - Falcon registry value modification (needs validation)

### Field Names
- **MD5HashData** - Falcon MD5 hash field (needs validation)
- **SHA1HashData** - Falcon SHA1 hash field (needs validation)
- **LocalAddressIP4** - Falcon local IP field (needs validation)
- **LocalPort** - Falcon local port field (needs validation, but 0/9 in current dataset)
- **RemotePort** - Falcon remote port field (needs validation)

### Functions
- **formatTime** - FQL time formatting function (needs validation)
- **cidr** - FQL CIDR matching function (20% precision in current dataset - needs more data)

## Excluded (High False Positive Rate)

These terms appear frequently but are NOT perfect discriminators:
- ❌ **event** / **events** - Too generic (1.0% / 1.1% precision)
- ❌ **UserName** - Too generic (1.7% precision)
- ❌ **FileName** - Too generic (4.1% precision)
- ❌ **CommandLine** - Too generic (9.1% precision)
- ❌ **ComputerName** - Too generic (27.8% precision)
- ❌ **DomainName** - Too generic (0% precision)
- ❌ **QueryName** - Too generic (0% precision)

## Recommended Implementation

### Phase 1: Perfect Discriminators (8 items)
Add these to `perfect_discriminators` in `src/utils/content.py`:

```python
"perfect_discriminators": [
    # ... existing KQL discriminators ...
    
    # Falcon EDR (CrowdStrike FQL) perfect discriminators
    "ProcessRollup2",
    "event_simpleName",
    "FileWritten",
    "ImageFileName",
    "ParentBaseFileName",
    "SHA256HashData",
    "RemoteAddressIP4",
    "groupBy",
]
```

### Phase 2: Validation (After More Data)
Once more Falcon content is collected, validate:
- NetworkConnect
- DnsRequest
- MD5HashData
- SHA1HashData
- formatTime
- cidr (with context requirements)

## Notes

1. **Case Sensitivity**: Some indicators may need case-insensitive matching (e.g., `groupBy` vs `groupby`)
2. **Context Requirements**: Consider requiring multiple indicators or query syntax patterns for stronger signals
3. **Co-occurrence**: Articles with multiple Falcon indicators are more likely to be true positives
4. **Source Bias**: Current dataset may have limited CrowdStrike/Falcon content, affecting validation
