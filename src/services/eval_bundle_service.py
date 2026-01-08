"""
Eval Bundle Export Service

Generates evaluation-ready JSON bundles for LLM generation attempts.
Source of truth: Postgres DB + internal tracing (Langfuse).
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from src.database.models import (
    AgenticWorkflowExecutionTable,
    ArticleTable,
    AgentPromptVersionTable,
    AgenticWorkflowConfigTable,
    SubagentEvaluationTable
)
from src.utils.langfuse_client import get_langfuse_client, is_langfuse_enabled

logger = logging.getLogger(__name__)


def canonical_json_dumps(obj: Any) -> str:
    """Canonical JSON serialization: sorted keys, UTF-8 encoding."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False).encode('utf-8').decode('utf-8')


def compute_sha256(data: str) -> str:
    """Compute SHA-256 hash of string data."""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def compute_sha256_json(obj: Any) -> str:
    """Compute SHA-256 hash of canonical JSON representation."""
    return hashlib.sha256(canonical_json_dumps(obj).encode('utf-8')).hexdigest()


class EvalBundleService:
    """Service for generating eval bundles from workflow executions."""
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
    
    def generate_bundle(
        self,
        execution_id: int,
        agent_name: str,
        attempt: Optional[int] = None,
        inline_large_text: bool = False,
        max_inline_chars: int = 200000
    ) -> Dict[str, Any]:
        """
        Generate eval bundle for a specific LLM call within a workflow execution.
        
        Args:
            execution_id: Workflow execution ID
            agent_name: Agent name (e.g., "CmdlineExtract", "rank_article")
            attempt: Attempt number (1-indexed)
            inline_large_text: Whether to inline large text fields
            max_inline_chars: Maximum characters to inline before truncation
        
        Returns:
            Eval bundle dict conforming to eval_bundle_v1 schema
        """
        warnings: List[str] = []
        
        # Fetch execution
        execution = self.db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.id == execution_id
        ).first()
        
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        
        # Log available agents for debugging
        # Ensure error_log is a dict (JSONB might be string)
        error_log_raw = execution.error_log
        if isinstance(error_log_raw, str):
            try:
                error_log = json.loads(error_log_raw)
            except (json.JSONDecodeError, TypeError):
                error_log = {}
        elif isinstance(error_log_raw, dict):
            error_log = error_log_raw
        else:
            error_log = {}
        
        if isinstance(error_log, dict):
            available_keys = list(error_log.keys())
            logger.debug(f"Execution {execution_id} error_log keys: {available_keys}")
        else:
            logger.debug(f"Execution {execution_id} error_log is not a dict: {type(error_log)}")
        
        # Fetch article
        article = self.db_session.query(ArticleTable).filter(
            ArticleTable.id == execution.article_id
        ).first()
        
        if not article:
            warnings.append("ARTICLE_NOT_FOUND")
            article_text = None
            article_sha256 = None
            article_length = 0
        else:
            article_text = article.content
            if article_text:
                article_sha256 = compute_sha256(article_text)
                article_length = len(article_text)
            else:
                warnings.append("FULL_ARTICLE_TEXT_MISSING")
                article_text = None
                article_sha256 = None
                article_length = 0
        
        # Extract LLM call data from error_log
        llm_request, llm_response, request_warnings, actual_attempt = self._extract_llm_call_data(
            execution, agent_name, attempt
        )
        warnings.extend(request_warnings)
        
        # Get workflow metadata (will update attempt after extracting LLM data)
        workflow_meta = self._extract_workflow_metadata(execution)
        
        # Get system prompt
        system_prompt_data = self._extract_system_prompt(execution, agent_name, warnings)
        
        # Build inputs array
        inputs = []
        
        # Article text input
        if article_text:
            was_truncated = False
            if not inline_large_text and article_length > max_inline_chars:
                article_text = article_text[:max_inline_chars] + "... [truncated]"
                was_truncated = True
                warnings.append("ARTICLE_TEXT_TRUNCATED_IN_BUNDLE")
            
            inputs.append({
                "name": "article_text",
                "source": "postgres",
                "text": article_text,
                "sha256": article_sha256,
                "length_chars": article_length,
                "was_truncated_anywhere": was_truncated
            })
        else:
            inputs.append({
                "name": "article_text",
                "source": "postgres",
                "text": None,
                "sha256": None,
                "length_chars": 0,
                "was_truncated_anywhere": False
            })
        
        # System prompt input
        inputs.append(system_prompt_data)
        
        # Update workflow metadata with actual attempt used
        workflow_meta["agent_name"] = agent_name
        workflow_meta["attempt"] = actual_attempt or 1
        
        # Get expected count from SubagentEvaluationTable if available
        # Map agent names to subagent names
        agent_to_subagent_map = {
            "CmdlineExtract": "cmdline",
            "ProcTreeExtract": "process_lineage"
        }
        subagent_name = agent_to_subagent_map.get(agent_name)
        expected_count = None
        if subagent_name:
            subagent_eval = self.db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.workflow_execution_id == execution_id,
                SubagentEvaluationTable.subagent_name == subagent_name
            ).first()
            if subagent_eval:
                expected_count = subagent_eval.expected_count
        
        if expected_count is not None:
            workflow_meta["expected_count"] = expected_count
        
        # Build bundle (without bundle_sha256 for now)
        bundle = {
            "schema_version": "eval_bundle_v1",
            "collected_at": datetime.utcnow().isoformat() + "Z",
            "bundle_id": str(uuid4()),
            "workflow": workflow_meta,
            "llm_request": llm_request,
            "llm_response": llm_response,
            "inputs": inputs,
            "integrity": {
                "bundle_sha256": "",  # Will compute after
                "warnings": warnings
            }
        }
        
        # Compute bundle SHA256 (excluding bundle_sha256 field)
        bundle_for_hash = bundle.copy()
        bundle_for_hash["integrity"] = {
            "bundle_sha256": "",
            "warnings": warnings
        }
        bundle_sha256 = compute_sha256_json(bundle_for_hash)
        bundle["integrity"]["bundle_sha256"] = bundle_sha256
        
        return bundle
    
    def _extract_llm_call_data(
        self,
        execution: AgenticWorkflowExecutionTable,
        agent_name: str,
        attempt: Optional[int]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str], Optional[int]]:
        """Extract LLM request/response data from execution error_log."""
        warnings: List[str] = []
        
        # Ensure error_log is a dict (JSONB might be string)
        error_log_raw = execution.error_log
        if error_log_raw is None:
            error_log = {}
        elif isinstance(error_log_raw, str):
            try:
                error_log = json.loads(error_log_raw)
                if not isinstance(error_log, dict):
                    logger.warning(f"Execution {execution.id}: error_log parsed to non-dict: {type(error_log)}")
                    error_log = {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Execution {execution.id}: Failed to parse error_log: {e}")
                error_log = {}
        elif isinstance(error_log_raw, dict):
            error_log = error_log_raw
        else:
            logger.warning(f"Execution {execution.id}: error_log is unexpected type: {type(error_log_raw)}")
            error_log = {}
        
        # Map agent names to error_log keys
        agent_key_map = {
            "rank_article": "rank_article",
            "extract_agent": "extract_agent",
            "generate_sigma": "generate_sigma",
            "os_detection": "os_detection",
            "CmdlineExtract": "extract_agent",
            "ProcTreeExtract": "extract_agent"
        }
        
        log_key = agent_key_map.get(agent_name, agent_name)
        agent_log = error_log.get(log_key, {}) if isinstance(error_log, dict) else {}
        
        if not agent_log or not isinstance(agent_log, dict):
            # Provide helpful error message
            if isinstance(error_log, dict):
                available_keys = list(error_log.keys())
            else:
                available_keys = []
            error_msg = f"AGENT_LOG_MISSING: {log_key}. Available keys in error_log: {available_keys}"
            warnings.append(error_msg)
            logger.warning(f"Execution {execution.id}: {error_msg}")
            return self._empty_llm_request(), self._empty_llm_response(), warnings, None
        
        conversation_log = agent_log.get("conversation_log", [])
        if not conversation_log or not isinstance(conversation_log, list):
            warnings.append("CONVERSATION_LOG_MISSING")
            return self._empty_llm_request(), self._empty_llm_response(), warnings, None
        
        # Find the specific attempt or agent entry
        attempt_entry = None
        
        # For extract_agent, entries might have 'agent' field for sub-agents
        if log_key == "extract_agent":
            # First try to find by agent name (for sub-agents like CmdlineExtract)
            for entry in conversation_log:
                if isinstance(entry, dict):
                    entry_agent = entry.get("agent", "")
                    # Match if agent name matches (case-insensitive)
                    if entry_agent and entry_agent.lower() == agent_name.lower():
                        attempt_entry = entry
                        break
                    # Also check if it's an attempt-based entry (unlikely for extract_agent)
                    if attempt and entry.get("attempt") == attempt:
                        attempt_entry = entry
                        break
        else:
            # For other agents, find by attempt number if specified
            if attempt:
                for entry in conversation_log:
                    if isinstance(entry, dict) and entry.get("attempt") == attempt:
                        attempt_entry = entry
                        break
            # If attempt not specified or not found, use last entry
            if not attempt_entry and conversation_log:
                attempt_entry = conversation_log[-1]
                if attempt:
                    warnings.append(f"ATTEMPT_{attempt}_NOT_FOUND_USING_LAST")
        
        if not attempt_entry:
            if conversation_log:
                # Fallback to last entry
                attempt_entry = conversation_log[-1]
                warnings.append("NO_MATCHING_ENTRY_USING_LAST")
            else:
                warnings.append("NO_CONVERSATION_ENTRIES")
                return self._empty_llm_request(), self._empty_llm_response(), warnings, None
        
        # Ensure attempt_entry is a dict before accessing
        if not isinstance(attempt_entry, dict):
            warnings.append("ATTEMPT_ENTRY_NOT_DICT")
            return self._empty_llm_request(), self._empty_llm_response(), warnings, None
        
        # Extract the actual attempt number used (for metadata)
        actual_attempt = attempt_entry.get("attempt")
        if actual_attempt is None and log_key == "extract_agent":
            # For extract_agent sub-agents, attempt is not used
            actual_attempt = 1  # Default for sub-agents
        
        # Extract messages
        # Priority: 1) direct in attempt_entry, 2) in result._llm_messages (new storage), 3) in result.raw
        messages = attempt_entry.get("messages", [])
        if not messages:
            result = attempt_entry.get("result", {})
            if isinstance(result, dict):
                # Check new storage location first (from llm_service changes)
                if "_llm_messages" in result:
                    messages = result["_llm_messages"]
                # Fallback to old locations
                elif "raw" in result:
                    raw_data = result.get("raw", {})
                    if isinstance(raw_data, dict):
                        if "messages" in raw_data:
                            messages = raw_data["messages"]
                        # Also check for conversation_log in raw
                        if not messages and "conversation_log" in raw_data:
                            conv_log = raw_data["conversation_log"]
                            if isinstance(conv_log, list) and conv_log:
                                last_entry = conv_log[-1]
                                if isinstance(last_entry, dict):
                                    messages = last_entry.get("messages", [])
        
        # Extract response
        # Priority: 1) direct in attempt_entry, 2) in result._llm_response (new storage), 3) in result.raw
        llm_response_text = attempt_entry.get("llm_response", "")
        if not llm_response_text:
            result = attempt_entry.get("result", {})
            if isinstance(result, dict):
                # Check new storage location first (from llm_service changes)
                if "_llm_response" in result:
                    llm_response_text = result["_llm_response"]
                # Fallback to old locations
                elif "raw" in result:
                    raw_data = result.get("raw", {})
                    if isinstance(raw_data, dict):
                        if "llm_response" in raw_data:
                            llm_response_text = raw_data["llm_response"]
                        elif "response" in raw_data:
                            llm_response_text = raw_data["response"]
                        # Also check for conversation_log in raw
                        if not llm_response_text and "conversation_log" in raw_data:
                            conv_log = raw_data["conversation_log"]
                            if isinstance(conv_log, list) and conv_log:
                                last_entry = conv_log[-1]
                                if isinstance(last_entry, dict):
                                    llm_response_text = last_entry.get("llm_response", "")
        
        # Always try to fetch from Langfuse if enabled (prefer Langfuse as source of truth)
        langfuse_messages = None
        langfuse_response = None
        langfuse_usage = None
        
        langfuse_enabled = is_langfuse_enabled()
        logger.info(f"Langfuse enabled check: {langfuse_enabled} for execution {execution.id}, agent {agent_name}")
        
        if langfuse_enabled:
            logger.info(f"Fetching Langfuse generation data for execution {execution.id}, agent {agent_name}, attempt {actual_attempt}")
            langfuse_data = self._fetch_langfuse_generation(
                execution_id=execution.id,
                agent_name=agent_name,
                attempt=actual_attempt,
                execution=execution
            )
            if langfuse_data:
                langfuse_messages = langfuse_data.get("messages")
                langfuse_response = langfuse_data.get("response")
                langfuse_usage = langfuse_data.get("usage")
                logger.info(f"✅ Langfuse data retrieved: messages={bool(langfuse_messages)} (len={len(langfuse_messages) if langfuse_messages else 0}), response={bool(langfuse_response)} (len={len(langfuse_response) if langfuse_response else 0}), usage={bool(langfuse_usage)}")
            else:
                logger.warning(f"⚠️ Langfuse enabled but no generation data returned for execution {execution.id}, agent {agent_name}, attempt {actual_attempt}")
        else:
            logger.warning(f"⚠️ Langfuse not enabled, skipping fetch for execution {execution.id}. Check LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY settings.")
        
        # Use Langfuse data if available (prefer Langfuse as source of truth), otherwise use what we found
        if langfuse_messages:
            messages = langfuse_messages
            warnings.append("MESSAGES_FETCHED_FROM_LANGFUSE")
        elif not messages or (isinstance(messages, list) and len(messages) == 0):
            warnings.append("MESSAGES_MISSING - LLM request messages not found in conversation_log entry or Langfuse")
            messages = []
        
        if langfuse_response:
            llm_response_text = langfuse_response
            warnings.append("RESPONSE_FETCHED_FROM_LANGFUSE")
        elif not llm_response_text or (isinstance(llm_response_text, str) and len(llm_response_text.strip()) == 0):
            warnings.append("RESPONSE_MISSING - LLM response text not found in conversation_log entry or Langfuse")
        
        # Get model/provider from config_snapshot or metadata
        # Ensure config_snapshot is a dict (JSONB might be string)
        config_snapshot_raw = execution.config_snapshot
        if isinstance(config_snapshot_raw, str):
            try:
                config_snapshot = json.loads(config_snapshot_raw)
            except (json.JSONDecodeError, TypeError):
                config_snapshot = {}
        elif isinstance(config_snapshot_raw, dict):
            config_snapshot = config_snapshot_raw
        else:
            config_snapshot = {}
        
        # Ensure agent_models is a dict
        agent_models_raw = config_snapshot.get("agent_models", {}) if isinstance(config_snapshot, dict) else {}
        if isinstance(agent_models_raw, str):
            try:
                agent_models = json.loads(agent_models_raw)
            except (json.JSONDecodeError, TypeError):
                agent_models = {}
        elif isinstance(agent_models_raw, dict):
            agent_models = agent_models_raw
        else:
            agent_models = {}
        
        # Map agent names to model config keys
        model_key_map = {
            "rank_article": "RankAgent",
            "extract_agent": "ExtractAgent",
            "generate_sigma": "SigmaAgent",
            "os_detection": "OSDetectionAgent",
            "CmdlineExtract": "ExtractAgent",
            "ProcTreeExtract": "ExtractAgent"
        }
        
        model_config_key = model_key_map.get(agent_name, agent_name)
        
        # Safely get model_config from agent_models
        try:
            if not isinstance(agent_models, dict):
                logger.warning(f"Execution {execution.id}: agent_models is not a dict: {type(agent_models)}, value: {str(agent_models)[:100]}")
                model_config_raw = {}
            else:
                model_config_raw = agent_models.get(model_config_key, {})
        except AttributeError as e:
            logger.error(f"Execution {execution.id}: AttributeError accessing agent_models: {e}, type: {type(agent_models)}")
            model_config_raw = {}
        
        # Ensure model_config is a dict
        if isinstance(model_config_raw, str):
            try:
                model_config = json.loads(model_config_raw)
                if not isinstance(model_config, dict):
                    logger.warning(f"Execution {execution.id}: model_config parsed to non-dict: {type(model_config)}")
                    model_config = {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Execution {execution.id}: Failed to parse model_config: {e}")
                model_config = {}
        elif isinstance(model_config_raw, dict):
            model_config = model_config_raw
        else:
            logger.warning(f"Execution {execution.id}: model_config_raw is unexpected type: {type(model_config_raw)}")
            model_config = {}
        
        # Safely extract values from model_config
        if not isinstance(model_config, dict):
            provider = "lmstudio"
            model = "unknown"
            temperature = 0.0
            top_p = None
            max_tokens = None
        else:
            provider = model_config.get("provider", "lmstudio")
            model = model_config.get("model", "unknown")
            temperature = model_config.get("temperature", 0.0)
            top_p = model_config.get("top_p")
            max_tokens = model_config.get("max_tokens")
        
        # Build request payload (reconstructed from messages)
        request_payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        if top_p is not None:
            request_payload["top_p"] = top_p
        if max_tokens is not None:
            request_payload["max_tokens"] = max_tokens
        
        payload_sha256 = compute_sha256_json(request_payload)
        
        # Determine if we have actual data (not reconstructed)
        has_actual_messages = bool(messages and len(messages) > 0)
        has_actual_response = bool(llm_response_text and len(llm_response_text.strip()) > 0)
        
        llm_request = {
            "provider": provider,
            "model": model,
            "parameters": {
                "temperature": temperature,
                "top_p": top_p,
                "top_k": None,
                "max_tokens": max_tokens,
                "stop": None,
                "seed": None,
                "presence_penalty": None,
                "frequency_penalty": None,
                "repetition_penalty": None,
                "response_format": None,
                "other": None
            },
            "raw_payload": request_payload,
            "messages": messages,
            "payload_sha256": payload_sha256,
            "reconstructed": not has_actual_messages  # Only mark as reconstructed if we don't have actual messages
        }
        
        # Build response
        response_payload = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": llm_response_text
                },
                "finish_reason": "stop"
            }]
        }
        
        response_sha256 = compute_sha256_json(response_payload)
        
        llm_response = {
            "raw_response": response_payload,
            "text_output": llm_response_text,
            "finish_reason": "stop",
            "usage": None,  # Not stored in conversation_log
            "response_sha256": response_sha256,
            "reconstructed": not has_actual_response  # Only mark as reconstructed if we don't have actual response
        }
        
        # Update usage if we got it from Langfuse
        if langfuse_usage and isinstance(llm_response, dict):
            llm_response["usage"] = langfuse_usage
        
        # Only warn about reconstruction if we're actually missing data
        # If we have actual messages/response (from Postgres or Langfuse), no warning needed
        if not has_actual_messages and not langfuse_messages:
            warnings.append("REQUEST_PAYLOAD_RECONSTRUCTED")
        if not has_actual_response and not langfuse_response:
            warnings.append("RESPONSE_RECONSTRUCTED")
        
        return llm_request, llm_response, warnings, actual_attempt
    
    def _fetch_langfuse_generation(
        self,
        execution_id: int,
        agent_name: str,
        attempt: Optional[int],
        execution: Optional[AgenticWorkflowExecutionTable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch LLM generation data from Langfuse for a specific agent call.
        
        Returns dict with 'messages', 'response', and 'usage' if found, None otherwise.
        """
        if not is_langfuse_enabled():
            return None
        
        client = get_langfuse_client()
        if not client:
            return None
        
        try:
            # Build session_id (matches what trace_llm_call uses)
            session_id = f"workflow_exec_{execution_id}"
            
            # Try to get trace_id from execution.error_log if available
            trace_id = None
            if execution:
                error_log_raw = execution.error_log
                if isinstance(error_log_raw, dict):
                    trace_id = error_log_raw.get("langfuse_trace_id")
                elif isinstance(error_log_raw, str):
                    try:
                        error_log = json.loads(error_log_raw)
                        if isinstance(error_log, dict):
                            trace_id = error_log.get("langfuse_trace_id")
                    except (json.JSONDecodeError, TypeError):
                        pass
            
            # Build generation name pattern
            # For CmdlineExtract: "cmdlineextract_extraction"
            # For other agents: "{agent_name.lower()}_extraction" or similar
            generation_name_pattern = f"{agent_name.lower()}_extraction"
            
            logger.info(f"Querying Langfuse for session_id={session_id}, trace_id={trace_id}, agent={agent_name}, pattern={generation_name_pattern}")
            
            # Query Langfuse for generations in this session
            # Try to get the generation that matches our agent
            try:
                # Try querying by session_id first (preferred method)
                generations = None
                query_method = None
                
                try:
                    generations = client.api.generations.list(
                        session_id=session_id,
                        limit=100,  # Get enough to find our agent
                        order_by="timestamp.desc"
                    )
                    query_method = "session_id"
                    logger.debug(f"Langfuse API call by session_id completed, response type: {type(generations)}")
                except Exception as session_query_error:
                    logger.warning(f"Failed to query Langfuse by session_id {session_id}: {session_query_error}")
                    
                    # Fallback 1: Try querying by trace_id if available
                    if trace_id:
                        try:
                            generations = client.api.generations.list(
                                trace_id=trace_id,
                                limit=100,
                                order_by="timestamp.desc"
                            )
                            query_method = "trace_id"
                            logger.debug(f"Langfuse API call by trace_id completed")
                        except Exception as trace_query_error:
                            logger.warning(f"Failed to query Langfuse by trace_id {trace_id}: {trace_query_error}")
                    
                    # Fallback 2: Try querying without filters (less efficient)
                    if not generations:
                        try:
                            all_generations = client.api.generations.list(
                                limit=1000,  # Need more since we're not filtering
                                order_by="timestamp.desc"
                            )
                            logger.debug(f"Langfuse API call without filters completed, got {len(all_generations.data) if hasattr(all_generations, 'data') else 0} total generations")
                            
                            # Filter by session_id manually
                            if hasattr(all_generations, 'data') and all_generations.data:
                                filtered = [
                                    gen for gen in all_generations.data 
                                    if (hasattr(gen, 'session_id') and getattr(gen, 'session_id') == session_id) or
                                       (trace_id and hasattr(gen, 'trace_id') and getattr(gen, 'trace_id') == trace_id)
                                ]
                                # Create a mock response object
                                class MockResponse:
                                    def __init__(self, data):
                                        self.data = data
                                generations = MockResponse(filtered)
                                query_method = "manual_filter"
                                logger.debug(f"Manually filtered to {len(filtered)} generations matching session_id or trace_id")
                        except Exception as fallback_error:
                            logger.error(f"All Langfuse query methods failed. Last error: {fallback_error}", exc_info=True)
                            return None
                
                if not generations or not hasattr(generations, 'data') or not generations.data:
                    logger.warning(f"No Langfuse generations found for session {session_id}")
                    return None
                
                logger.debug(f"Found {len(generations.data)} generations in session {session_id}, searching for agent {agent_name} (pattern: {generation_name_pattern})")
                
                # Find generation matching our agent name
                matching_generation = None
                for gen in generations.data:
                    gen_name = getattr(gen, 'name', '')
                    gen_metadata = getattr(gen, 'metadata', {}) or {}
                    if not isinstance(gen_metadata, dict):
                        # metadata might be a string or other type
                        try:
                            if isinstance(gen_metadata, str):
                                gen_metadata = json.loads(gen_metadata)
                            else:
                                gen_metadata = {}
                        except (json.JSONDecodeError, TypeError):
                            gen_metadata = {}
                    
                    logger.debug(f"Checking generation: name='{gen_name}', metadata.agent_name='{gen_metadata.get('agent_name', '')}'")
                    
                    # Check if name matches or metadata has matching agent_name
                    if (generation_name_pattern in gen_name.lower() or 
                        gen_metadata.get('agent_name', '').lower() == agent_name.lower()):
                        matching_generation = gen
                        logger.info(f"Found matching generation: name='{gen_name}' for agent {agent_name}")
                        break
                
                if not matching_generation:
                    # Log all generation names for debugging
                    all_names = [getattr(gen, 'name', '') for gen in generations.data]
                    logger.warning(f"No matching Langfuse generation found for agent {agent_name} (pattern: {generation_name_pattern}) in session {session_id}. Available generation names: {all_names}")
                    return None
                
                # Extract data from generation
                result = {}
                
                # For extraction agents, log_llm_completion stores:
                # - input: dataset-compatible dict ({"article_text": ...}) if input_object provided
                # - model_parameters.messages: actual messages array (always stored here)
                # So we should check model_parameters.messages FIRST, then fall back to input
                
                # Check model_parameters.messages first (this is where messages are stored by log_llm_completion)
                gen_model_params = getattr(matching_generation, 'model_parameters', None)
                if gen_model_params:
                    logger.debug(f"Checking model_parameters for messages, type: {type(gen_model_params)}")
                    if isinstance(gen_model_params, dict):
                        if 'messages' in gen_model_params:
                            result['messages'] = gen_model_params['messages']
                            logger.debug(f"Extracted {len(gen_model_params['messages'])} messages from model_parameters")
                    # model_parameters might also be a string (JSON)
                    elif isinstance(gen_model_params, str):
                        try:
                            model_params_dict = json.loads(gen_model_params)
                            if isinstance(model_params_dict, dict) and 'messages' in model_params_dict:
                                result['messages'] = model_params_dict['messages']
                                logger.debug(f"Extracted {len(model_params_dict['messages'])} messages from model_parameters JSON string")
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.debug(f"Failed to parse model_parameters JSON: {e}")
                
                # Fallback: check input (might be messages array if input_object wasn't provided)
                if not result.get('messages'):
                    gen_input = getattr(matching_generation, 'input', None)
                    logger.debug(f"Generation input type: {type(gen_input)}, value preview: {str(gen_input)[:200] if gen_input else None}")
                    
                    if gen_input:
                        # Input might be messages array or dict with messages
                        if isinstance(gen_input, list):
                            # Assume it's messages array (from trace_llm_call with metadata["messages"])
                            result['messages'] = gen_input
                            logger.debug(f"Extracted {len(gen_input)} messages from input list")
                        elif isinstance(gen_input, dict):
                            # Check if messages are in the dict
                            if 'messages' in gen_input:
                                result['messages'] = gen_input['messages']
                                logger.debug(f"Extracted {len(gen_input['messages'])} messages from input dict")
                
                # Get output (response text)
                # For extraction agents, output is json.dumps(output_for_langfuse) which is the parsed result JSON string
                # This is NOT the raw LLM response text, but it's what we have
                gen_output = getattr(matching_generation, 'output', None)
                logger.debug(f"Generation output type: {type(gen_output)}, preview: {str(gen_output)[:200] if gen_output else None}")
                
                if gen_output:
                    if isinstance(gen_output, str):
                        result['response'] = gen_output
                        logger.debug(f"Extracted response string (length: {len(gen_output)})")
                    elif isinstance(gen_output, dict):
                        # Might be structured output (from extraction agents)
                        # Try to get text content, or serialize the dict
                        if 'text' in gen_output:
                            result['response'] = gen_output['text']
                        elif 'content' in gen_output:
                            result['response'] = gen_output['content']
                        else:
                            # For extraction agents, output might be the parsed result
                            # Try to extract a meaningful text representation
                            result['response'] = json.dumps(gen_output, indent=2)
                            logger.debug(f"Extracted response from dict (serialized, length: {len(result['response'])})")
                
                # Get usage (stored in usage_details by log_llm_completion)
                gen_usage_details = getattr(matching_generation, 'usage_details', None)
                if gen_usage_details:
                    if isinstance(gen_usage_details, dict):
                        result['usage'] = gen_usage_details
                    else:
                        # Usage might be an object with attributes
                        result['usage'] = {
                            'prompt_tokens': getattr(gen_usage_details, 'prompt_tokens', None),
                            'completion_tokens': getattr(gen_usage_details, 'completion_tokens', None),
                            'total_tokens': getattr(gen_usage_details, 'total_tokens', None)
                        }
                else:
                    # Fallback to usage field if usage_details not available
                    gen_usage = getattr(matching_generation, 'usage', None)
                    if gen_usage:
                        if isinstance(gen_usage, dict):
                            result['usage'] = gen_usage
                        else:
                            result['usage'] = {
                                'prompt_tokens': getattr(gen_usage, 'prompt_tokens', None),
                                'completion_tokens': getattr(gen_usage, 'completion_tokens', None),
                                'total_tokens': getattr(gen_usage, 'total_tokens', None)
                            }
                
                if result:
                    logger.info(f"Fetched Langfuse data for {agent_name} in execution {execution_id}: found messages={bool(result.get('messages'))}, response={bool(result.get('response'))}")
                    return result
                else:
                    logger.debug(f"Langfuse generation found but no extractable data for {agent_name}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error querying Langfuse API for execution {execution_id}, session {session_id}: {e}", exc_info=True)
                return None
                
        except Exception as e:
            logger.error(f"Error fetching Langfuse generation for execution {execution_id}, agent {agent_name}: {e}", exc_info=True)
            return None
    
    def _extract_workflow_metadata(
        self,
        execution: AgenticWorkflowExecutionTable
    ) -> Dict[str, Any]:
        """Extract workflow metadata from execution."""
        # Ensure config_snapshot is a dict (JSONB might be string)
        config_snapshot_raw = execution.config_snapshot
        if isinstance(config_snapshot_raw, str):
            try:
                config_snapshot = json.loads(config_snapshot_raw)
            except (json.JSONDecodeError, TypeError):
                config_snapshot = {}
        elif isinstance(config_snapshot_raw, dict):
            config_snapshot = config_snapshot_raw
        else:
            config_snapshot = {}
        
        # Get prompt versions from config
        agent_prompts = config_snapshot.get("agent_prompts", {}) if isinstance(config_snapshot, dict) else {}
        workflow_config_version = config_snapshot.get("config_version") if isinstance(config_snapshot, dict) else None
        
        return {
            "execution_id": str(execution.id),
            "article_id": str(execution.article_id) if execution.article_id else None,
            "workflow_type": "agentic_workflow",
            "agent_name": "unknown",  # Will be set by caller
            "attempt": None,  # Will be set after extracting LLM data
            "run_started_at": execution.started_at.isoformat() + "Z" if execution.started_at else None,
            "run_finished_at": execution.completed_at.isoformat() + "Z" if execution.completed_at else None,
            "versions": {
                "app_version": None,  # Not tracked
                "workflow_version": None,  # Not tracked
                "agent_prompt_version": None  # Could extract from AgentPromptVersionTable
            }
        }
    
    def _extract_system_prompt(
        self,
        execution: AgenticWorkflowExecutionTable,
        agent_name: str,
        warnings: List[str]
    ) -> Dict[str, Any]:
        """Extract system prompt for agent."""
        # Ensure config_snapshot is a dict (JSONB might be string)
        config_snapshot_raw = execution.config_snapshot
        if isinstance(config_snapshot_raw, str):
            try:
                config_snapshot = json.loads(config_snapshot_raw)
            except (json.JSONDecodeError, TypeError):
                config_snapshot = {}
        elif isinstance(config_snapshot_raw, dict):
            config_snapshot = config_snapshot_raw
        else:
            config_snapshot = {}
        
        # Ensure agent_prompts is a dict
        agent_prompts_raw = config_snapshot.get("agent_prompts", {}) if isinstance(config_snapshot, dict) else {}
        if isinstance(agent_prompts_raw, str):
            try:
                agent_prompts = json.loads(agent_prompts_raw)
            except (json.JSONDecodeError, TypeError):
                agent_prompts = {}
        elif isinstance(agent_prompts_raw, dict):
            agent_prompts = agent_prompts_raw
        else:
            agent_prompts = {}
        
        # Map agent names to prompt config keys
        prompt_key_map = {
            "rank_article": "RankAgent",
            "extract_agent": "ExtractAgent",
            "generate_sigma": "SigmaAgent",
            "os_detection": "OSDetectionAgent"
        }
        
        prompt_key = prompt_key_map.get(agent_name, agent_name)
        prompt_config_raw = agent_prompts.get(prompt_key, {}) if isinstance(agent_prompts, dict) else {}
        
        # Ensure prompt_config is a dict
        if isinstance(prompt_config_raw, str):
            try:
                prompt_config = json.loads(prompt_config_raw)
            except (json.JSONDecodeError, TypeError):
                prompt_config = {}
        elif isinstance(prompt_config_raw, dict):
            prompt_config = prompt_config_raw
        else:
            prompt_config = {}
        
        system_prompt_text = None
        if isinstance(prompt_config, dict):
            system_prompt_text = prompt_config.get("prompt") or prompt_config.get("system_prompt")
        
        if not system_prompt_text:
            warnings.append("PROMPT_TEXT_MISSING")
            return {
                "name": "system_prompt",
                "source": "postgres",
                "text": None,
                "ref": None,
                "sha256": None,
                "length_chars": 0,
                "was_truncated_anywhere": False
            }
        
        prompt_sha256 = compute_sha256(system_prompt_text)
        
        return {
            "name": "system_prompt",
            "source": "postgres",
            "text": system_prompt_text,
            "ref": None,  # Could extract from AgentPromptVersionTable
            "sha256": prompt_sha256,
            "length_chars": len(system_prompt_text),
            "was_truncated_anywhere": False
        }
    
    def _empty_llm_request(self) -> Dict[str, Any]:
        """Return empty LLM request structure."""
        return {
            "provider": None,
            "model": None,
            "parameters": {
                "temperature": None,
                "top_p": None,
                "top_k": None,
                "max_tokens": None,
                "stop": None,
                "seed": None,
                "presence_penalty": None,
                "frequency_penalty": None,
                "repetition_penalty": None,
                "response_format": None,
                "other": None
            },
            "raw_payload": {},
            "messages": None,
            "payload_sha256": None,
            "reconstructed": False
        }
    
    def _empty_llm_response(self) -> Dict[str, Any]:
        """Return empty LLM response structure."""
        return {
            "raw_response": {},
            "text_output": "",
            "finish_reason": None,
            "usage": None,
            "response_sha256": None,
            "reconstructed": False
        }
