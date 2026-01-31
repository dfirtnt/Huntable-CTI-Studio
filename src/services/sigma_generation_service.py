"""
SIGMA Rule Generation Service.

Reusable service for generating SIGMA rules from articles using LLM.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import yaml

from src.services.llm_service import LLMService
from src.services.sigma_validator import ValidationResult, clean_sigma_rule, validate_sigma_rule
from src.utils.langfuse_client import log_llm_completion, log_llm_error, trace_llm_call
from src.utils.llm_optimizer import optimize_article_content

logger = logging.getLogger(__name__)


@dataclass
class RuleValidationResult:
    """Result of validating a single rule."""

    rule_id: str
    rule_yaml: str
    validation_result: ValidationResult
    rule_index: int
    generation_phase: str = "generation"
    repair_attempts: list[dict[str, Any]] = None
    final_status: str = "pending"

    def __post_init__(self):
        if self.repair_attempts is None:
            self.repair_attempts = []


@dataclass
class ValidationResults:
    """Categorized validation results."""

    valid_rules: list[RuleValidationResult]
    invalid_rules: list[RuleValidationResult]
    all_rules: list[RuleValidationResult]


class SigmaGenerationService:
    """Service for generating SIGMA rules from articles."""

    def __init__(self, config_models: dict[str, str] | None = None):
        """
        Initialize SIGMA generation service.

        Args:
            config_models: Optional dict of agent models from workflow config.
                          Format: {"RankAgent": "model_name", "ExtractAgent": "...", "SigmaAgent": "..."}
                          If provided, these override environment variables.
        """
        self.llm_service = LLMService(config_models=config_models)

    async def generate_sigma_rules(
        self,
        article_title: str,
        article_content: str,
        source_name: str,
        url: str,
        ai_model: str = "lmstudio",
        api_key: str | None = None,
        max_attempts: int = 3,
        min_confidence: float = 0.7,
        execution_id: int | None = None,
        article_id: int | None = None,
        qa_feedback: str | None = None,
        sigma_prompt_template: str | None = None,
        sigma_system_prompt: str | None = None,
        extraction_result: dict[str, Any] | None = None,
        enable_multi_rule_expansion: bool = True,
        max_repair_attempts_per_rule: int = 3,
    ) -> dict[str, Any]:
        """
        Generate SIGMA rules from article content using phased approach.

        Args:
            article_title: Article title
            article_content: Full article content
            source_name: Source name
            url: Article URL
            ai_model: AI model to use ('lmstudio' or 'chatgpt')
            api_key: OpenAI API key (required for ChatGPT)
            max_attempts: Maximum number of generation attempts (deprecated, kept for compatibility)
            min_confidence: Minimum confidence for content filtering
            extraction_result: Optional extraction result with observables for artifact-driven expansion
            enable_multi_rule_expansion: Whether to enable Phase 4 expansion
            max_repair_attempts_per_rule: Maximum repair attempts per individual rule

        Returns:
            Dict with 'rules' (list of validated rules), 'metadata', 'errors'
        """
        try:
            # Optimize content with filtering
            optimization_result = await optimize_article_content(article_content, min_confidence=min_confidence)

            if optimization_result["success"]:
                content_to_analyze = optimization_result["filtered_content"]
                logger.info(f"Content optimized: {optimization_result['tokens_saved']} tokens saved")
            else:
                content_to_analyze = article_content
                logger.warning("Content optimization failed, using original content")

            # Load SIGMA generation prompt (async to avoid blocking)
            # Use provided template from database if available, otherwise load from file
            sigma_prompt = None
            if sigma_prompt_template:
                # Format the database prompt template with article data
                try:
                    sigma_prompt = sigma_prompt_template.format(
                        title=article_title, source=source_name, url=url or "N/A", content=content_to_analyze
                    )
                    logger.info(f"Using database prompt template for SIGMA generation (len={len(sigma_prompt)} chars)")
                except (KeyError, AttributeError, ValueError) as e:
                    logger.warning(f"Database prompt template formatting failed ({e}), falling back to file")
                    sigma_prompt = None  # Ensure it's None so we fall through to file loading

            if not sigma_prompt:
                # Fallback to file-based prompt (use new multi-rule prompt, fallback to old for compatibility)
                from src.utils.prompt_loader import format_prompt_async

                try:
                    sigma_prompt = await format_prompt_async(
                        "sigma_generate_multi",
                        title=article_title,
                        source=source_name,
                        url=url or "N/A",
                        content=content_to_analyze,
                    )
                    if sigma_prompt and isinstance(sigma_prompt, str):
                        logger.info(
                            f"Using file-based multi-rule prompt for SIGMA generation (len={len(sigma_prompt)} chars)"
                        )
                except Exception as e:
                    # Fallback to old prompt for backward compatibility
                    logger.warning(f"Failed to load sigma_generate_multi prompt, falling back to sigma_generation: {e}")
                    sigma_prompt = await format_prompt_async(
                        "sigma_generation",
                        title=article_title,
                        source=source_name,
                        url=url or "N/A",
                        content=content_to_analyze,
                    )
                    if sigma_prompt and isinstance(sigma_prompt, str):
                        logger.info(f"Using file-based prompt for SIGMA generation (len={len(sigma_prompt)} chars)")

            # Ensure we have a valid prompt
            if not sigma_prompt or not isinstance(sigma_prompt, str):
                raise ValueError("Failed to load SIGMA generation prompt from both database and file")

            # Handle context window limits for LMStudio
            if ai_model == "lmstudio":
                lmstudio_model_name = self.llm_service.lmstudio_model
                if not lmstudio_model_name or not isinstance(lmstudio_model_name, str):
                    logger.warning(
                        f"lmstudio_model is None or not a string: {lmstudio_model_name}, using default context window"
                    )
                    max_prompt_chars = 8000
                elif "8b" in lmstudio_model_name.lower() or "7b" in lmstudio_model_name.lower():
                    max_prompt_chars = 12000
                elif "3b" in lmstudio_model_name.lower():
                    max_prompt_chars = 9000
                else:
                    max_prompt_chars = 8000

                if len(sigma_prompt) > max_prompt_chars:
                    logger.warning(f"Truncating prompt from {len(sigma_prompt)} to {max_prompt_chars} chars")
                    sigma_prompt = (
                        sigma_prompt[:max_prompt_chars] + "\n\n[Prompt truncated to fit model context window]"
                    )

            # Phase 1: Multi-rule generation (structurally constrained)
            logger.info("Phase 1: Multi-rule generation")
            generated_yaml = await self._generate_multi_rules(
                sigma_prompt=sigma_prompt,
                qa_feedback=qa_feedback,
                sigma_system_prompt=sigma_system_prompt,
                ai_model=ai_model,
                execution_id=execution_id,
                article_id=article_id,
            )

            # Phase 2: Validation & Categorization
            logger.info("Phase 2: Validation & categorization")
            validation_results = self._validate_all_rules(generated_yaml)

            # Phase 3: Per-rule repair (strict mode)
            logger.info(f"Phase 3: Per-rule repair ({len(validation_results.invalid_rules)} invalid rules)")
            repaired_results = await self._repair_rules(
                invalid_rules=validation_results.invalid_rules,
                max_repair_attempts_per_rule=max_repair_attempts_per_rule,
                execution_id=execution_id,
                article_id=article_id,
                sigma_system_prompt=sigma_system_prompt,
            )

            # Combine valid and repaired rules
            all_valid_rules = validation_results.valid_rules + repaired_results

            # Track all rules that went through repair (including failed ones) for attempt counting
            # Failed repair rules are still in validation_results.invalid_rules but with repair_attempts populated
            all_rules_with_repair_attempts = validation_results.all_rules.copy()

            # Phase 4: Optional expansion (artifact-driven)
            expansion_rules = []
            expansion_validation = None
            if enable_multi_rule_expansion and extraction_result:
                logger.info("Phase 4: Checking for expansion opportunities")
                expansion_needed, uncovered_categories = self._needs_expansion(
                    valid_rules=all_valid_rules, extraction_result=extraction_result
                )

                if expansion_needed:
                    logger.info(
                        f"Phase 4: Generating additional rules for uncovered categories: {uncovered_categories}"
                    )
                    expansion_prompt = await self._build_expansion_prompt(
                        sigma_prompt_template=sigma_prompt_template,
                        article_title=article_title,
                        source_name=source_name,
                        url=url,
                        content_to_analyze=content_to_analyze,
                        uncovered_categories=uncovered_categories,
                        extraction_result=extraction_result,
                    )

                    expansion_yaml = await self._generate_multi_rules(
                        sigma_prompt=expansion_prompt,
                        qa_feedback=None,
                        sigma_system_prompt=sigma_system_prompt,
                        ai_model=ai_model,
                        execution_id=execution_id,
                        article_id=article_id,
                    )

                    expansion_validation = self._validate_all_rules(expansion_yaml)
                    # Mark expansion rules with correct phase
                    for rule in expansion_validation.all_rules:
                        rule.generation_phase = "expansion"

                    # Repair expansion rules if needed
                    if expansion_validation.invalid_rules:
                        expansion_repaired = await self._repair_rules(
                            invalid_rules=expansion_validation.invalid_rules,
                            max_repair_attempts_per_rule=max_repair_attempts_per_rule,
                            execution_id=execution_id,
                            article_id=article_id,
                            sigma_system_prompt=sigma_system_prompt,
                        )
                        expansion_rules = expansion_validation.valid_rules + expansion_repaired
                    else:
                        expansion_rules = expansion_validation.valid_rules

            # Build final rules list and conversation log
            final_rules = []
            conversation_log = []

            # Process all rules and build rule-scoped logs
            for rule_result in all_valid_rules + expansion_rules:
                if rule_result.final_status == "valid" or rule_result.final_status == "repaired":
                    try:
                        parsed_yaml = yaml.safe_load(rule_result.rule_yaml)
                        if parsed_yaml:
                            detection = parsed_yaml.get("detection")
                            if detection and isinstance(detection, dict):
                                rule_metadata = {
                                    "title": parsed_yaml.get("title"),
                                    "description": parsed_yaml.get("description"),
                                    "id": parsed_yaml.get("id"),
                                    "tags": parsed_yaml.get("tags", []),
                                    "level": parsed_yaml.get("level"),
                                    "status": parsed_yaml.get("status", "experimental"),
                                    "logsource": parsed_yaml.get("logsource", {}),
                                    "detection": detection,
                                }
                                final_rules.append(rule_metadata)
                    except Exception as e:
                        logger.warning(f"Failed to parse rule {rule_result.rule_id}: {e}")

                # Build conversation log entry for this rule
                rule_log = {
                    "rule_id": rule_result.rule_id,
                    "generation_phase": rule_result.generation_phase,
                    "final_status": rule_result.final_status,
                    "repair_attempts": rule_result.repair_attempts,
                    "validation": {
                        "is_valid": rule_result.validation_result.is_valid,
                        "errors": rule_result.validation_result.errors,
                        "warnings": rule_result.validation_result.warnings,
                        "rule_index": rule_result.rule_index,
                    },
                }
                conversation_log.append(rule_log)

            # Build validation results summary
            # Include all rules (valid, invalid, repaired, failed) for attempt counting
            # validation_results.all_rules includes all Phase 2 rules (both valid and invalid)
            # Invalid rules that failed repair still have repair_attempts populated
            all_rules_for_counting = all_rules_with_repair_attempts.copy()

            # Add expansion rules (both valid and invalid) if expansion occurred
            if expansion_validation:
                # Include all expansion rules (valid + invalid) for attempt counting
                all_rules_for_counting.extend(expansion_validation.all_rules)

            all_validation_results = [
                {
                    "is_valid": r.validation_result.is_valid,
                    "errors": r.validation_result.errors,
                    "warnings": r.validation_result.warnings,
                    "rule_index": r.rule_index,
                }
                for r in validation_results.all_rules
                + (expansion_validation.all_rules if expansion_validation else expansion_rules)
            ]

            # Calculate total attempts: 1 initial attempt + repair attempts for each rule
            # This includes all rules (valid, invalid, repaired, failed)
            # Each rule gets 1 for initial generation + len(repair_attempts) for repair attempts
            # Minimum is 1 (the initial generation attempt) even if no rules were parsed
            total_attempts = sum(len(r.repair_attempts) + 1 for r in all_rules_for_counting)
            # Ensure at least 1 attempt is counted (the initial generation in Phase 1)
            # This handles cases where all generated YAML is rejected early (e.g., no title: found)
            if total_attempts == 0:
                total_attempts = 1  # At minimum, we made 1 generation attempt in Phase 1

            return {
                "rules": final_rules,
                "metadata": {
                    "total_attempts": total_attempts,
                    "valid_rules": len(final_rules),
                    "validation_results": all_validation_results,
                    "conversation_log": conversation_log,
                },
                "errors": None if final_rules else "No valid SIGMA rules could be generated after all phases",
            }

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            logger.error(f"Error generating SIGMA rules: {e}")
            return {"rules": [], "metadata": {}, "errors": str(e)}

    async def _generate_multi_rules(
        self,
        sigma_prompt: str,
        qa_feedback: str | None,
        sigma_system_prompt: str | None,
        ai_model: str,
        execution_id: int | None,
        article_id: int | None,
    ) -> str:
        """Phase 1: Generate multi-rule YAML with structural constraints."""
        # Prepare prompt
        current_prompt = sigma_prompt
        if qa_feedback:
            current_prompt = f"{qa_feedback}\n\n{current_prompt}"

        # Call LLM API
        sigma_provider = self.llm_service.provider_sigma
        requested_provider = self.llm_service._canonicalize_provider(ai_model)
        if ai_model and ai_model != "lmstudio" and requested_provider != "lmstudio":
            sigma_provider = requested_provider

        sigma_response = await self._call_provider_for_sigma(
            current_prompt,
            provider=sigma_provider,
            execution_id=execution_id,
            article_id=article_id,
            system_prompt=sigma_system_prompt,
        )

        if sigma_response is None:
            sigma_response = ""
        else:
            sigma_response = str(sigma_response)

        logger.info(f"Phase 1: Generated {len(sigma_response)} chars of YAML")
        return sigma_response

    def _validate_all_rules(self, yaml_content: str) -> ValidationResults:
        """Phase 2: Parse and validate all rules with defensive parsing."""
        # Handle multiple rules: first try extracting from markdown code blocks, then split by ---
        rule_blocks = []

        # Strategy 1: Extract from multiple markdown code blocks (backward compatibility)
        import re

        code_block_pattern = r"```(?:yaml|yml)?\s*\n(.*?)```"
        code_blocks = re.findall(code_block_pattern, yaml_content, re.DOTALL)
        if code_blocks:
            rule_blocks = [block.strip() for block in code_blocks]
            logger.debug(f"Extracted {len(rule_blocks)} rules from markdown code blocks")
        else:
            # Strategy 2: Split by --- separator (preferred for new prompt)
            cleaned_response = clean_sigma_rule(yaml_content)
            if "---" in cleaned_response:
                rule_blocks = cleaned_response.split("---")
                rule_blocks = [block.strip() for block in rule_blocks]
                logger.debug(f"Split by --- separator: {len(rule_blocks)} blocks")
            else:
                # Strategy 3: Try to find multiple title: entries (fallback)
                # Look for patterns like "title: ..." followed by another "title:" later
                title_pattern = r"(?:^|\n)title\s*:"
                title_matches = list(re.finditer(title_pattern, cleaned_response, re.MULTILINE))
                if len(title_matches) > 1:
                    # Split at each title: after the first one
                    rule_blocks = [cleaned_response[: title_matches[1].start()].strip()]
                    for i in range(1, len(title_matches)):
                        start = title_matches[i].start()
                        end = title_matches[i + 1].start() if i + 1 < len(title_matches) else len(cleaned_response)
                        rule_blocks.append(cleaned_response[start:end].strip())
                    logger.debug(f"Split by multiple title: entries: {len(rule_blocks)} blocks")
                else:
                    # Single rule - clean it
                    rule_blocks = [cleaned_response]

        all_rules = []
        valid_rules = []
        invalid_rules = []

        for i, block in enumerate(rule_blocks):
            block = block.strip()

            # Trim empty documents
            if not block:
                logger.debug(f"Skipping empty block {i + 1}")
                continue

            # Clean the block (in case it came from markdown extraction)
            cleaned_block = clean_sigma_rule(block)

            # Require title: at root level (fail closed)
            if "title:" not in cleaned_block[:200]:  # Check first 200 chars for title
                logger.warning(f"Block {i + 1} rejected: no 'title:' found at root level after cleaning")
                continue

            # Check if block looks like YAML structure
            has_yaml_structure = ":" in cleaned_block and any(
                key in cleaned_block for key in ["title", "id", "description", "logsource", "detection"]
            )

            if not has_yaml_structure:
                logger.warning(f"Block {i + 1} rejected: doesn't look like YAML")
                continue

            # Validate rule
            validation_result = validate_sigma_rule(cleaned_block)
            rule_id = str(uuid.uuid4())

            rule_result = RuleValidationResult(
                rule_id=rule_id,
                rule_yaml=cleaned_block,
                validation_result=validation_result,
                rule_index=i + 1,
                generation_phase="generation",
                final_status="valid" if validation_result.is_valid else "invalid",
            )

            all_rules.append(rule_result)

            if validation_result.is_valid:
                valid_rules.append(rule_result)
            else:
                invalid_rules.append(rule_result)

        logger.info(f"Phase 2: Parsed {len(all_rules)} rules ({len(valid_rules)} valid, {len(invalid_rules)} invalid)")

        return ValidationResults(valid_rules=valid_rules, invalid_rules=invalid_rules, all_rules=all_rules)

    async def _repair_rules(
        self,
        invalid_rules: list[RuleValidationResult],
        max_repair_attempts_per_rule: int,
        execution_id: int | None,
        article_id: int | None,
        sigma_system_prompt: str | None,
    ) -> list[RuleValidationResult]:
        """Phase 3: Repair invalid rules one at a time."""
        repaired_rules = []

        for rule_result in invalid_rules:
            logger.info(f"Repairing rule {rule_result.rule_id} (attempt 1/{max_repair_attempts_per_rule})")

            previous_errors_text = (
                "\n".join(rule_result.validation_result.errors)
                if rule_result.validation_result.errors
                else "No valid SIGMA YAML detected."
            )
            previous_yaml_preview = rule_result.rule_yaml[:500] if rule_result.rule_yaml else "No YAML was detected."

            repaired = False
            for attempt in range(max_repair_attempts_per_rule):
                try:
                    # Load repair prompt
                    from src.utils.prompt_loader import format_prompt_async

                    repair_prompt = await format_prompt_async(
                        "sigma_repair_single",
                        validation_errors=previous_errors_text,
                        original_rule=previous_yaml_preview,
                    )

                    # Call LLM API for repair
                    sigma_provider = self.llm_service.provider_sigma
                    repaired_yaml = await self._call_provider_for_sigma(
                        repair_prompt,
                        provider=sigma_provider,
                        execution_id=execution_id,
                        article_id=article_id,
                        system_prompt=sigma_system_prompt,
                    )

                    if repaired_yaml is None:
                        repaired_yaml = ""
                    else:
                        repaired_yaml = str(repaired_yaml)

                    # Clean and validate repaired rule
                    cleaned_repaired = clean_sigma_rule(repaired_yaml)
                    validation_result = validate_sigma_rule(cleaned_repaired)

                    # Log repair attempt
                    repair_attempt = {
                        "attempt": attempt + 1,
                        "llm_response": repaired_yaml,
                        "validation": {
                            "is_valid": validation_result.is_valid,
                            "errors": validation_result.errors,
                            "warnings": validation_result.warnings,
                        },
                    }
                    rule_result.repair_attempts.append(repair_attempt)

                    if validation_result.is_valid:
                        # Repair successful
                        rule_result.rule_yaml = cleaned_repaired
                        rule_result.validation_result = validation_result
                        rule_result.final_status = "repaired"
                        repaired_rules.append(rule_result)
                        repaired = True
                        logger.info(f"Rule {rule_result.rule_id} repaired successfully after {attempt + 1} attempts")
                        break
                    # Prepare for next attempt
                    previous_errors_text = (
                        "\n".join(validation_result.errors) if validation_result.errors else previous_errors_text
                    )
                    previous_yaml_preview = cleaned_repaired[:500]

                except Exception as e:
                    logger.error(f"Repair attempt {attempt + 1} failed for rule {rule_result.rule_id}: {e}")
                    repair_attempt = {"attempt": attempt + 1, "llm_response": None, "validation": None, "error": str(e)}
                    rule_result.repair_attempts.append(repair_attempt)

            if not repaired:
                rule_result.final_status = "failed"
                logger.warning(
                    f"Rule {rule_result.rule_id} failed to repair after {max_repair_attempts_per_rule} attempts"
                )

        logger.info(f"Phase 3: Repaired {len(repaired_rules)}/{len(invalid_rules)} rules")
        return repaired_rules

    def _needs_expansion(
        self, valid_rules: list[RuleValidationResult], extraction_result: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Phase 4: Check if expansion needed (artifact-driven)."""
        # Map observable types to logsource categories
        observable_to_category = {
            "cmdline": "process_creation",
            "process_lineage": "process_creation",
            "network_connection": "network_connection",
            "registry_keys": "registry_event",
            "file_event": "file_event",
            "powershell": "powershell",
            "wmi": "wmi",
        }

        # Get available observables from extraction_result
        available_observables = {}
        subresults = extraction_result.get("subresults", {})
        if isinstance(subresults, dict):
            for obs_type, obs_result in subresults.items():
                if isinstance(obs_result, dict):
                    count = obs_result.get("count", 0)
                    items = obs_result.get("items", [])
                    if count > 0 or (isinstance(items, list) and len(items) > 0):
                        available_observables[obs_type] = {"count": count if count > 0 else len(items), "items": items}

        # Get covered categories from valid rules
        covered_categories = set()
        for rule_result in valid_rules:
            try:
                parsed_yaml = yaml.safe_load(rule_result.rule_yaml)
                if parsed_yaml:
                    logsource = parsed_yaml.get("logsource", {})
                    if isinstance(logsource, dict):
                        category = logsource.get("category")
                        if category:
                            covered_categories.add(category)
            except Exception as e:
                logger.debug(f"Failed to parse rule for category extraction: {e}")

        # Check which observable types map to uncovered categories
        uncovered_categories = []
        for obs_type, category in observable_to_category.items():
            if obs_type in available_observables and category not in covered_categories:
                uncovered_categories.append(category)
                logger.info(
                    f"Found uncovered category {category} from observable type {obs_type} (count: {available_observables[obs_type]['count']})"
                )

        needs_expansion = len(uncovered_categories) > 0
        return needs_expansion, uncovered_categories

    async def _build_expansion_prompt(
        self,
        sigma_prompt_template: str | None,
        article_title: str,
        source_name: str,
        url: str,
        content_to_analyze: str,
        uncovered_categories: list[str],
        extraction_result: dict[str, Any],
    ) -> str:
        """Build prompt for expansion phase focusing on uncovered categories."""
        # Build context about uncovered categories and their observables
        category_context = []
        observable_to_category = {
            "cmdline": "process_creation",
            "process_lineage": "process_creation",
            "network_connection": "network_connection",
            "registry_keys": "registry_event",
            "file_event": "file_event",
            "powershell": "powershell",
            "wmi": "wmi",
        }

        subresults = extraction_result.get("subresults", {})
        for obs_type, category in observable_to_category.items():
            if category in uncovered_categories and obs_type in subresults:
                obs_result = subresults[obs_type]
                items = obs_result.get("items", [])
                if items:
                    category_context.append(f"\n{category.upper()} observables ({obs_type}):")
                    for item in items[:5]:  # Limit to first 5 items
                        if isinstance(item, str) or isinstance(item, dict):
                            category_context.append(f"  - {item}")

        context_text = "\n".join(category_context) if category_context else ""

        # Use multi-rule generation prompt template
        from src.utils.prompt_loader import format_prompt_async

        base_prompt = await format_prompt_async(
            "sigma_generate_multi",
            title=article_title,
            source=source_name,
            url=url or "N/A",
            content=content_to_analyze,
        )

        # Add expansion context
        expansion_prompt = f"""Generate additional SIGMA rules for the following uncovered logsource categories: {", ".join(uncovered_categories)}

These categories have observables available but no rules generated yet:
{context_text}

{base_prompt}

Focus on generating rules for the uncovered categories listed above."""

        return expansion_prompt

    async def _call_provider_for_sigma(
        self,
        prompt: str,
        *,
        provider: str,
        execution_id: int | None = None,
        article_id: int | None = None,
        system_prompt: str | None = None,
    ) -> str:
        raw_model_name = self.llm_service.model_sigma or self.llm_service.provider_defaults.get(
            provider, self.llm_service.lmstudio_model
        )

        # Don't normalize here - let request_chat handle normalization and retry logic
        # This allows the retry logic to try with the full model name (with prefix) if needed
        model_name = raw_model_name

        # Use provided system prompt or fall back to default
        default_system_prompt = "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries. No markdown, no explanations. IMPORTANT: If title or description contains special YAML characters (?, :, [, ], {, }, |, &, *, #, @, `), quote the value with double quotes, e.g., title: \"Rule Title with ?\"."
        system_content = system_prompt if system_prompt else default_system_prompt

        messages = [{"role": "system", "content": system_content}, {"role": "user", "content": prompt}]

        converted_messages = self.llm_service._convert_messages_for_model(messages, model_name)

        is_reasoning_model = "r1" in model_name.lower() or "reasoning" in model_name.lower()
        max_tokens = 2000 if is_reasoning_model else 800

        with trace_llm_call(
            name="generate_sigma",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata={"prompt_length": len(prompt), "max_tokens": max_tokens, "provider": provider},
        ) as generation:
            try:
                result = await self.llm_service.request_chat(
                    provider=provider,
                    model_name=model_name,
                    messages=converted_messages,
                    max_tokens=max_tokens,
                    temperature=self.llm_service.temperature_sigma,
                    timeout=300.0,
                    failure_context=f"Failed to generate SIGMA rules via {provider}",
                    top_p=self.llm_service.top_p_sigma,
                    seed=self.llm_service.seed,
                )

                message = result["choices"][0]["message"]
                content_text = message.get("content", "")
                reasoning_text = message.get("reasoning_content", "")

                if content_text and (content_text.strip().startswith("title:") or "title:" in content_text[:100]):
                    output = content_text
                    logger.debug("Using 'content' field for SIGMA generation (contains YAML)")
                elif reasoning_text:
                    import re

                    yaml_match = re.search(r"(?:^|\n)title:\s*[^\n]+\n(?:[^\n]+\n)*", reasoning_text, re.MULTILINE)
                    if yaml_match:
                        yaml_start = yaml_match.start()
                        yaml_block = reasoning_text[yaml_start:]
                        output = yaml_block
                        logger.debug("Extracted YAML from 'reasoning_content' field")
                    else:
                        output = reasoning_text
                        logger.debug("Using 'reasoning_content' field for SIGMA generation (no YAML pattern found)")
                else:
                    output = content_text or reasoning_text or ""

                finish_reason = result["choices"][0].get("finish_reason", "")
                if finish_reason == "length":
                    logger.warning(
                        f"SIGMA generation response was truncated (finish_reason=length). Used {result.get('usage', {}).get('completion_tokens', 0)} tokens. max_tokens={max_tokens} may need to be increased."
                    )

                if not output or len(output.strip()) == 0:
                    logger.error("LLM returned empty response for SIGMA generation")
                    raise ValueError(
                        "LLM returned empty response for SIGMA generation. Check the configured provider is responding correctly."
                    )

                usage = result.get("usage", {})

                log_llm_completion(
                    generation,
                    input_messages=messages,
                    output=output,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    metadata={"output_length": len(output), "finish_reason": finish_reason, "provider": provider},
                )

                return output
            except Exception as e:
                log_llm_error(generation, e)
                raise
