"""
Pydantic schema for workflow config v2.

PascalCase convention. All agent definitions require Provider, Model, Temperature, TopP, Enabled.
ExtractAgent is the model/provider fallback key for sub-agents (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract),
which each carry their own prompt. ExtractAgent does not have a prompt of its own.

Strict export: Prompts may only contain canonical prompt-bearing agent names (no ExtractAgentSettings).
Features only SigmaFallbackEnabled and CmdlineAttentionPreprocessorEnabled;
agent execution is controlled by Agents.<name>.Enabled (legacy rank/os flags emitted by to_legacy_response_dict).

QA Agents are fully deprecated (removed 2026-05-22). RankAgentQA and all extractor QA agents are gone.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    """Per-agent LLM configuration. All fields required for execution."""

    model_config = {"extra": "forbid"}

    Provider: str = ""
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


class EmbeddingsConfig(BaseModel):
    """Embedding model names. Moved out of agent_models."""

    model_config = {"extra": "forbid"}

    OsDetection: str = "ibm-research/CTI-BERT"
    Sigma: str = "ibm-research/CTI-BERT"


class FeatureFlags(BaseModel):
    """Feature toggles (no agent enablement; agent execution is Agents.<name>.Enabled)."""

    model_config = {"extra": "forbid"}

    SigmaFallbackEnabled: bool = False
    CmdlineAttentionPreprocessorEnabled: bool = True
    ProcTreeAttentionPreprocessorEnabled: bool = True


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
AGENT_NAMES_SUB = [
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
]
AGENT_NAMES_QA: list[str] = []
AGENT_NAMES_SPECIAL: list[str] = []
ALL_AGENT_NAMES = AGENT_NAMES_MAIN + AGENT_NAMES_SUB + AGENT_NAMES_QA + AGENT_NAMES_SPECIAL

# Prompts section may only contain these keys (no ExtractAgentSettings; that lives under Execution).
CANONICAL_PROMPT_AGENT_NAMES = frozenset(ALL_AGENT_NAMES)

# Human-readable display names — single source of truth consumed by Python and JS.
AGENT_DISPLAY_NAMES: dict[str, str] = {
    "RankAgent": "Rank Agent",
    "ExtractAgent": "Extract Agent",
    "SigmaAgent": "SIGMA Agent",
    "OSDetectionAgent": "OS Detection",
    "CmdlineExtract": "Command Line Extraction",
    "ProcTreeExtract": "Process Lineage Extraction",
    "HuntQueriesExtract": "Hunt Queries Extraction",
    "RegistryExtract": "Registry Artifacts Extraction",
    "ServicesExtract": "Windows Services Extraction",
    "ScheduledTasksExtract": "Scheduled Tasks Extraction",
}

# QA agents fully deprecated (2026-05-22). These dicts are intentionally empty.
BASE_AGENT_TO_QA: dict[str, str] = {}
QA_AGENT_TO_BASE: dict[str, str] = {}


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
    def llm_agent_symmetry(self) -> WorkflowConfigV2:
        """Enforce symmetry: (0) enabled agents must have Provider+Model; (1) prompt block per LLM agent."""
        agents = self.Agents
        prompts = self.Prompts
        # Part 0: if Enabled == true, Provider and Model must be non-empty (no pseudo-enabled empty-model loophole)
        for name, cfg in agents.items():
            if cfg.Enabled and (not cfg.Provider or not cfg.Model):
                raise ValueError(f"Agent '{name}' is Enabled but missing Provider or Model.")
        # Part 1: every agent with Provider+Model must have a prompt block.
        # ExtractAgent is excluded: it is a model/provider fallback key for sub-agents only
        # and must NOT appear in the Prompts block (migrator strips any stale DB entry).
        _PROMPT_FREE = {"ExtractAgent"}
        for name, cfg in agents.items():
            if name in _PROMPT_FREE:
                continue
            if cfg.Provider and cfg.Model and name not in prompts:
                raise ValueError(f"Missing prompt block for agent {name}")
        for name in prompts:
            if name in _PROMPT_FREE:
                raise ValueError(f"Prompts block must not contain '{name}': it is a model/provider fallback key only.")
        return self

    def flatten_for_llm_service(self) -> dict[str, Any]:
        """
        Produce flat key format expected by LLMService and other legacy consumers.
        Keys: RankAgent_provider, RankAgent, RankAgent_temperature, RankAgent_top_p, etc.
        Main agents use name as model key; sub-agents use name_model.
        """
        out: dict[str, Any] = {}
        main_model_keys = {"RankAgent", "ExtractAgent", "SigmaAgent"}
        sub_agents = {
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        }
        for agent_name, agent in self.Agents.items():
            if not isinstance(agent, AgentConfig):
                continue
            out[f"{agent_name}_provider"] = agent.Provider
            if agent_name in main_model_keys:
                model_key = agent_name
            elif agent_name in sub_agents:
                model_key = f"{agent_name}_model"
            else:
                model_key = agent_name
            out[model_key] = agent.Model
            out[f"{agent_name}_temperature"] = agent.Temperature
            out[f"{agent_name}_top_p"] = agent.TopP
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
        # UI expects agent_prompts.ExtractAgentSettings.disabled_agents on GET so extract toggles persist after refresh
        agent_prompts_out["ExtractAgentSettings"] = {
            "disabled_agents": list(self.Execution.ExtractAgentSettings.DisabledAgents),
        }
        rank_agent = self.Agents.get("RankAgent")
        return {
            "id": id,
            "min_hunt_score": self.Thresholds.MinHuntScore,
            "ranking_threshold": self.Thresholds.RankingThreshold,
            "similarity_threshold": self.Thresholds.SimilarityThreshold,
            "junk_filter_threshold": self.Thresholds.JunkFilterThreshold,
            "version": version,
            "is_active": is_active,
            "description": self.Metadata.Description,
            "agent_prompts": agent_prompts_out,
            "agent_models": self.flatten_for_llm_service(),
            "sigma_fallback_enabled": self.Features.SigmaFallbackEnabled,
            "rank_agent_enabled": rank_agent.Enabled if isinstance(rank_agent, AgentConfig) else True,
            "cmdline_attention_preprocessor_enabled": self.Features.CmdlineAttentionPreprocessorEnabled,
            "proc_tree_attention_preprocessor_enabled": self.Features.ProcTreeAttentionPreprocessorEnabled,
            "created_at": created_at,
            "updated_at": updated_at,
        }
