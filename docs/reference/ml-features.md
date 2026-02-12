# ML Model Feature Definitions

Detailed definitions of all parameters used in the content filter ML model, including how each feature is accurately identified.

## Overview

The content filter uses a **RandomForestClassifier** with 27 features (or 31 with new features enabled). Features are **NOT weighted equally** - the model learns feature importances during training, with some features (like `hunt_score` and `perfect_pattern_count`) having significantly higher weights.

---

## Pattern-Based Features

### `huntable_pattern_count`
**Definition:** Total count of huntable pattern matches in the text chunk.

**How it's identified:**
- Searches text (case-insensitive) against a combined list of:
  - **Perfect discriminators** (103 patterns): Keywords that appear exclusively in high-quality threat hunting content
  - **Good discriminators**: Supporting technical keywords
  - **LOLBAS executables**: Living Off the Land Binaries and Scripts
  - **Intelligence indicators**: Core threat intelligence keywords
- Uses regex matching with word boundaries to prevent false positives
- Patterns are loaded from `HUNT_SCORING_KEYWORDS` dictionary

**Accuracy:** High - Uses validated keyword lists from analysis of 319 historically labeled training samples (historical labels 'high-signal' and 'low-signal' with 97 and 222 samples respectively). Note: article-level "chosen/rejected" classification is removed from the UI and should not be relied upon.articles (97 Chosen, 222 Rejected)

**Examples:**
- Perfect: `rundll32.exe`, `msiexec.exe`, `powershell.exe`, `hklm`, `.lnk`
- Good: `EventCode`, `KQL`, `parent-child`
- LOLBAS: `certutil.exe`, `schtasks.exe`, `wmic.exe`

---

### `not_huntable_pattern_count`
**Definition:** Count of negative indicator patterns that suggest non-huntable content.

**How it's identified:**
- Searches for marketing, educational, or acknowledgment patterns
- Patterns include: `demo`, `free trial`, `book a demo`, `managed service`, `platform`, `acknowledgement`, `gratitude`, `thank you`, `contact`
- Case-insensitive regex matching

**Accuracy:** High - Identifies common marketing/PR language patterns

---

### `perfect_pattern_count` (New Feature)
**Definition:** Count of perfect discriminator matches only (subset of huntable patterns).

**How it's identified:**
- Searches against **103 perfect discriminators** only
- These are keywords that had **100% precision** in training data analysis
- Includes Windows executables, registry paths, PowerShell techniques, EDR query syntax

**Accuracy:** Very High - Perfect discriminators have 100% precision (0% false positives in training data)

