"""
RAG chat API endpoint.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.database.manager import DatabaseManager
from src.database.models import RagPresetTable
from src.utils.sentence_splitter import split_sentences
from src.web.dependencies import logger

router = APIRouter(tags=["Chat"])


class SaveRagPresetRequest(BaseModel):
    """Request model for saving a RAG preset."""

    name: str
    description: Optional[str] = None
    provider: str
    model: str
    max_results: int = 5
    similarity_threshold: float = 0.38

# Known threat/malware/family terms for lexical relevance filtering
_LEXICAL_TERMS = frozenset({
    "emotet", "cobalt strike", "cobaltstrike", "lockbit", "conti", "revil",
    "wannacry", "ryuk", "trickbot", "qbot", "qakbot", "bazar", "icedid",
    "hive", "blackcat", "alphv", "clop", "ransomware", "apt28", "apt29",
    "lazarus", "sandworm", "fin7", "carbanak", "maze", "sodinokibi",
})


def _extract_lexical_terms(query: str) -> list[str]:
    """Extract known threat/malware terms from query for relevance filtering."""
    q = query.lower().strip()
    found = []
    for term in _LEXICAL_TERMS:
        if term in q:
            found.append(term)
    # Also extract CamelCase/Title-case malware names (e.g. Emotet, LockBit)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b", query):
        w = m.group(1).lower()
        if w in _LEXICAL_TERMS:
            found.append(w)
    return list(dict.fromkeys(found))


def _filter_by_lexical_relevance(
    articles: list, terms: list[str], max_results: int = 5
) -> list:
    """Prioritize articles matching query terms. When terms exist and we have
    lexical matches, exclude non-lexical articles to avoid tangentially related
    results (e.g. 'New OpenAI leak' for 'Emotet delivery techniques')."""
    if not terms:
        return articles[:max_results]
    lexical = [
        a for a in articles
        if any(
            t in (a.get("title") or "").lower() or t in (a.get("content") or "").lower()
            for t in terms
        )
    ]
    if lexical:
        # Only return lexical matches; exclude tangentially related non-matches
        return lexical[:max_results]
    # No lexical matches: fall back to embedding order
    return articles[:max_results]


@router.post("/api/chat/preset/save")
async def save_rag_preset(save_request: SaveRagPresetRequest):
    """Save a new RAG preset."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            existing = db_session.query(RagPresetTable).filter(
                RagPresetTable.name == save_request.name
            ).first()
            if existing:
                existing.description = save_request.description
                existing.provider = save_request.provider
                existing.model = save_request.model
                existing.max_results = save_request.max_results
                existing.similarity_threshold = save_request.similarity_threshold
                existing.updated_at = datetime.now()
                db_session.commit()
                db_session.refresh(existing)
                return {
                    "success": True,
                    "id": existing.id,
                    "message": "Preset updated",
                    "created_at": existing.created_at.isoformat(),
                    "updated_at": existing.updated_at.isoformat(),
                }
            preset = RagPresetTable(
                name=save_request.name,
                description=save_request.description,
                provider=save_request.provider,
                model=save_request.model,
                max_results=save_request.max_results,
                similarity_threshold=save_request.similarity_threshold,
            )
            db_session.add(preset)
            db_session.commit()
            db_session.refresh(preset)
            return {
                "success": True,
                "id": preset.id,
                "message": "Preset saved",
                "created_at": preset.created_at.isoformat(),
                "updated_at": preset.updated_at.isoformat(),
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error("Error saving RAG preset: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error saving preset: {str(e)}")


@router.get("/api/chat/preset/list")
async def list_rag_presets():
    """Get list of all saved RAG presets."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            presets = db_session.query(RagPresetTable).order_by(
                RagPresetTable.name.asc()
            ).all()
            preset_list = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "provider": p.provider,
                    "model": p.model,
                    "max_results": p.max_results,
                    "similarity_threshold": p.similarity_threshold,
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in presets
            ]
            return {"success": True, "presets": preset_list}
        finally:
            db_session.close()
    except Exception as e:
        logger.error("Error listing RAG presets: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing presets: {str(e)}")


@router.get("/api/chat/preset/{preset_id}")
async def get_rag_preset(preset_id: int):
    """Get a specific RAG preset by ID."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            preset = db_session.query(RagPresetTable).filter(
                RagPresetTable.id == preset_id
            ).first()
            if not preset:
                raise HTTPException(status_code=404, detail="Preset not found")
            return {
                "success": True,
                "id": preset.id,
                "name": preset.name,
                "description": preset.description,
                "provider": preset.provider,
                "model": preset.model,
                "max_results": preset.max_results,
                "similarity_threshold": preset.similarity_threshold,
                "created_at": preset.created_at.isoformat(),
                "updated_at": preset.updated_at.isoformat(),
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting RAG preset: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting preset: {str(e)}")


@router.delete("/api/chat/preset/{preset_id}")
async def delete_rag_preset(preset_id: int):
    """Delete a RAG preset."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            preset = db_session.query(RagPresetTable).filter(
                RagPresetTable.id == preset_id
            ).first()
            if not preset:
                raise HTTPException(status_code=404, detail="Preset not found")
            db_session.delete(preset)
            db_session.commit()
            return {"success": True, "message": "Preset deleted"}
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting RAG preset: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting preset: {str(e)}")


@router.post("/api/chat/rag")
async def api_rag_chat(request: Request):
    """
    Chat with the database using RAG (Retrieval-Augmented Generation).
    """
    try:
        from src.services.rag_service import get_rag_service

        start_time = datetime.now()
        body = await request.json()
        message = body.get("message", "")
        conversation_history = body.get("conversation_history", [])
        max_results = body.get("max_results", 5)
        similarity_threshold = body.get("similarity_threshold", 0.38)
        use_chunks = body.get("use_chunks", False)
        context_length = body.get("context_length", 2000)
        include_sigma_rules = body.get("include_sigma_rules", True)  # New parameter

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        rag_service = get_rag_service()

        context_summary = ""
        if conversation_history:
            recent_turns = conversation_history[-6:]
            context_parts: list[str] = []
            for msg in recent_turns:
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "user":
                    context_parts.append(f"User asked: {content}")
                elif role == "assistant":
                    threat_terms = [
                        "cobalt strike",
                        "ransomware",
                        "malware",
                        "apt",
                        "threat actor",
                        "vulnerability",
                        "exploit",
                        "phishing",
                        "ioc",
                        "pentest",
                        "red team",
                        "beacon",
                        "payload",
                        "backdoor",
                        "attack",
                        "breach",
                        "compromise",
                    ]
                    sentences = split_sentences(content)
                    relevant_sentences = [
                        sentence
                        for sentence in sentences
                        if any(term in sentence.lower() for term in threat_terms)
                    ]
                    if relevant_sentences:
                        context_parts.append(f"Previous context: {' '.join(relevant_sentences[:2])}")

            if context_parts:
                context_summary = " | ".join(context_parts[-3:])
                if len(context_summary) > 300:
                    context_summary = context_summary[:300] + "..."

        enhanced_query = f"{message} {context_summary}" if context_summary else message

        # Determine which LLM would be used
        use_llm_generation = body.get("use_llm_generation", True)
        requested_provider = body.get("llm_provider", "auto")
        llm_error: str | None = None
        
        # Get the actual model name that would be used
        llm_provider = "template"
        llm_model_name = "Template"
        llm_service = None
        canonical_requested = None
        if use_llm_generation:
            try:
                from src.services.llm_generation_service import get_llm_generation_service
                llm_service = get_llm_generation_service()
                canonical_requested = llm_service._canonicalize_requested_provider(requested_provider)
                selected_provider = llm_service._select_provider(requested_provider)
                llm_provider = selected_provider
                resolved_model = llm_service._get_model_name(selected_provider)
                llm_model_name = llm_service._build_model_display(
                    selected_provider, resolved_model, canonical_requested
                )
            except Exception as e:
                logger.warning(f"Could not determine LLM model: {e}")

        search_limit = max_results if max_results <= 100 else 50
        lexical_terms = _extract_lexical_terms(message)
        if lexical_terms:
            # Fetch more candidates so lexical filter has a larger pool to select from
            search_limit = max(search_limit, 50)
        
        # Extract hunt score filter from query if present
        min_hunt_score = None
        if "hunt score" in enhanced_query.lower() or "hunt_score" in enhanced_query.lower():
            # Look for patterns like "hunt score above 80", "hunt score > 70", etc.
            import re
            score_patterns = [
                r'hunt\s+scores?\s+(?:above|>|>=)\s*(\d+)',
                r'hunt\s+scores?\s+(\d+)\s*(?:and\s+above|or\s+higher)',
                r'hunt\s+scores?\s+over\s*(\d+)',
                r'hunt\s+scores?\s+(\d+)\+',
                r'hunt\s+scores?\s+(\d+)',  # Simple "hunt score 80"
                r'scores?\s+(?:above|>|>=)\s*(\d+)',  # "score above 80"
                r'scores?\s+(\d+)\+'  # "score 80+"
            ]
            for pattern in score_patterns:
                match = re.search(pattern, enhanced_query.lower())
                if match:
                    min_hunt_score = float(match.group(1))
                    logger.info(f"Extracted hunt score filter: {min_hunt_score}")
                    break
        
        # Use unified search if Sigma rules are enabled
        if include_sigma_rules:
            unified_results = await rag_service.find_unified_results(
                query=enhanced_query,
                top_k_articles=search_limit,
                top_k_rules=min(5, max_results),  # Limit to 5 rules max
                threshold=similarity_threshold,
                use_chunks=use_chunks,
                context_length=context_length,
                min_hunt_score=min_hunt_score,
            )
            relevant_articles = unified_results.get('articles', [])
            relevant_rules = unified_results.get('rules', [])
            logger.info(f"RAG search returned {len(relevant_articles)} articles and {len(relevant_rules)} SIGMA rules")
        else:
            relevant_articles = await rag_service.find_similar_content(
                query=enhanced_query,
                top_k=search_limit,
                threshold=similarity_threshold,
                use_chunks=use_chunks,
                context_length=context_length,
                min_hunt_score=min_hunt_score,
            )
            relevant_rules = []

        # Lexical relevance: prioritize articles mentioning query terms
        if lexical_terms:
            before = len(relevant_articles)
            relevant_articles = _filter_by_lexical_relevance(
                relevant_articles, lexical_terms, max_results=max_results
            )
            # If few lexical matches from embedding pool, supplement with direct lexical search
            if len(relevant_articles) < max_results:
                from src.database.async_manager import async_db_manager
                lexical_articles = await async_db_manager.search_articles_by_lexical_terms(
                    terms=lexical_terms, limit=max_results * 3
                )
                seen_ids = {a.get("id") or a.get("article_id") for a in relevant_articles}
                for la in lexical_articles:
                    aid = la.get("id")
                    if aid and aid not in seen_ids:
                        seen_ids.add(aid)
                        relevant_articles.append(la)
                        if len(relevant_articles) >= max_results:
                            break
            if before != len(relevant_articles):
                logger.info(f"Lexical filter ({lexical_terms}): {before} -> {len(relevant_articles)} articles")

        # Always cap at Max Results setting
        relevant_articles = relevant_articles[:max_results]

        if relevant_articles:
            # Use LLM generation service for synthesized responses
            use_llm_generation = body.get("use_llm_generation", True)
            
            if use_llm_generation:
                try:
                    if llm_service is None:
                        from src.services.llm_generation_service import get_llm_generation_service

                        llm_service = get_llm_generation_service()
                        canonical_requested = llm_service._canonicalize_requested_provider(requested_provider)
                    logger.info(f"Passing {len(relevant_rules)} SIGMA rules to LLM generation")
                    generation_result = await llm_service.generate_rag_response(
                        query=message,
                        retrieved_chunks=relevant_articles,
                        conversation_history=conversation_history,
                        provider=body.get("llm_provider", "auto"),
                        retrieved_rules=relevant_rules,
                        model_override=body.get("llm_model"),
                    )
                    
                    response = generation_result["response"]
                    llm_provider = generation_result["provider"]
                    llm_model_name = (
                        generation_result.get("model_display_name")
                        or generation_result.get("model_name")
                        or llm_provider
                    )
                    logger.info(f"Generated LLM response using {llm_provider} ({llm_model_name})")
                    
                except Exception as e:
                    llm_error = str(e)
                    logger.warning(f"LLM generation failed, falling back to template: {llm_error}")
                    use_llm_generation = False
            
            if not use_llm_generation:
                # Fallback to template-based response
                context_parts = []
                for article in relevant_articles:
                    context_parts.append(f"{article['title']} from {article['source_name']}: {article['content']}")
                    context_parts.append(f"Source: {article['canonical_url']}")

                context = "\n\n".join(context_parts)

                unique_techniques = []
                unique_threats = []
                unique_sources = []
                insights = []

                for article in relevant_articles:
                    metadata = article.get("metadata", {}) or {}

                    for technique in article.get("keywords", []) or metadata.get("keywords", []):
                        if technique not in unique_techniques:
                            unique_techniques.append(technique)

                    category = metadata.get("threat_category")
                    if category and category not in unique_threats:
                        unique_threats.append(category)

                    source_name = article.get("source_name")
                    if source_name and source_name not in unique_sources:
                        unique_sources.append(source_name)

                    summary = metadata.get("ai_summary")
                    if summary and summary not in insights:
                        insights.append(summary)

                ai_articles = [
                    article
                    for article in relevant_articles
                    if "prompt injection" in article.get("content", "").lower()
                    or "promptlock" in article.get("title", "").lower()
                    or "funklocker" in article.get("title", "").lower()
                ]
                if len(ai_articles) >= 3:
                    insights.append(
                        "AI threat landscape is maturing - from proof-of-concept PromptLock to operational FunkLocker, "
                        "showing progression from research to real-world deployment"
                    )

                techniques_str = "\n".join(f"- {tech}" for tech in unique_techniques[:5]) if unique_techniques else "- (not extracted from retrieved articles)"
                threats_str = "\n".join(f"- {threat}" for threat in unique_threats[:3]) if unique_threats else "- (not extracted from retrieved articles)"
                insights_str = (
                    "\n".join(f"- {insight}" for insight in insights[:3])
                    if insights
                    else "- (no structured insights extracted; consider enabling LLM synthesis for richer analysis)"
                )
                analysis_text = (
                    "**Key Detection Techniques Identified:**\n"
                    + techniques_str
                    + "\n\n**Threat Categories Covered:**\n"
                    + threats_str
                    + "\n\n**Research Sources:**\n"
                    + "\n".join(f"- {source}" for source in unique_sources[:3])
                    + "\n\n**Key Insights:**\n"
                    + insights_str
                )

                llm_provider = "template"
                if llm_service is None:
                    try:
                        from src.services.llm_generation_service import get_llm_generation_service

                        llm_service = get_llm_generation_service()
                    except Exception:
                        llm_service = None

                if llm_service is not None and canonical_requested is None:
                    try:
                        canonical_requested = llm_service._canonicalize_requested_provider(requested_provider)
                    except Exception:
                        canonical_requested = None

                if llm_service is not None:
                    try:
                        llm_model_name = llm_service._build_model_display(
                            "template",
                            "template",
                            canonical_requested,
                        )
                    except Exception:
                        llm_model_name = "Template"
                else:
                    llm_model_name = "Template"

                max_sim = max(a.get("similarity", 0) for a in relevant_articles) if relevant_articles else 0
                low_conf_note = (
                    "_Note: Similarity scores are moderate. Some results may be tangentially related._\n\n"
                    if max_sim < 0.45
                    else ""
                )
                response = (
                    low_conf_note
                    + "Based on our comprehensive threat intelligence analysis, here's my assessment of your query:\n\n"
                    "**Executive Summary**:\n"
                    f"{analysis_text}\n\n"
                    "**Synthesized Insights**:\n"
                    + "\n".join(f"- {insight}" for insight in insights)
                    + "\n\n**Threat Intelligence Assessment**:\n"
                    f"I've identified {len(relevant_articles)} highly relevant articles from our threat intelligence "
                    "database that directly address your query. These sources provide authoritative coverage from leading "
                    "cybersecurity organizations and researchers.\n\n"
                    "**Key Implications**:\n"
                    f"- Multiple authoritative sources confirm the threat landscape\n"
                    f"- Similarity scores range from {min(article['similarity'] for article in relevant_articles):.1%} "
                    f"to {max(article['similarity'] for article in relevant_articles):.1%}"
                    + (" (moderate relevance)" if max_sim < 0.45 else ", indicating strong relevance")
                    + "\n"
                    "- Cross-source validation strengthens the reliability of findings\n\n"
                    "**Recommendations**:\n"
                    "- Review the linked sources for detailed technical information\n"
                    "- Consider the temporal aspects of the threat intelligence\n"
                    "- Integrate findings into your security posture and threat hunting activities\n\n"
                    "Would you like me to provide deeper analysis on any specific aspect or explore related threat vectors?"
            )
        else:
            response = (
                "I couldn't find any relevant articles in our threat intelligence database that match your query.\n\n"
                "This could be because:\n"
                "- The query doesn't match the content we have\n"
                "- The similarity threshold is too high\n"
                "- We don't have articles covering this specific topic\n\n"
                "Try rephrasing your question or asking about broader cybersecurity topics like malware, ransomware, "
                "threat actors, or security vulnerabilities."
            )

        conversation_history.append(
            {
                "role": "user",
                "content": message,
                "timestamp": datetime.now().isoformat(),
                "context_summary": context_summary,
            }
        )
        conversation_history.append(
            {
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
                "relevant_articles_count": len(relevant_articles),
                "enhanced_query": enhanced_query,
            }
        )

        try:
            from src.database.models import ChatLogTable
            import uuid

            urls = [
                article.get("canonical_url", "")
                for article in relevant_articles
                if article.get("canonical_url")
            ]
            similarity_scores = [article.get("similarity", 0.0) for article in relevant_articles]

            chat_log = ChatLogTable(
                session_id=str(uuid.uuid4())[:8],
                query=message,
                retrieved_chunks=[
                    {
                        "id": article.get("id"),
                        "article_id": article.get("article_id"),
                        "title": article.get("title"),
                        "similarity": article.get("similarity"),
                    }
                    for article in relevant_articles
                ],
                llm_response=response,
                model_used=llm_provider,
                urls=urls,
                similarity_scores=similarity_scores,
                response_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

            async with rag_service.db_manager.get_session() as session:
                session.add(chat_log)
                await session.flush()
                log_id = chat_log.id
                await session.commit()
                logger.info("Logged chat interaction: %s", log_id)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to log chat interaction: %s", exc)

        return {
            "response": response,
            "conversation_history": conversation_history,
            "relevant_articles": relevant_articles,
            "relevant_rules": relevant_rules if include_sigma_rules else [],
            "total_results": len(relevant_articles),
            "total_rules": len(relevant_rules) if include_sigma_rules else 0,
            "query": message,
            "timestamp": datetime.now().isoformat(),
            "llm_provider": llm_provider if 'llm_provider' in locals() else "template",
            "llm_model_name": llm_model_name if 'llm_model_name' in locals() else "template",
            "use_llm_generation": use_llm_generation if 'use_llm_generation' in locals() else False,
            "include_sigma_rules": include_sigma_rules,
            "llm_error": llm_error,
        }

    except HTTPException:
        # Re-raise HTTP exceptions (like validation errors) as-is
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("RAG chat error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
