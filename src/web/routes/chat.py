"""
RAG chat API endpoint.
"""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from src.web.dependencies import logger

router = APIRouter(tags=["Chat"])


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
        similarity_threshold = body.get("similarity_threshold", 0.3)
        use_chunks = body.get("use_chunks", False)
        context_length = body.get("context_length", 2000)

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
                    sentences = content.split(".")
                    relevant_sentences = [
                        sentence.strip()
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
        
        # Get the actual model name that would be used
        llm_provider = "template"
        llm_model_name = "template"
        if use_llm_generation:
            try:
                from src.services.llm_generation_service import get_llm_generation_service
                llm_service = get_llm_generation_service()
                # Just get the model name without calling it
                selected_provider = llm_service._select_provider(requested_provider)
                llm_provider = selected_provider
                llm_model_name = llm_service._get_model_name(selected_provider)
            except Exception as e:
                logger.warning(f"Could not determine LLM model: {e}")

        search_limit = max_results if max_results <= 100 else 50
        relevant_articles = await rag_service.find_similar_content(
            query=enhanced_query,
            top_k=search_limit,
            threshold=similarity_threshold,
            use_chunks=use_chunks,
            context_length=context_length,
        )

        if relevant_articles:
            # Use LLM generation service for synthesized responses
            use_llm_generation = body.get("use_llm_generation", True)
            
            if use_llm_generation:
                try:
                    from src.services.llm_generation_service import get_llm_generation_service
                    
                    llm_service = get_llm_generation_service()
                    generation_result = await llm_service.generate_rag_response(
                        query=message,
                        retrieved_chunks=relevant_articles,
                        conversation_history=conversation_history,
                        provider=body.get("llm_provider", "auto")
                    )
                    
                    response = generation_result["response"]
                    llm_provider = generation_result["provider"]
                    llm_model_name = generation_result.get("model_name", llm_provider)
                    logger.info(f"Generated LLM response using {llm_provider} ({llm_model_name})")
                    
                except Exception as e:
                    logger.warning(f"LLM generation failed, falling back to template: {e}")
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
                    metadata = article.get("metadata", {})

                    for technique in article.get("keywords", []):
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

                analysis_text = (
                    "**Key Detection Techniques Identified:**\n"
                    + "\n".join(f"- {tech}" for tech in unique_techniques[:5])
                    + "\n\n**Threat Categories Covered:**\n"
                    + "\n".join(f"- {threat}" for threat in unique_threats[:3])
                    + "\n\n**Research Sources:**\n"
                    + "\n".join(f"- {source}" for source in unique_sources[:3])
                    + "\n\n**Key Insights:**\n"
                    + (
                        "\n".join(f"- {insight}" for insight in insights[:3])
                        if insights
                        else "- Multiple authoritative sources provide comprehensive coverage of malware detection techniques"
                    )
                )

                response = (
                    "Based on our comprehensive threat intelligence analysis, here's my assessment of your query:\n\n"
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
                    f"to {max(article['similarity'] for article in relevant_articles):.1%}, indicating strong relevance\n"
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
                await session.commit()
                logger.info("Logged chat interaction: %s", chat_log.id)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to log chat interaction: %s", exc)

        return {
            "response": response,
            "conversation_history": conversation_history,
            "relevant_articles": relevant_articles,
            "total_results": len(relevant_articles),
            "query": message,
            "timestamp": datetime.now().isoformat(),
            "llm_provider": llm_provider if 'llm_provider' in locals() else "template",
            "llm_model_name": llm_model_name if 'llm_model_name' in locals() else "template",
            "use_llm_generation": use_llm_generation if 'use_llm_generation' in locals() else False,
        }

    except HTTPException:
        # Re-raise HTTP exceptions (like validation errors) as-is
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("RAG chat error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