**Examples:**
- `rundll32.exe`, `comspec`, `msiexec.exe`, `wmic.exe`
- `hklm`, `appdata`, `programdata`, `powershell.exe`
- `.lnk`, `D:\`, `.iso`, `MZ`
- `svchost.exe`, `lsass.exe`, `WINDIR`, `wintmp`
- KQL tables: `DeviceProcessEvents`, `DeviceNetworkEvents`
- Falcon EDR fields: `ProcessRollup2`, `event_simpleName`

---

### `other_huntable_pattern_count` (New Feature)
**Definition:** Count of huntable patterns excluding perfect discriminators.

**How it's identified:**
- Good discriminators + LOLBAS executables + Intelligence indicators
- Excludes patterns already counted in perfect discriminators

**Accuracy:** High - Supporting technical content indicators

---

### `huntable_pattern_ratio`
**Definition:** Ratio of huntable patterns to total word count.

**Calculation:** `huntable_pattern_count / word_count`

**Purpose:** Normalizes pattern count by text length to compare chunks of different sizes.

---

### `not_huntable_pattern_ratio`
**Definition:** Ratio of negative indicators to total word count.

**Calculation:** `not_huntable_pattern_count / word_count`

**Purpose:** Identifies marketing/PR content density.

---

### `perfect_pattern_ratio` (New Feature)
**Definition:** Ratio of perfect discriminators to total word count.

**Calculation:** `perfect_pattern_count / word_count`

**Purpose:** Measures technical depth density.

---

### `other_huntable_pattern_ratio` (New Feature)
**Definition:** Ratio of other huntable patterns to total word count.

**Calculation:** `other_huntable_pattern_count / word_count`

---

## Text Characteristics

### `char_count`
**Definition:** Total character count in the text chunk.

**How it's identified:**
- Direct: `len(text)`
- Includes all characters (spaces, punctuation, etc.)

**Accuracy:** Exact

---

### `word_count`
**Definition:** Total word count in the text chunk.

**How it's identified:**
- Direct: `len(text.split())`
- Splits on whitespace

**Accuracy:** High - Simple whitespace splitting (may miscount hyphenated words)

---

### `sentence_count`
**Definition:** Number of sentences in the text chunk.

**How it's identified:**
- Uses `count_sentences()` function from `sentence_splitter` module
- Uses SpaCy sentence boundary detection for accuracy
- Handles abbreviations and decimal numbers correctly

**Accuracy:** High - Uses NLP sentence boundary detection

---

### `avg_word_length`
**Definition:** Average length of words in the chunk.

**How it's identified:**
- Calculation: `mean([len(word) for word in text.split()])`
- Uses NumPy for calculation

**Accuracy:** High - Simple statistical measure

**Purpose:** Longer words may indicate technical terminology.

---

## Technical Content Indicators

### `command_count`
**Definition:** Count of command execution patterns.

**How it's identified:**
- Regex pattern: `r"\b(powershell|cmd|bash|ssh|curl|wget|invoke)\b"`
- Case-insensitive word boundary matching
- Matches common command-line tools and execution keywords

**Accuracy:** High - Specific command keywords with word boundaries

**Examples:**
- `powershell`, `cmd`, `bash`, `ssh`, `curl`, `wget`, `invoke`

---

### `url_count`
**Definition:** Count of HTTP/HTTPS URLs in the text.

**How it's identified:**
- Regex pattern: `r"http[s]?://[^\s]+"`
- Matches `http://` or `https://` followed by non-whitespace characters

**Accuracy:** Very High - Standard URL pattern matching

---

### `ip_count`
**Definition:** Count of IPv4 addresses in the text.

**How it's identified:**
- Regex pattern: `r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"`
- Matches 1-3 digit groups separated by dots with word boundaries
- **Note:** Does not validate IP ranges (e.g., 999.999.999.999 would match)

**Accuracy:** Medium-High - May have false positives for non-IP numbers (e.g., version numbers)

**Limitation:** Does not validate that numbers are in valid IP range (0-255)

---

### `file_path_count`
**Definition:** Count of file system paths in the text.

**How it's identified:**
- Regex pattern: `r"[A-Za-z]:\\\\[^\s]+|/[^\s]+"`
- Matches:
  - Windows paths: `C:\path\to\file` (drive letter + backslashes)
  - Unix paths: `/path/to/file` (leading slash)

**Accuracy:** High - Common path patterns

**Examples:**
- `C:\Windows\System32\cmd.exe`
- `/usr/bin/bash`
- `D:\temp\file.txt`

---

### `process_count`
**Definition:** Count of specific process names in the text.

**How it's identified:**
- Regex pattern: `r"\b(node\.exe|ws_tomcatservice\.exe|powershell\.exe|cmd\.exe)\b"`
- Case-insensitive word boundary matching
- Matches specific executable names commonly referenced in threat hunting

**Accuracy:** High - Specific process names

**Limitation:** Only matches 4 specific processes (not comprehensive)

---

### `cve_count`
**Definition:** Count of CVE (Common Vulnerabilities and Exposures) references.

**How it's identified:**
- Regex pattern: `r"CVE-\d{4}-\d+"` (case-insensitive)
- Matches format: `CVE-YYYY-NNNN+`

**Accuracy:** Very High - Standard CVE format is unique

