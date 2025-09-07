-- Migration: Add article annotations table
-- This migration adds support for text annotations on articles

-- Create article_annotations table
CREATE TABLE article_annotations (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    user_id INTEGER, -- For future user management
    annotation_type VARCHAR(20) NOT NULL CHECK (annotation_type IN ('huntable', 'not_huntable')),
    selected_text TEXT NOT NULL,
    start_position INTEGER NOT NULL,
    end_position INTEGER NOT NULL,
    context_before TEXT,
    context_after TEXT,
    confidence_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_article_annotations_article_id ON article_annotations(article_id);
CREATE INDEX idx_article_annotations_type ON article_annotations(annotation_type);
CREATE INDEX idx_article_annotations_created_at ON article_annotations(created_at);

-- Add comment to the table
COMMENT ON TABLE article_annotations IS 'Text annotations for articles (huntable/not_huntable)';
COMMENT ON COLUMN article_annotations.annotation_type IS 'Type of annotation: huntable or not_huntable';
COMMENT ON COLUMN article_annotations.selected_text IS 'The actual text that was selected';
COMMENT ON COLUMN article_annotations.start_position IS 'Character position where selection starts';
COMMENT ON COLUMN article_annotations.end_position IS 'Character position where selection ends';
COMMENT ON COLUMN article_annotations.context_before IS 'Text context before the selection';
COMMENT ON COLUMN article_annotations.context_after IS 'Text context after the selection';
COMMENT ON COLUMN article_annotations.confidence_score IS 'Confidence score for the annotation (0.0-1.0)';
