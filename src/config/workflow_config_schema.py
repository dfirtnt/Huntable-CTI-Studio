"""
Pydantic schema for workflow config v2.

PascalCase convention. All agent definitions require Provider, Model, Temperature, TopP, Enabled.
ExtractAgent is the supervisor; sub-agents (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract)
inherit provider/model when not configured.

Strict export: Prompts may only contain canonical prompt-bearing agent names (no ExtractAgentSettings).
QA.Enabled keys must match Agents keys. Features only SigmaFallbackEnabled and CmdlineAttentionPreprocessorEnabled;
agent execution is controlled by Agents.<name>.Enabled (legacy rank/os flags emitted by to_legacy_response_dict).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    """Per-agent LLM configuration. All fields required for execution."""

    model_config = {"extra": "forbid"}

    Provider: str = "lmstudio"
    Model: str = ""
    Temperature: float = 0.0
    TopP: float = 0.9
    Enabled: bool = True


class ThresholdConfig(BaseModel):
    """Workflow thresholds."""

    model_config = {"extra": "forbid"}

    MinHuntScore: float = 97.0
    RankingThreshold: float = 6.0
    SimilarityThreshold: float = 0.5
    JunkFilterThreshold: float = 0.8
    AutoTriggerHuntScoreThreshold: float = 60.0


class EmbeddingsConfig(BaseModel):
    """Embedding model names. Moved out of agent_models."""

    model_config = {"extra": "forbid"}

    OsDetection: str = "ibm-research/CTI-BERT"
    Sigma: str = "ibm-research/CTI-BERT"


class QAConfig(BaseModel):
    """QA toggles and max retries."""

    model_config = {"extra": "forbid"}

    Enabled: dict[str, bool] = Field(default_factory=dict)
    MaxRetries: int = 5


class FeatureFlags(BaseModel):
    """Feature toggles (no agent enablement; agent execution is Agents.<name>.Enabled)."""

    model_config = {"extra": "forbid"}

    SigmaFallbackEnabled: bool = False
    CmdlineAttentionPreprocessorEnabled: bool = True


class PromptConfig(BaseModel):
    """Per-agent prompt/instructions. Only prompt and instructions allowed."""

    model_config = {"extra": "forbid"}

    prompt: str = ""
    instructions: str = ""


class ExtractAgentSettingsModel(BaseModel):
    """Execution settings for ExtractAgent (supervisor)."""

    model_config = {"extra": "forbid"}

    DisabledAgents: list[str] = Field(default_factory=list)


def _default_windows_os() -> list[str]:
    return ["Windows"]


class ExecutionConfig(BaseModel):
    """Execution-related settings."""

    model_config = {"extra": "forbid"}

    ExtractAgentSettings: ExtractAgentSettingsModel = Field(default_factory=ExtractAgentSettingsModel)
    OsDetectionSelectedOs: list[str] = Field(default_factory=_default_windows_os)


class MetadataConfig(BaseModel):
    """Config metadata."""

    model_config = {"extra": "forbid"}

    CreatedAt: str = ""
    Description: str = ""


# Agent names in canonical order (main, sub-agents, QA, special)
AGENT_NAMES_MAIN = ["RankAgent", "ExtractAgent", "SigmaAgent"]
AGENT_NAMES_SUB = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract"]
AGENT_NAMES_QA = ["RankAgentQA", "CmdlineQA", "ProcTreeQA", "HuntQueriesQA"]
AGENT_NAMES_SPECIAL = ["OSDetectionFallback"]
ALL_AGENT_NAMES = AGENT_NAMES_MAIN + AGENT_NAMES_SUB + AGENT_NAMES_QA + AGENT_NAMES_SPECIAL

# Prompts section may only contain these keys (no ExtractAgentSettings; that lives under Execution).
CANONICAL_PROMPT_AGENT_NAMES = frozenset(ALL_AGENT_NAMES)

# LLM agent symmetry: base agents that require a QA agent (explicit mapping matches codebase naming).
BASE_AGENT_TO_QA: dict[str, str] = {
    "RankAgent": "RankAgentQA",
    "CmdlineExtract": "CmdlineQA",
    "ProcTreeExtract": "ProcTreeQA",
    "HuntQueriesExtract": "HuntQueriesQA",
}
QA_AGENT_TO_BASE: dict[str, str] = {qa: base for base, qa in BASE_AGENT_TO_QA.items()}


class WorkflowConfigV2(BaseModel):
    """
    Normalized workflow config v2. Version required.
    Unknown keys forbidden at root; nested models use extra='forbid' where specified.
    """

    model_config = {"extra": "forbid"}

    Version: str = Field(..., pattern=r"^2\.0$")
    Metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    Thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    Agents: dict[str, AgentConfig] = Field(default_factory=dict)
    Embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    QA: QAConfig = Field(default_factory=QAConfig)
    Features: FeatureFlags = Field(default_factory=FeatureFlags)
    Prompts: dict[str, PromptConfig] = Field(default_factory=dict)
    Execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    @model_validator(mode="after")
    def ensure_agent_fields(self) -> WorkflowConfigV2:
        """Ensure each agent has Provider, Model, Temperature, TopP, Enabled."""
        for _name, agent in self.Agents.items():
            if not isinstance(agent, AgentConfig):
                continue
            # Pydantic already validates AgentConfig; no-op here
        return self

    @model_validator(mode="after")
    def prompts_keys_canonical(self) -> WorkflowConfigV2:
        """Reject stray prompt keys; only canonical agent/QA names allowed (no ExtractAgentSettings)."""
        for key in self.Prompts:
            if key not in CANONICAL_PROMPT_AGENT_NAMES:
                allowed = sorted(CANONICAL_PROMPT_AGENT_NAMES)
                raise ValueError(f"Prompts key '{key}' is not a canonical agent name; allowed: {allowed}")
        return self

    @model_validator(mode="after")
    def qa_enabled_keys_in_agents(self) -> WorkflowConfigV2:
        """Every QA.Enabled key must exist in Agents; no orphan QA keys."""
        for key in self.QA.Enabled:
            if key not in self.Agents:
                raise ValueError(f"QA.Enabled key '{key}' is not in Agents; QA.Enabled must align with Agents keys")
        return self

    @model_validator(mode="after")
    def llm_agent_symmetry(self) -> WorkflowConfigV2:
        """Enforce: (0) enabled agents have Provider+Model; (1) required QA for enabled base agents;
        (2) no orphan QA agents; (3) prompt block per LLM agent."""
        agents = self.Agents
        prompts = self.Prompts
        # Part 0: if Enabled == true, Provider and Model must be non-empty (no pseudo-enabled empty-model loophole)
        for name, cfg in agents.items():
            if cfg.Enabled and (not cfg.Provider or not cfg.Model):
                raise ValueError(f"Agent '{name}' is Enabled but missing Provider or Model.")
        # Part 1: every enabled base agent (with Provider+Model) in mapping must have its QA agent
        for name, cfg in agents.items():
            if name.endswith("QA") or name == "OSDetectionFallback":
                continue
            if not (cfg.Enabled and cfg.Provider and cfg.Model):
                continue
            expected_qa = BASE_AGENT_TO_QA.get(name)
            if expected_qa is not None and expected_qa not in agents:
                raise ValueError(f"Missing QA agent for {name}: expected {expected_qa} in Agents")
        # Part 2: every QA agent must have its base agent
        for name in agents:
            if not name.endswith("QA"):
                continue
            base = QA_AGENT_TO_BASE.get(name, name[:-2])
            if base not in agents:
                raise ValueError(f"Orphan QA agent {name}: base agent {base} must exist in Agents")
        # Part 3: every agent with Provider+Model must have a prompt block
        # (except OSDetectionFallback when disabled and no model)
        for name, cfg in agents.items():
            if name == "OSDetectionFallback" and not cfg.Enabled and not cfg.Model:
                continue
            if cfg.Provider and cfg.Model and name not in prompts:
                raise ValueError(f"Missing prompt block for agent {name}")
        return self

    def flatten_for_llm_service(self) -> dict[str, Any]:
        """
        Produce flat key format expected by LLMService and other legacy consumers.
        Keys: RankAgent_provider, RankAgent, RankAgent_temperature, RankAgent_top_p, etc.
        Main agents use name as model key; sub-agents use name_model; QA use name.
        """
        out: dict[str, Any] = {}
        main_model_keys = {"RankAgent", "ExtractAgent", "SigmaAgent"}
        qa_agents = {"RankAgentQA", "CmdlineQA", "ProcTreeQA", "HuntQueriesQA"}
        sub_agents = {"CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract"}
        # Legacy flat keys expected by UI and services (v2 CmdlineQA -> CmdLineQA)
        legacy_flat_prefix: dict[str, str] = {"CmdlineQA": "CmdLineQA"}
        for agent_name, agent in self.Agents.items():
            if not isinstance(agent, AgentConfig):
                continue
            prefix = legacy_flat_prefix.get(agent_name, agent_name)
            if agent_name == "OSDetectionFallback":
                prefix = "OSDetectionAgent_fallback"
            out[f"{prefix}_provider"] = agent.Provider
            if agent_name == "OSDetectionFallback":
                model_key = "OSDetectionAgent_fallback"
            elif agent_name in main_model_keys:
                model_key = agent_name
            elif agent_name in sub_agents:
                model_key = f"{prefix}_model"
            elif agent_name in qa_agents:
                model_key = prefix
            else:
                model_key = prefix
            out[model_key] = agent.Model
            out[f"{prefix}_temperature"] = agent.Temperature
            out[f"{prefix}_top_p"] = agent.TopP
        out["OSDetectionAgent_embedding"] = self.Embeddings.OsDetection
        out["SigmaEmbeddingModel"] = self.Embeddings.Sigma
        if self.Execution.OsDetectionSelectedOs:
            out["OSDetectionAgent_selected_os"] = self.Execution.OsDetectionSelectedOs
        return out

    def to_legacy_response_dict(
        self,
        *,
        id: int = 0,
        version: int = 1,
        is_active: bool = True,
        created_at: str = "",
        updated_at: str = "",
    ) -> dict[str, Any]:
        """Build dict suitable for WorkflowConfigResponse (legacy API shape)."""
        agent_prompts_out: dict[str, Any] = {}
        for name, val in self.Prompts.items():
            if isinstance(val, PromptConfig):
                agent_prompts_out[name] = {"prompt": val.prompt, "instructions": val.instructions}
            elif isinstance(val, dict):
                agent_prompts_out[name] = {"prompt": val.get("prompt", ""), "instructions": val.get("instructions", "")}
        rank_agent = self.Agents.get("RankAgent")
        os_fallback = self.Agents.get("OSDetectionFallback")
        return {
            "id": id,
            "min_hunt_score": self.Thresholds.MinHuntScore,
            "ranking_threshold": self.Thresholds.RankingThreshold,
            "similarity_threshold": self.Thresholds.SimilarityThreshold,
            "junk_filter_threshold": self.Thresholds.JunkFilterThreshold,
            "auto_trigger_hunt_score_threshold": self.Thresholds.AutoTriggerHuntScoreThreshold,
            "version": version,
            "is_active": is_active,
            "description": self.Metadata.Description,
            "agent_prompts": agent_prompts_out,
            "agent_models": self.flatten_for_llm_service(),
            "qa_enabled": self.QA.Enabled,
            "sigma_fallback_enabled": self.Features.SigmaFallbackEnabled,
            "osdetection_fallback_enabled": os_fallback.Enabled if isinstance(os_fallback, AgentConfig) else False,
            "qa_max_retries": self.QA.MaxRetries,
            "rank_agent_enabled": rank_agent.Enabled if isinstance(rank_agent, AgentConfig) else True,
            "cmdline_attention_preprocessor_enabled": self.Features.CmdlineAttentionPreprocessorEnabled,
            "created_at": created_at,
            "updated_at": updated_at,
        }
