"""Rating and categorization models for articles."""

from datetime import datetime

from pydantic import BaseModel, Field, validator


class ArticleRating(BaseModel):
    """Model for article ratings."""

    id: int | None = None
    article_id: int = Field(..., description="ID of the rated article")
    rating: int = Field(..., ge=1, le=5, description="Rating from 1-5 stars")
    feedback: str | None = Field(None, description="Optional feedback text")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When rating was created")
    updated_at: datetime | None = Field(None, description="When rating was last updated")

    @validator("rating")
    def validate_rating(cls, v):
        """Validate rating is between 1 and 5."""
        if not 1 <= v <= 5:
            raise ValueError("Rating must be between 1 and 5")
        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
        schema_extra = {
            "example": {
                "article_id": 123,
                "rating": 4,
                "feedback": "Good threat intelligence with actionable insights",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class ArticleCategorization(BaseModel):
    """Model for article training categorizations."""

    id: int | None = None
    article_id: int = Field(..., description="ID of the categorized article")
    category: str = Field(..., description="Category: 'chosen' or 'rejected'")
    reason: str | None = Field(None, description="Optional reason for categorization")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When categorization was created")
    updated_at: datetime | None = Field(None, description="When categorization was last updated")

    @validator("category")
    def validate_category(cls, v):
        """Validate category is either 'chosen' or 'rejected'."""
        valid_categories = {"chosen", "rejected"}
        if v not in valid_categories:
            raise ValueError(f"Category must be one of {valid_categories}")
        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
        schema_extra = {
            "example": {
                "article_id": 123,
                "category": "chosen",
                "reason": "High-quality threat intelligence with technical details",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class RatingCreate(BaseModel):
    """Model for creating new ratings."""

    article_id: int
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = None


class CategorizationCreate(BaseModel):
    """Model for creating new categorizations."""

    article_id: int
    category: str
    reason: str | None = None
