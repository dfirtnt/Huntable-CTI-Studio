# Agent Workflow UI - Complete Configurable Features

## Configuration URL
`http://127.0.0.1:8001/workflow#config`

---

## 1. JUNK FILTER

### Configurable Parameters:
- **Junk Filter Threshold**: Numeric input (0-1)
  - Description: Minimum confidence (0-1) for content filtering
  - Default: 0.9

---

## 2. QA SETTINGS

### Configurable Parameters:
- **QA Max Retries**: Numeric input (1-3)
  - Description: Maximum number of times QA Agent will give feedback to counterpart agent
  - Range: 1-3
  - Default: 3

---

## 3. OS DETECTION

### Configurable Parameters:
- **OS Detection Model**: Dropdown selection
  - **Embedding Model**: Dropdown (CTI-BERT)
  - **Target Operating Systems**: Multi-checkbox selection
    - Windows
    - Linux
    - MacOS
    - Network
    - Other
    - All
  - Description: Select target operating systems for detection (stub - only Windows enabled)

---

## 4. RANK AGENT CONFIGS

### Status: Disabled (with QA: OFF badge)

### Configurable Parameters:

#### 4.1 Rank Agent Enabled
- **Toggle**: Enable/Disable
  - Description: If enabled, articles are ranked using LLM before extraction. If disabled, ranking is skipped and workflow proceeds directly to extraction.

#### 4.2 Rank Agent Model
- **Model Provider**: Dropdown (LMStudio Local / OpenAI Cloud)
- **Model Selection**: Dropdown (google/gemma-3-4b)
- **Temperature**: Numeric input (0.0-1.0)
  - Description: Required for Rank Agent scoring
  - Default: 0.6
- **Top_P**: Numeric input (0.0-1.0)
  - Default: 0.9

#### 4.3 Rank Agent Thresholds
- **Ranking Threshold**: Numeric input (0-10)
  - Description: Minimum LLM ranking (0-10) to continue workflow
  - Default: 6

#### 4.4 Rank Agent Prompts
- **RankAgent Prompt**: Expandable prompt editor
  - Model: google/gemma-3-4b
  - Full system prompt customization

#### 4.5 Rank QA Agent
- **Toggle**: Enable QA validation
  - Description: Enable QA validation using the configured QA retry limit (default 5, max 20)

#### 4.6 Test Feature
- **Test with Custom ArticleID**: Button to test ranking on specific article

---

## 5. EXTRACT AGENTS (Supervisor)

### Configurable Parameters:

#### 5.1 Extract Agents Fallback Model
- **Model Provider**: Dropdown (LMStudio Local)
- **Model Selection**: Dropdown (codellama-7b-instruct)
- **Temperature**: Numeric input (0.0-1.0)
  - Description: Required for Extract Agent operations
  - Default: 0.1
- **Top_P**: Numeric input (0.0-1.0)
  - Default: 0.9

#### 5.2 Extract Agent Prompt
- **ExtractAgent Prompt**: Expandable prompt editor
  - Model: codellama-7b-instruct
  - Full system prompt customization

#### 5.3 Extract Agents Sub-Agents
Specialized extraction agents orchestrated by the Supervisor:

##### A. CmdlineExtract (Command Line Extraction)
- **Status**: Enabled (with QA: OFF badge)
- **Enable Toggle**: On/Off with observable count
- **Model Provider**: Dropdown (OpenAI Cloud)
- **Model Selection**: Dropdown (gpt-5.1)
- **Temperature**: Numeric input (0.0-1.0)
  - Default: 0.1
  - Description: 0.0 = deterministic, higher = more creative
- **Top_P**: Numeric input (0.0-1.0)
  - Default: 0.9
  - Description: Top-p sampling parameter (0.0-1.0, default: 0.9)
- **Test with Custom ArticleID**: Button
- **Save Preset**: Button
- **Load Preset**: Button
- **CmdlineExtract Prompt**: Expandable prompt editor (Model: gpt-5.1)
- **CmdlineExtract QA Agent**: Toggle for QA validation

##### B. ProcTreeExtract (Process Lineage)
- **Status**: Disabled (with QA: OFF badge)
- **Enable Toggle**: On/Off
- **Model Provider**: Dropdown
- **Model Selection**: Dropdown (google/gemma-3-1b / lmstudio)
- **Temperature**: Numeric input
- **Top_P**: Numeric input
- **Prompt Editor**: Expandable
- **QA Agent Toggle**