**Examples:**
- `CVE-2023-1234`
- `CVE-2024-56789`

---

## Content Quality Indicators

### `technical_term_count`
**Definition:** Count of technical security terminology.

**How it's identified:**
- Regex pattern: `r"\b(dll|exe|payload|backdoor|shell|exploit|vulnerability|malware)\b"`
- Case-insensitive word boundary matching
- Matches common security/technical terms

**Accuracy:** High - Specific technical keywords

**Examples:**
- `dll`, `exe`, `payload`, `backdoor`, `shell`, `exploit`, `vulnerability`, `malware`

---

### `marketing_term_count`
**Definition:** Count of marketing/PR terminology.

**How it's identified:**
- Regex pattern: `r"\b(demo|free trial|book a demo|managed service|platform)\b"`
- Case-insensitive word boundary matching
- Identifies commercial/marketing language

**Accuracy:** High - Common marketing phrases

**Examples:**
- `demo`, `free trial`, `book a demo`, `managed service`, `platform`

---

### `acknowledgment_count`
**Definition:** Count of acknowledgment/gratitude phrases.

**How it's identified:**
- Regex pattern: `r"\b(acknowledgement|gratitude|thank you|appreciate|contact)\b"`
- Case-insensitive word boundary matching
- Identifies author bios, contact sections, acknowledgments

**Accuracy:** High - Common acknowledgment phrases

**Examples:**
- `acknowledgement`, `gratitude`, `thank you`, `appreciate`, `contact`

---

### `technical_term_ratio`
**Definition:** Ratio of technical terms to total word count.

**Calculation:** `technical_term_count / word_count`

**Purpose:** Measures technical content density.

---

### `marketing_term_ratio`
**Definition:** Ratio of marketing terms to total word count.

**Calculation:** `marketing_term_count / word_count`

**Purpose:** Identifies marketing content density.

---

## Structural Features (Boolean)

### `has_code_blocks`
**Definition:** Boolean indicating presence of code blocks.

