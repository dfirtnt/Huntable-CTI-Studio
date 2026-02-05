Huntable Hybrid Command-Line Extraction Pipeline

Developer/AI Implementation Spec (Strict, Atomic, Buildable)

Goal

Replace the existing LLM CmdLineExtractAgent with a deterministic + encoder + (optional) QA hybrid pipeline.

Output MUST remain fully compatible with:

{ "cmdline_items": [...], "count": N, "qa_corrections": {...} }

---

FILE STRUCTURE THE AI MUST CREATE

src/
  extractors/
    hybrid_cmdline_extractor.py
    regex_windows.py
    encoder_classifier.py
    qa_validator.py   (optional)
workflows/
  nodes/
    hybrid_extractor_node.py
resources/
  regex/
    windows_cmd_patterns.yaml
tests/
  test_hybrid_extractor.py

---

1. Regex Candidate Extractor (deterministic)

File: src/extractors/regex_windows.py

Function to create:

def extract_candidate_lines(text: str) -> list[str]:
    """
    Return list of raw candidate command-line strings from the article.
    These are NOT validated; high recall, low precision.
    """

Implementation requirements:
    • Apply multiple regexes, each catching different command-line shapes.
    • Return deduped list.
    • Preserve original text (no normalization).
    • Must catch:
    • *.exe with args
    • Windows paths + args
    • powershell patterns
    • net/ipconfig/setspn/quser + args
    • quoted executables
    • pipeline operators (|, >, &&)

AI must write these regexes:

PATTERN_EXE_WITH_ARGS:
    r'(?:"?[A-Za-z]:\\\\[^"\\s]+\\.\\w{3,4}"?(?:\\s+[^\\r\\n]+))'

PATTERN_BARE_EXE_WITH_ARGS:
    r'(?:[A-Za-z0-9_\\-]+\\.exe)(?:\\s+[^\\r\\n]+)'

PATTERN_POWERSHELL:
    r'(?:powershell(?:\\.exe)?)\\s+[^\\r\\n]+'

PATTERN_SYSTEM32_UTILS:
    r'(?:"?C:\\\\Windows\\\\System32\\\\(?:net|ipconfig|setspn|quser)\\.exe"?\\s+[^\\r\\n]+)'

Output example:

["C:\\\\Windows\\\\System32\\\\net.exe group domain ...", "powershell.exe ..."]

---

2. Encoder Classifier (semantic filtering)

File: src/extractors/encoder_classifier.py

Function to create:

def classify_candidates(candidates: list[str]) -> list[str]:
    """
    Return the subset of candidates that are VALID Windows commands.
    Uses an encoder to filter log lines, ARGV arrays, filenames, and noise.
    """

Required model:

Use one of:
    • sentence-transformers/all-MiniLM-L6-v2
    • intfloat/e5-base-v2
    • microsoft/CTI-BERT  ← recommended

Classifier behavior:

AI must implement one of these:

Option A — Zero-shot similarity

Create two lists:

VALID_EXAMPLES = [
  'powershell.exe -ExecutionPolicy Bypass -enc AAA',
  '"C:\\\\Program Files\\\\App\\\\app.exe" -flag',
  'C:\\\\Windows\\\\System32\\\\net.exe group "domain users" /do'
]

INVALID_EXAMPLES = [
  'Service Control Manager/7036; Velociraptor running',
  'MsiInstaller/11707; Product installed successfully',
  '"C:\\\\Program Files\\\\Velociraptor\\\\Velociraptor.exe"',
  'Velociraptor/1000; ARGV: ["C:..."]'
]

Compute cosine similarity:

sim_valid = cos(emb(candidate), emb(VALID_EXAMPLES).mean)
sim_invalid = cos(emb(candidate), emb(INVALID_EXAMPLES).mean)

Keep candidate if:

sim_valid > sim_invalid + 0.05

Output:

List of validated command-lines.

---

3. LLM QA Validator (optional)

File: src/extractors/qa_validator.py

Function to create:

def qa_validate(final_candidates: list[str], article: str) -> list[str]:
    """
    Use a small LLM to re-check borderline cases.
    Must output the same or reduced list.
    """

Model:

Qwen2.5-Coder-7B-Instruct or Llama-3.1-8B

Prompt skeleton AI must implement:

You are a QA validator. 
For each string, return VALID or INVALID.

VALID if:
- appears literally in the article
- contains a Windows executable
- includes at least one argument
- is NOT a log row or MSI/SCM entry

---

4. Hybrid Extractor Entry Point

File: src/extractors/hybrid_cmdline_extractor.py

Function to create:

def extract_commands(article_text: str) -> dict:
    """
    Returns JSON-ready dict:
    {
        "cmdline_items": [...],
        "count": N,
        "qa_corrections": {...}
    }
    """

Algorithm:

candidates = extract_candidate_lines(article_text)
filtered   = classify_candidates(candidates)

if QA is enabled:
    final = qa_validate(filtered, article_text)
else:
    final = filtered

return {
  "cmdline_items": final,
  "count": len(final),
  "qa_corrections": {"removed": [], "added": [], "summary": "None."}
}

---

5. LangChain / LangGraph Integration

File: workflows/nodes/hybrid_extractor_node.py

Node signature:

class HybridExtractorNode:
    def run(self, article_text: str) -> dict:
        return extract_commands(article_text)

Replace old node:

CmdLineExtractAgent  → HybridExtractorNode

No other workflow changes required.

All downstream agents see identical JSON structure.

---

6. Unit Tests

File: tests/test_hybrid_extractor.py

AI must write tests for:
    • event logs → rejected
    • ARGV arrays → rejected
    • MSI lines → rejected
    • .exe with no args → rejected
    • multi-line commands → accepted
    • powershell encoded commands → accepted
    • dedupe
    • exact literal matching
    • integration: article → output count

---

7. Optional Extras

Add config file:

resources/regex/windows_cmd_patterns.yaml
If you want to make regex editable without modifying code.

---

8. Performance Requirements
    • < 100ms per article
    • 0 hallucination
    • near-100% literal recall
    • 95% filtering precision
    • output must remain identical JSON schema

---