##### C. HuntQueriesExtract (Hunt Queries)
- **Status**: Disabled (with QA: OFF badge)
- **Enable Toggle**: On/Off
- **Model Provider**: Dropdown
- **Model Selection**: Dropdown (google/gemma-3-1b / lmstudio)
- **Temperature**: Numeric input
- **Top_P**: Numeric input
- **Prompt Editor**: Expandable
- **QA Agent Toggle**

---

## 6. SIGMA GENERATOR AGENT

### Status: Enabled

### Configurable Parameters:

#### 6.1 SIGMA Generator Agent Model
- **Model Provider**: Dropdown (LMStudio Local)
- **Model Selection**: Dropdown (qwen3-coder-30b-a3b-instruct)
- **Temperature**: Numeric input (0.0-1.0)
  - Default: 1
- **Top_P**: Numeric input (0.0-1.0)
  - Default: 0.8

#### 6.2 SIGMA Content Options
- **Similarity Threshold**: Numeric input (0-1)
  - Description: Max similarity (0-1) to queue rule
  - Default: 0.95

#### 6.3 Test Features
- **Test with Custom ArticleID**: Button
  - Note: Test requests run directly on article content. In actual workflow, SIGMA generation ingests observables emitted by Extract Agents

#### 6.4 SIGMA Prompts
- **SigmaAgent Prompt**: Expandable prompt editor
  - Model: qwen3-coder-30b-a3b-instruct
  - Full system prompt customization

#### 6.5 Content Source Toggle
- **Use Full Article Content (Minus Junk)**: Toggle
  - Description: If enabled, SIGMA generation will use filtered article content (junk-filtered) instead of extracted observables summary. If disabled, SIGMA generates from extracted observables only.

---

## 7. CONFIGURATION PRESETS

### Management Features:
- **Save Preset**: Save current configuration to server
- **Load Preset**: Load saved configuration from server
- **Restore by version**: Restore configuration from version history
- **Export Preset**: Export configuration to local JSON file
- **Import Preset**: Import configuration from local JSON file

### Preset Scope:
Presets include:
- Thresholds
- Model selections
- QA toggles
- Temperature settings
- Extract agent toggles
- SIGMA content source settings
- Agent prompts

---

## 8. CURRENT CONFIGURATION SUMMARY

Displays read-only summary of active configuration:
- **Version**: Configuration version number (e.g., 8351)
- **Ranking Threshold**: Current value (e.g., 6)
- **Junk Filter Threshold**: Current value (e.g., 0.9)
- **Similarity Threshold**: Current value (e.g., 0.85)
- **Updated**: Timestamp of last configuration change
- **Selected Models**: Tree view of all enabled models
  - Extract agents with their models and status
  - Sub-agent models (CmdlineExtract, ProcTreeExtract QA, HuntQueries QA)
  - SIGMA agent model

---

## 9. ACTION BUTTONS

### Primary Actions:
- **Generate LMStudio Commands**: Generate commands for LMStudio setup
- **Reset**: Reset configuration to defaults
- **Save Configuration**: Save current configuration (purple button)

---

## 10. WORKFLOW OVERVIEW VISUALIZATION

Displays workflow steps with visual indicators:
- **Step 0**: OS Detection
- **Step 1**: Junk Filter
- **Step 2**: LLM Ranking (if enabled)
- **Step 3**: Extract Agents (3 Sub-Agents)
- **Step 4**: Generate SIGMA
- **Step 5**: Similarity Search
- **Step 6**: Queue

Each step shows:
- Step number and name
- Color-coded status
- Sub-agent count (where applicable)

---

## TOTAL CONFIGURABLE COMPONENTS: 50+

### Summary by Category:
1. **Thresholds**: 4 (Junk, Ranking, Similarity, QA Retries)
2. **Model Configurations**: 5+ (Rank, Extract Fallback, CmdlineExtract, ProcTreeExtract, HuntQueries, SIGMA)
3. **Temperature/Top_P Settings**: 10+ (per model configuration)
4. **Toggle Switches**: 8+ (Agent enables, QA enables, content source)
5. **Prompt Editors**: 5+ (RankAgent, ExtractAgent, Sub-agents, SIGMA)
6. **Preset Management**: 5 actions
7. **OS Detection Options**: 6 checkboxes
8. **Test Functions**: Multiple test-with-article buttons
9. **Provider Selections**: Multiple dropdown menus per agent