**How it's identified:**
- Regex pattern: `r"```|`[^`]+`"`
- Matches:
  - Triple backticks: ` ``` `
  - Inline code: `` `code` ``

**Accuracy:** High - Standard markdown code block patterns

---

### `has_commands`
**Definition:** Boolean indicating presence of command markers.

**How it's identified:**
- Regex pattern: `r"Command:|Cleartext:"`
- Matches specific command extraction markers

**Accuracy:** High - Specific markers from extraction system

**Purpose:** Identifies extracted command-line data.

---

### `has_urls`
**Definition:** Boolean indicating presence of URLs.

**How it's identified:**
- Regex pattern: `r"http[s]?://"`
- Simple presence check (not count)

**Accuracy:** Very High

---

### `has_file_paths`
**Definition:** Boolean indicating presence of file paths.

**How it's identified:**
- Regex pattern: `r"[A-Za-z]:\\\\|/[^\s]+"`
- Matches Windows or Unix path patterns

**Accuracy:** High

---

## Hunt Score Integration Features

### `hunt_score`
**Definition:** Normalized threat hunting score (0-1 range).

**How it's identified:**
- Source: Article metadata `threat_hunting_score` (0-100 range)
- Normalization: `hunt_score / 100.0`
- Calculated by `ThreatHuntingScorer.score_threat_hunting_content()`

**Calculation Method:**
- Uses logarithmic bucket scoring with geometric series
- Perfect discriminators: 75 points max
- LOLBAS: 10 points max
- Intelligence indicators: 10 points max
- Good discriminators: 5 points max
- Negative penalty: -10 points max
- Final score: 0-99.9 range (never reaches 100)

**Accuracy:** Very High - Based on validated keyword analysis of 319 articles

---

### `hunt_score_high`
**Definition:** Boolean indicating high-quality content (score ≥ 70).

**How it's identified:**
- Calculation: `1.0 if hunt_score >= 70 else 0.0`
- Binary feature for high-quality threshold

**Accuracy:** Exact

---

### `hunt_score_medium`
**Definition:** Boolean indicating medium-quality content (30-69).

**How it's identified:**
- Calculation: `1.0 if 30 <= hunt_score < 70 else 0.0`
- Binary feature for medium-quality range

**Accuracy:** Exact

---

### `hunt_score_low`
**Definition:** Boolean indicating low-quality content (score < 30).

**How it's identified:**
- Calculation: `1.0 if hunt_score < 30 else 0.0`
- Binary feature for low-quality threshold

**Accuracy:** Exact

---

## Feature Identification Accuracy Summary

| Feature | Accuracy | Method | Notes |
|---------|----------|--------|-------|
| `perfect_pattern_count` | Very High | Regex + validated keywords | 100% precision in training data |
| `hunt_score` | Very High | Logarithmic scoring system | Based on 319 article analysis |
| `cve_count` | Very High | Regex pattern | Standard CVE format |
| `url_count` | Very High | Regex pattern | Standard URL format |
| `huntable_pattern_count` | High | Regex + keyword lists | Validated keyword sets |
| `command_count` | High | Regex with word boundaries | Specific command keywords |
| `file_path_count` | High | Regex pattern | Common path patterns |
| `sentence_count` | High | NLP (SpaCy) | Sentence boundary detection |
| `ip_count` | Medium-High | Regex pattern | May match non-IP numbers |
| `process_count` | High | Regex pattern | Limited to 4 specific processes |

---

## Pattern Matching Details

### Keyword Matching Algorithm

The system uses `ThreatHuntingScorer._keyword_matches()` for pattern matching:

1. **Regex Patterns:** If keyword starts with `r"`, treated as raw regex
2. **Word Boundaries:** Literal keywords use word boundaries to prevent false positives
3. **Obfuscation Detection:** Includes regex patterns for cmd.exe obfuscation:
   - Environment variable substring access: `%VAR:~0,5%`
   - Delayed expansion: `!VAR!`
   - Caret obfuscation: `s^e^t`, `c^a^l^l`
   - FOR loop obfuscation
4. **Case-Insensitive:** All matching is case-insensitive

### Perfect Discriminators (103 patterns)

**Source:** Analysis of 319 articles showing 100% precision (0% false positives)

**Categories:**
- **Windows Executables:** `rundll32.exe`, `msiexec.exe`, `svchost.exe`, `lsass.exe`
- **Registry/Paths:** `hklm`, `appdata`, `programdata`, `WINDIR`, `wintmp`
- **Command Execution:** `powershell.exe`, `wmic.exe`, `iex`, `findstr.exe`
- **File Types:** `.lnk`, `.iso`, `MZ`
- **PowerShell Techniques:** `FromBase64String`, `MemoryStream`, `DownloadString`
- **KQL Tables:** `DeviceProcessEvents`, `DeviceNetworkEvents`, `EmailEvents`
- **Falcon EDR Fields:** `ProcessRollup2`, `event_simpleName`, `ImageFileName`
- **SentinelOne Fields:** `TgtFileProcessPath`, `SrcProcParentPath`
- **Splunk CIM:** `Processes`, `Network_Traffic`
- **Elastic Security:** `process.command_line`, `file.path`

---

## Model Training Context

-- **Algorithm:** RandomForestClassifier
-- **Training Data:** 278 historical samples (222 annotations and+ 81 feedback) — dataset labels reflect legacy "high/low signal" annotations and do not imply an active article-level classification UI
- samples)
- **Features:** 27 base features (31 with new features)
- **Feature Importances:** Learned during training (not equal weighting)
- **Accuracy:** ~80% on test data

The model learns which features are most important for classification, with features like `hunt_score`, `perfect_pattern_count`, and `huntable_pattern_count` typically having higher importances than structural features like `char_count` or `avg_word_length`.
<!--stackedit_data:
eyJoaXN0b3J5IjpbMTU4MzMxOTcxN119
-->