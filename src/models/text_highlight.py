"""Pydantic models for text highlighting and categorization."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TextHighlightCreate(BaseModel):
    """Model for creating a new text highlight."""
    article_id: int = Field(..., description="ID of the article containing the highlighted text")
    selected_text: str = Field(..., description="The text that was highlighted/selected")
    start_offset: int = Field(..., description="Starting character position in the article content")
    end_offset: int = Field(..., description="Ending character position in the article content")
    is_huntable: bool = Field(..., description="Whether the user categorized this text as huntable")


class TextHighlightUpdate(BaseModel):
    """Model for updating an existing text highlight."""
    is_huntable: bool = Field(..., description="Whether the user categorized this text as huntable")


class TextHighlight(BaseModel):
    """Model for text highlight data."""
    id: int
    article_id: int
    selected_text: str
    start_offset: int
    end_offset: int
    is_huntable: bool
    categorized_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TextHighlightResponse(BaseModel):
    """Response model for text highlight operations."""
    success: bool
    message: str
    highlight: Optional[TextHighlight] = None
