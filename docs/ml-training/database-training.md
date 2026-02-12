# Database-Based Training System

## Overview

The ML training system has been refactored to use database storage instead of CSV files for improved data management, consistency, and scalability.

**Migration Date**: 2025-10-18  
**Previous System**: CSV-based feedback storage  
**Current System**: Database-based with PostgreSQL

## Architecture

### Database Tables

#### 1. Chunk Classification Feedback
```sql
CREATE TABLE chunk_classification_feedback (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    chunk_id INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    model_classification VARCHAR(20) NOT NULL,
    model_confidence FLOAT NOT NULL,
    model_reason TEXT,
    is_correct BOOLEAN NOT NULL,
    user_classification VARCHAR(20),
    comment TEXT,
    used_for_training BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
```

**Purpose**: Stores user feedback on ML model predictions for chunk classification.

#### 2. Article Annotations (Training Data)
```sql
-- Existing table, now used for training
SELECT COUNT(*) FROM article_annotations 
WHERE LENGTH(selected_text) >= 950 
AND LENGTH(selected_text) <= 1050 
AND used_for_training = FALSE;
```

**Purpose**: Uses existing annotations as training data with length validation (950-1050 characters).

### Key Features

#### 1. Length Validation
- **Frontend**: JavaScript validation prevents annotations <950 or >1050 characters
- **Backend**: API validation enforces length requirements
- **Purpose**: Ensures optimal training data quality

#### 2. Auto-Expand UI
- **Automatic Selection**: UI automatically expands text to 1000 characters
- **User Experience**: No manual adjustment needed
- **Consistency**: All annotations are optimal length for training

#### 3. Usage Tracking
- **`used_for_training` Flag**: Tracks which data has been used for training
- **Prevents Duplication**: Same data not used multiple times
- **Audit Trail**: Complete history of training data usage

## API Endpoints

### Feedback Management
```http
POST /api/feedback/chunk-classification
Content-Type: application/json

{
    "article_id": 123,
    "chunk_id": 0,
    "chunk_text": "malware sample text...",
    "model_classification": "Huntable",
    "model_confidence": 0.85,
    "is_correct": false,
    "user_classification": "Not Huntable",
    "comment": "User feedback"
}
```

### Annotation Creation
```http
POST /api/articles/{article_id}/annotations
Content-Type: application/json

{
    "annotation_type": "huntable",
    "selected_text": "1000 character text...",
    "start_position": 0,
    "end_position": 1000
}
```

**Validation**: Returns 400 error if text length <950 or >1050 characters.

### Training Status
```http
GET /api/model/feedback-count

Response:
{
    "success": true,
    "count": 5,
    "feedback_count": 2,
    "annotation_count": 3,
    "message": "Found 5 training samples available (2 feedback + 3 annotations)"
}
```

### Model Retraining
```http
POST /api/model/retrain

Response:
{
    "success": true,
    "message": "Retraining completed successfully! New model: v57",
    "new_version": 57,
    "training_accuracy": 0.892,
    "training_samples": 5,
    "feedback_samples": 2,
    "annotation_samples": 3,
    "training_duration": "45.2s"
}
```

## Training Workflow

### 1. Data Collection
```mermaid
graph TD
    A[User Creates Annotation] --> B{Length Valid?}
    B -->|No| C[Show Error Message]
    B -->|Yes| D[Store in article_annotations]
    
    E[User Provides Feedback] --> F[Store in chunk_classification_feedback]
    
    D --> G[Mark as used_for_training = FALSE]
    F --> G
```

### 2. Model Retraining (Cumulative Learning)
```mermaid
graph TD
    A[Trigger Retraining] --> B[Query Database for Unused Data]
    B --> C[Load ALL Previous Feedback]
    C --> D[Load ALL Previous Annotations]
    D --> E[Load Original Training Data]
    E --> F[Combine ALL Data Sets]
    F --> G[Train New Model on Combined Data]
    G --> H[Save Model Version]
    H --> I[Mark New Data as Used]
    I --> J[Return Results]
```

**Key Point: Cumulative Learning Process**
- Each retraining session uses **ALL previous data** (original + all previous feedback + all previous annotations)
- New feedback/annotations are **added to** the existing dataset, not replacing it
- This ensures **progressive improvement** and **no data loss**
- The model builds upon all previous learning, making it more robust over time

**Why This Matters:**
- **No Catastrophic Forgetting**: Previous model knowledge is preserved
- **Stable Learning**: Each retrain builds on solid foundation rather than starting fresh
- **Efficient Use of Data**: All user feedback contributes to model improvement
- **Progressive Accuracy**: Model accuracy improves with each retraining session
- **Small Batch Friendly**: Even small amounts of new feedback improve the model

