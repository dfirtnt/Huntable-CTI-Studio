# Backup Manifest - Old Architecture

## Backup Information

- **Backup Date**: August 31, 2024
- **Backup Purpose**: Preserve old architecture before major refactor
- **Backup Location**: `backup_old_architecture/`
- **Backup Reason**: Major architectural changes in v2.0.0

## Files Backed Up

### Quality Assessment System
- `llm_quality_assessor_v1.py` - Original LLM-powered quality assessor
- `ttp_extractor_v1.py` - Original threat hunting detector

### Original System Characteristics

#### LLM Quality Assessor v1
- **Purpose**: LLM-powered content quality assessment
- **Features**: 
  - Async LLM calls to Ollama
  - Quality scoring and recommendations
  - Hunting priority determination
- **Limitations**:
  - Limited to LLM-based analysis only
  - No rule-based fallback
  - Dependency on external LLM service

#### TTP Extractor v1
- **Purpose**: Threat hunting technique detection
- **Features**:
  - Pattern-based TTP extraction
  - Confidence scoring
  - Artifact categorization
- **Limitations**:
  - Basic pattern matching
  - Limited artifact coverage
  - Generic detection patterns

## New System Features

### Advanced Quality System
- **Multi-dimensional scoring**: Artifact coverage, technical depth, actionable intelligence
- **Platform coverage**: Windows, Linux, Cloud, and more
- **Criticality levels**: Critical, High, Medium, Low
- **Hunting priority algorithm**: Advanced priority determination

### Enhanced TTP Extraction
- **Comprehensive patterns**: 50+ artifact types with specific patterns
- **Actionable intelligence**: Specific detection queries and guidance
- **Quality filtering**: Minimum length and specificity requirements
- **Platform-specific detection**: Windows, Linux, Cloud artifacts

### Dual Analysis Systems
- **Rule-based system**: Fast, reliable, comprehensive coverage
- **LLM-powered system**: Advanced AI analysis and reasoning
- **Integrated approach**: Best of both worlds

## Migration Notes

### From Old to New System
1. **Quality Assessment**: 
   - Old: Single LLM-based scoring
   - New: Multi-dimensional rule-based + LLM analysis

2. **TTP Extraction**:
   - Old: Basic pattern matching
   - New: Comprehensive artifact coverage with actionable intelligence

3. **Architecture**:
   - Old: Single analysis path
   - New: Dual analysis systems with integration

### Compatibility
- **Backward Compatibility**: Not maintained due to major architectural changes
- **Data Migration**: Required for existing data
- **Configuration**: New environment-based configuration required

## Restoration Instructions

### If Restoration is Needed
1. **Copy files back**:
   ```bash
   cp backup_old_architecture/quality_assessment/llm_quality_assessor_v1.py src/utils/
   cp backup_old_architecture/quality_assessment/ttp_extractor_v1.py src/utils/
   ```

2. **Update imports**:
   ```python
   # Update import statements in affected files
   from src.utils.llm_quality_assessor_v1 import LLMQualityAssessor
   from src.utils.ttp_extractor_v1 import ThreatHuntingDetector
   ```

3. **Test functionality**:
   ```bash
   pytest tests/ -k "quality_assessment"
   pytest tests/ -k "ttp_extraction"
   ```

### Warning
- **Not Recommended**: The old system has known limitations
- **Performance**: New system provides better performance and accuracy
- **Security**: New system includes enhanced security features
- **Maintenance**: Old system will not receive updates

## Backup Verification

### Integrity Check
- [x] All files backed up successfully
- [x] File permissions preserved
- [x] No corruption detected
- [x] Backup location documented

### Size Information
- **Total Backup Size**: ~50KB
- **Number of Files**: 2
- **Backup Format**: Direct file copy
- **Compression**: None (files are small)

## Future Considerations

### Long-term Storage
- **Retention Period**: 1 year
- **Archive Location**: To be determined
- **Access Method**: Direct file access

### Documentation
- **Purpose**: Historical reference and rollback capability
- **Usage**: Emergency restoration only
- **Maintenance**: No planned updates

---

**Note**: This backup was created during the v2.0.0 major release. The new system provides significant improvements in functionality, performance, and security. Restoration should only be considered in emergency situations.
