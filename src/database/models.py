"""SQLAlchemy database models with enhanced deduplication support."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey, JSON, Numeric, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class SourceTable(Base):
    """Database table for sources."""
    
    __tablename__ = 'sources'
    
    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    url = Column(Text, nullable=False)
    rss_url = Column(Text, nullable=True)
    check_frequency = Column(Integer, nullable=False, default=3600)
    lookback_days = Column(Integer, nullable=False, default=180)
    active = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=False, default=dict)
    
    # Tracking fields
    last_check = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    total_articles = Column(Integer, nullable=False, default=0)
    
    # Health metrics
    average_response_time = Column(Float, nullable=False, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    articles = relationship("ArticleTable", back_populates="source", cascade="all, delete-orphan")
    checks = relationship("SourceCheckTable", back_populates="source", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Source(id={self.id}, identifier='{self.identifier}', name='{self.name}')>"


class ArticleTable(Base):
    """Database table for articles with enhanced deduplication."""
    
    __tablename__ = 'articles'
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
    canonical_url = Column(Text, nullable=False, index=True)
    title = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=False, index=True)
    modified_at = Column(DateTime, nullable=True)
    authors = Column(JSON, nullable=False, default=list)  # List of strings
    tags = Column(JSON, nullable=False, default=list)    # List of strings
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    article_metadata = Column(JSON, nullable=False, default=dict)
    
    # Enhanced deduplication fields
    simhash = Column(Numeric(20, 0), nullable=True, index=True)  # 64-bit SimHash for near-duplicate detection
    simhash_bucket = Column(Integer, nullable=True, index=True)  # Bucket for efficient SimHash lookup
    
    # Processing fields
    discovered_at = Column(DateTime, nullable=False, default=func.now())
    processing_status = Column(String(50), nullable=False, default='pending', index=True)
    
    # Quality metrics
    word_count = Column(Integer, nullable=False, default=0)
    
    # Vector embedding fields
    embedding = Column(Vector(768), nullable=True, index=True)  # 768-dimensional embedding vector
    embedding_model = Column(String(100), nullable=True, default='all-mpnet-base-v2')
    embedded_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    archived = Column(Boolean, nullable=False, default=False, index=True)
    
    # Relationships
    source = relationship("SourceTable", back_populates="articles")
    chunk_analysis_results = relationship("ChunkAnalysisResultTable", back_populates="article", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50]}...', source_id={self.source_id})>"


class SourceCheckTable(Base):
    """Database table for tracking source check history."""
    
    __tablename__ = 'source_checks'
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
    check_time = Column(DateTime, nullable=False, default=func.now(), index=True)
    success = Column(Boolean, nullable=False)
    method = Column(String(50), nullable=False)  # 'rss', 'basic_scraping', 'simple_scraping'
    articles_found = Column(Integer, nullable=False, default=0)
    response_time = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    check_metadata = Column(JSON, nullable=False, default=dict)
    
    # Relationships
    source = relationship("SourceTable", back_populates="checks")
    
    def __repr__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"<SourceCheck(source_id={self.source_id}, {status}, {self.articles_found} articles)>"


class ArticleAnnotationTable(Base):
    """Database table for article text annotations with vector embeddings."""
    
    __tablename__ = 'article_annotations'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)  # For future user management
    annotation_type = Column(String(20), nullable=False, index=True)  # 'huntable' or 'not_huntable'
    selected_text = Column(Text, nullable=False)
    start_position = Column(Integer, nullable=False)
    end_position = Column(Integer, nullable=False)
    context_before = Column(Text, nullable=True)
    context_after = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=False, default=0.0)
    
    # Vector embedding fields
    embedding = Column(Vector(768), nullable=True, index=True)  # 768-dimensional embedding vector
    embedding_model = Column(String(100), nullable=True, default='all-mpnet-base-v2')
    embedded_at = Column(DateTime, nullable=True)
    
    # Training tracking
    used_for_training = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    article = relationship("ArticleTable", backref="annotations")
    
    def __repr__(self):
        return f"<ArticleAnnotation(id={self.id}, type='{self.annotation_type}', text='{self.selected_text[:50]}...')>"


class ContentHashTable(Base):
    """Database table for content hash tracking (for efficient deduplication)."""
    
    __tablename__ = 'content_hashes'
    
    id = Column(Integer, primary_key=True, index=True)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    first_seen = Column(DateTime, nullable=False, default=func.now())
    
    def __repr__(self):
        return f"<ContentHash(hash='{self.content_hash[:8]}...', article_id={self.article_id})>"


class SimHashBucketTable(Base):
    """Database table for SimHash bucket tracking (for near-duplicate detection)."""
    
    __tablename__ = 'simhash_buckets'
    
    id = Column(Integer, primary_key=True, index=True)
    bucket_id = Column(Integer, nullable=False, index=True)  # SimHash bucket number
    simhash = Column(Numeric(20, 0), nullable=False, index=True)  # 64-bit SimHash value
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    first_seen = Column(DateTime, nullable=False, default=func.now())
    
    def __repr__(self):
        return f"<SimHashBucket(bucket={self.bucket_id}, simhash={self.simhash}, article_id={self.article_id})>"


class URLTrackingTable(Base):
    """Database table for tracking processed URLs (for conditional requests)."""
    
    __tablename__ = 'url_tracking'
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(Text, nullable=False, unique=True, index=True)
    last_checked = Column(DateTime, nullable=False, default=func.now())
    etag = Column(String(255), nullable=True)
    last_modified = Column(String(255), nullable=True)
    status_code = Column(Integer, nullable=True)
    content_length = Column(Integer, nullable=True)
    
    def __repr__(self):
        return f"<URLTracking(url='{self.url[:50]}...', last_checked={self.last_checked})>"


class MLModelVersionTable(Base):
    """Database table for tracking ML model versions and performance metrics."""
    
    __tablename__ = 'ml_model_versions'
    
    id = Column(Integer, primary_key=True, index=True)
    version_number = Column(Integer, nullable=False)
    trained_at = Column(DateTime, nullable=False, default=func.now())
    training_data_size = Column(Integer, nullable=False)
    feedback_samples_count = Column(Integer, nullable=False, default=0)
    
    # Test set performance metrics
    accuracy = Column(Float, nullable=True)
    precision_huntable = Column(Float, nullable=True)
    precision_not_huntable = Column(Float, nullable=True)
    recall_huntable = Column(Float, nullable=True)
    recall_not_huntable = Column(Float, nullable=True)
    f1_score_huntable = Column(Float, nullable=True)
    f1_score_not_huntable = Column(Float, nullable=True)
    
    # Model configuration
    model_params = Column(JSON, nullable=False, default=dict)
    
    # Training metadata
    training_duration_seconds = Column(Float, nullable=True)
    model_file_path = Column(Text, nullable=True)
    
    # Comparison metadata
    compared_with_version = Column(Integer, ForeignKey('ml_model_versions.id'), nullable=True)
    comparison_results = Column(JSON, nullable=True)
    
    # Evaluation metrics (on 160 annotated chunks)
    eval_accuracy = Column(Float, nullable=True)
    eval_precision_huntable = Column(Float, nullable=True)
    eval_precision_not_huntable = Column(Float, nullable=True)
    eval_recall_huntable = Column(Float, nullable=True)
    eval_recall_not_huntable = Column(Float, nullable=True)
    eval_f1_score_huntable = Column(Float, nullable=True)
    eval_f1_score_not_huntable = Column(Float, nullable=True)
    eval_confusion_matrix = Column(JSON, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    def __repr__(self):
        return f"<MLModelVersion(id={self.id}, version={self.version_number}, accuracy={self.accuracy:.3f})>"


class ChunkAnalysisResultTable(Base):
    """Database table for chunk analysis results (ML vs Hunt scoring comparison)."""
    
    __tablename__ = 'chunk_analysis_results'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    chunk_start = Column(Integer, nullable=False)
    chunk_end = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    model_version = Column(String(50), nullable=False, index=True)
    ml_prediction = Column(Boolean, nullable=False, index=True)
    ml_confidence = Column(Float, nullable=False)
    hunt_score = Column(Float, nullable=False, index=True)
    hunt_prediction = Column(Boolean, nullable=False, index=True)
    perfect_discriminators_found = Column(ARRAY(String), nullable=True)
    good_discriminators_found = Column(ARRAY(String), nullable=True)
    lolbas_matches_found = Column(ARRAY(String), nullable=True)
    intelligence_matches_found = Column(ARRAY(String), nullable=True)
    negative_matches_found = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    article = relationship("ArticleTable", back_populates="chunk_analysis_results")
    
    def __repr__(self):
        return f"<ChunkAnalysisResult(id={self.id}, article_id={self.article_id}, model_version='{self.model_version}')>"


class ChatLogTable(Base):
    """Database table for RAG chat logs and evaluation."""
    
    __tablename__ = 'chat_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    query = Column(Text, nullable=False)
    retrieved_chunks = Column(JSON, nullable=True)  # List of chunk IDs and metadata
    llm_response = Column(Text, nullable=True)
    model_used = Column(String(100), nullable=True)
    urls = Column(JSON, nullable=True)  # List of source URLs
    similarity_scores = Column(JSON, nullable=True)  # List of similarity scores
    response_time_ms = Column(Integer, nullable=True)
    
    # Evaluation fields
    relevance_score = Column(Float, nullable=True)  # User rating 1-5
    hallucination_detected = Column(Boolean, nullable=True)
    accuracy_rating = Column(Float, nullable=True)  # User rating 1-5
    user_feedback = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<ChatLog(id={self.id}, session_id='{self.session_id}', query='{self.query[:50]}...')>"


class ChunkClassificationFeedbackTable(Base):
    """Database table for chunk classification feedback."""
    
    __tablename__ = 'chunk_classification_feedback'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    chunk_id = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    model_classification = Column(String(20), nullable=False)
    model_confidence = Column(Float, nullable=False)
    model_reason = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=False)
    user_classification = Column(String(20), nullable=True)
    comment = Column(Text, nullable=True)
    used_for_training = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    article = relationship("ArticleTable")
    
    def __repr__(self):
        return f"<ChunkClassificationFeedback(id={self.id}, article_id={self.article_id}, chunk_id={self.chunk_id})>"


class SigmaRuleTable(Base):
    """Database table for Sigma detection rules from SigmaHQ repository."""
    
    __tablename__ = 'sigma_rules'
    
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    logsource = Column(JSONB, nullable=False)
    detection = Column(JSONB, nullable=False)
    tags = Column(ARRAY(String), nullable=False, default=list)
    level = Column(String(20), nullable=True)
    status = Column(String(20), nullable=True)
    author = Column(Text, nullable=True)
    date = Column(DateTime, nullable=True)
    rule_references = Column(ARRAY(Text), nullable=False, default=list)
    false_positives = Column(ARRAY(Text), nullable=False, default=list)
    fields = Column(ARRAY(String), nullable=False, default=list)
    
    # Embedding fields
    embedding = Column(Vector(768), nullable=True, index=True)
    embedding_model = Column(String(100), nullable=True, default='intfloat/e5-base-v2')
    embedded_at = Column(DateTime, nullable=True)
    
    # Section-based embedding fields for enhanced similarity
    title_embedding = Column(Vector(768), nullable=True)
    description_embedding = Column(Vector(768), nullable=True)
    tags_embedding = Column(Vector(768), nullable=True)
    logsource_embedding = Column(Vector(768), nullable=True)
    detection_structure_embedding = Column(Vector(768), nullable=True)
    detection_fields_embedding = Column(Vector(768), nullable=True)
    
    # Source tracking
    file_path = Column(Text, nullable=False)
    repo_commit_sha = Column(String(40), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    article_matches = relationship("ArticleSigmaMatchTable", back_populates="sigma_rule", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<SigmaRule(id={self.id}, rule_id='{self.rule_id}', title='{self.title[:50]}...')>"


class ArticleSigmaMatchTable(Base):
    """Database table for article-to-Sigma rule matches with coverage analysis."""
    
    __tablename__ = 'article_sigma_matches'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    sigma_rule_id = Column(Integer, ForeignKey('sigma_rules.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Match metadata
    similarity_score = Column(Float, nullable=False)
    match_level = Column(String(20), nullable=False, index=True)
    chunk_id = Column(Integer, nullable=True)
    
    # Coverage classification
    coverage_status = Column(String(20), nullable=False, index=True)
    coverage_confidence = Column(Float, nullable=True)
    coverage_reasoning = Column(Text, nullable=True)
    
    # Behavior extraction from chunk_analysis_results
    matched_discriminators = Column(ARRAY(String), nullable=False, default=list)
    matched_lolbas = Column(ARRAY(String), nullable=False, default=list)
    matched_intelligence = Column(ARRAY(String), nullable=False, default=list)
    
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    article = relationship("ArticleTable", backref="sigma_matches")
    sigma_rule = relationship("SigmaRuleTable", back_populates="article_matches")
    
    def __repr__(self):
        return f"<ArticleSigmaMatch(id={self.id}, article_id={self.article_id}, sigma_rule_id={self.sigma_rule_id}, coverage='{self.coverage_status}')>"


class AppSettingsTable(Base):
    """Database table for application settings (user preferences that override environment variables)."""

    __tablename__ = 'app_settings'

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)  # e.g., 'llm', 'api', 'system'

    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AppSettings(key='{self.key}', value='{self.value[:50] if self.value else None}...')>"


class AgenticWorkflowConfigTable(Base):
    """Database table for agentic workflow configuration settings."""
    
    __tablename__ = 'agentic_workflow_config'
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Configuration parameters
    min_hunt_score = Column(Float, nullable=False, default=97.0)
    ranking_threshold = Column(Float, nullable=False, default=6.0)
    similarity_threshold = Column(Float, nullable=False, default=0.5)
    junk_filter_threshold = Column(Float, nullable=False, default=0.8)  # min_confidence for junk filter (0.0-1.0)
    
    # Versioning and audit
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    description = Column(Text, nullable=True)
    
    # Agent prompts (JSONB: {agent_name: {prompt: "...", instructions: "..."}})
    agent_prompts = Column(JSONB, nullable=True)
    
    # Agent models (JSONB: {agent_name: "model_name"})
    # e.g., {"RankAgent": "deepseek/deepseek-r1", "ExtractAgent": "...", "SigmaAgent": "..."}
    agent_models = Column(JSONB, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<AgenticWorkflowConfig(id={self.id}, min_hunt_score={self.min_hunt_score}, is_active={self.is_active})>"


class AgenticWorkflowExecutionTable(Base):
    """Database table for tracking agentic workflow executions."""
    
    __tablename__ = 'agentic_workflow_executions'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Execution state
    status = Column(String(50), nullable=False, default='pending', index=True)  # pending, running, completed, failed
    current_step = Column(String(50), nullable=True)  # junk_filter, rank_article, extract_agent, generate_sigma, similarity_search, promote_to_queue
    config_snapshot = Column(JSONB, nullable=True)  # Snapshot of config used for this execution
    
    # Step results (stored as JSONB for flexibility)
    junk_filter_result = Column(JSONB, nullable=True)
    ranking_score = Column(Float, nullable=True)
    ranking_reasoning = Column(Text, nullable=True)  # Full LLM reasoning response
    extraction_result = Column(JSONB, nullable=True)
    sigma_rules = Column(JSONB, nullable=True)  # Array of generated rules
    similarity_results = Column(JSONB, nullable=True)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    error_log = Column(JSONB, nullable=True)  # Detailed error logs per step
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    article = relationship("ArticleTable", backref="workflow_executions")
    
    def __repr__(self):
        return f"<AgenticWorkflowExecution(id={self.id}, article_id={self.article_id}, status='{self.status}', step='{self.current_step}')>"


class SigmaRuleQueueTable(Base):
    """Database table for queuing SIGMA rules pending human review and PR submission."""
    
    __tablename__ = 'sigma_rule_queue'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    workflow_execution_id = Column(Integer, ForeignKey('agentic_workflow_executions.id', ondelete='CASCADE'), nullable=True, index=True)
    
    # Rule data
    rule_yaml = Column(Text, nullable=False)
    rule_metadata = Column(JSONB, nullable=True)  # Extracted title, description, tags, etc.
    
    # Similarity results
    similarity_scores = Column(JSONB, nullable=True)  # Array of {rule_id, similarity, title} objects
    max_similarity = Column(Float, nullable=True)
    
    # Queue status
    status = Column(String(50), nullable=False, default='pending', index=True)  # pending, approved, rejected, submitted
    reviewed_by = Column(String(255), nullable=True)
    review_notes = Column(Text, nullable=True)
    
    # PR submission tracking
    pr_submitted = Column(Boolean, nullable=False, default=False)
    pr_url = Column(Text, nullable=True)
    pr_repository = Column(String(255), nullable=True)  # e.g., 'SigmaHQ/sigma'
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    reviewed_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    article = relationship("ArticleTable", backref="queued_sigma_rules")
    workflow_execution = relationship("AgenticWorkflowExecutionTable", backref="queued_rules")
    
    def __repr__(self):
        return f"<SigmaRuleQueue(id={self.id}, article_id={self.article_id}, status='{self.status}')>"


class AgentPromptVersionTable(Base):
    """Database table for version control of agent prompts."""
    
    __tablename__ = 'agent_prompt_versions'
    
    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(255), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    instructions = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, index=True)
    workflow_config_version = Column(Integer, nullable=False, index=True)  # Links to AgenticWorkflowConfigTable.version
    
    # Change tracking
    change_description = Column(Text, nullable=True)  # Optional description of changes
    changed_by = Column(String(255), nullable=True)  # Future: user who made the change
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    
    def __repr__(self):
        return f"<AgentPromptVersion(id={self.id}, agent_name='{self.agent_name}', version={self.version})>"