### 3. Data Usage Tracking
```sql
-- Before training: Count available data
SELECT COUNT(*) FROM chunk_classification_feedback WHERE used_for_training = FALSE;
SELECT COUNT(*) FROM article_annotations 
WHERE LENGTH(selected_text) BETWEEN 950 AND 1050 
AND used_for_training = FALSE;

-- After training: Mark as used
UPDATE chunk_classification_feedback SET used_for_training = TRUE;
UPDATE article_annotations SET used_for_training = TRUE 
WHERE LENGTH(selected_text) BETWEEN 950 AND 1050;
```

## Migration from CSV

### Migration Script
```bash
python scripts/migrate_feedback_csv_to_db.py
```

**What it does**:
- Reads existing `chunk_classification_feedback.csv`
- Imports data into database table
- Preserves all existing feedback
- Marks as `used_for_training = FALSE` for new training

### Backward Compatibility
- **CSV Files**: Still exist but not used for new training
- **Evaluation Data**: `eval_set.csv` remains unchanged
- **Original Training**: `combined_training_data.csv` used as baseline

## Benefits

### 1. Data Integrity
- **ACID Compliance**: Database transactions ensure data consistency
- **Foreign Keys**: Referential integrity with articles table
- **Audit Trail**: Complete history of all training data

### 2. Scalability
- **Indexed Queries**: Fast retrieval of training data
- **Concurrent Access**: Multiple users can provide feedback simultaneously
- **Storage Efficiency**: No duplicate data storage

### 3. User Experience
- **Auto-Expand**: Automatic 1000-character selection
- **Real-time Validation**: Immediate feedback on annotation length
- **Consistent Interface**: Same UI for all annotation types

### 4. Development
- **Type Safety**: SQLAlchemy models with proper typing
- **Query Optimization**: Database-level filtering and aggregation
- **Testing**: Easier to test with database fixtures

## Testing

### Updated Test Files
- `tests/api/test_ml_feedback.py` - API contract tests
- `tests/integration/test_retraining_integration.py` - Workflow tests

### New Test Coverage
- Database feedback storage
- Annotation length validation
- Training data counting
- Usage tracking

### Test Commands
```bash
# Run ML feedback tests
docker exec cti_web python -m pytest tests/api/test_ml_feedback.py -v

# Run retraining integration tests
docker exec cti_web python -m pytest tests/integration/test_retraining_integration.py -v
```

## Monitoring

### Key Metrics
- **Training Samples Available**: Count of unused feedback + annotations
- **Model Accuracy**: Performance on evaluation dataset
- **Data Quality**: Percentage of annotations meeting length requirements
- **Usage Rate**: How quickly training data is consumed

### Database Queries
```sql
-- Available training data
SELECT 
    (SELECT COUNT(*) FROM chunk_classification_feedback WHERE used_for_training = FALSE) as feedback_count,
    (SELECT COUNT(*) FROM article_annotations 
     WHERE LENGTH(selected_text) BETWEEN 950 AND 1050 
     AND used_for_training = FALSE) as annotation_count;

-- Training data quality
SELECT 
    COUNT(*) as total_annotations,
    COUNT(CASE WHEN LENGTH(selected_text) BETWEEN 950 AND 1050 THEN 1 END) as valid_length,
    ROUND(COUNT(CASE WHEN LENGTH(selected_text) BETWEEN 950 AND 1050 THEN 1 END) * 100.0 / COUNT(*), 2) as quality_percentage
FROM article_annotations;
```

## Future Enhancements

### 1. Advanced Analytics
- Training data quality metrics
- Model performance correlation with data quality
- User feedback effectiveness analysis

### 2. Data Management
- Bulk import/export capabilities
- Data archiving for old training sets
- Automated data quality checks

### 3. UI Improvements
- Training data visualization
- Quality metrics dashboard
- Batch annotation tools

## Conclusion

The database-based training system provides a robust, scalable foundation for ML model improvement. Key benefits include:

- ✅ **Data Integrity**: ACID compliance and referential integrity
- ✅ **User Experience**: Auto-expand UI and real-time validation
- ✅ **Scalability**: Efficient database queries and concurrent access
- ✅ **Maintainability**: Type-safe models and comprehensive testing
- ✅ **Monitoring**: Built-in metrics and quality tracking

The system successfully migrates from CSV-based storage while maintaining backward compatibility and improving the overall training workflow.
