# ML vs Hunt Comparison Dashboard Guide

## Overview

The ML vs Hunt Comparison Dashboard is a comprehensive analytics interface that provides detailed analysis of machine learning model performance compared to the Hunt scoring system. This dashboard enables data-driven model improvements and performance monitoring.

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
- [Time Series Analysis](#time-series-analysis)
- [Model Retraining](#model-retraining)
- [Model Evaluation](#model-evaluation)
- [Performance Visualization](#performance-visualization)
- [Backfill Processing](#backfill-processing)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)

## Features

### 📊 Classification Trends Chart
- **Time series visualization** showing how ML and Hunt predictions align across model versions
- **Four categories tracked**: Agreement, ML-only, Hunt-only, and Neither
- **Percentage-based metrics** for better trend analysis
- **Interactive tooltips** with training dates and accuracy metrics

### 🔄 Model Retraining Panel
- **Feedback tracking** to prevent duplicate training on the same data
- **Automatic feedback marking** after retraining completes
- **Visual feedback** for button states (disabled when no feedback available)
- **Progress tracking** during retraining process

### 🧪 Model Evaluation
- **Test set evaluation** on 160 annotated chunks from article_annotations table
- **Comprehensive metrics**: accuracy, precision, recall, F1 scores
- **Confusion matrix** visualization
- **Misclassified chunk analysis** with examples

### 📈 Performance Visualization
- **Radar chart** with 4 focused metrics (Accuracy, Precision, Recall, F1 for Huntable)
- **Accuracy trends** over model versions
- **Real-time data updates**
- **Export capabilities** for further analysis

## Getting Started

### Accessing the Dashboard
1. Navigate to the main menu
2. Click on "ML vs Hunt Comparison"
3. The dashboard will load with current model statistics

### Initial Data Loading
- **Total Model Versions**: Number of trained model versions
- **Total Chunk Analyses**: Total number of chunk analyses performed (currently 11,644)
- **Average Accuracy**: Average accuracy across all model versions
- **Last Updated**: Date of last model training or evaluation

## Time Series Analysis

### Understanding the Chart
The Classification Trends chart shows how the relationship between ML predictions and Hunt scoring has evolved across different model versions.

**Categories Explained:**
- **Agreement (Both Huntable)**: Both ML and Hunt systems classify content as huntable
- **ML Only (ML Huntable)**: Only ML system classifies as huntable
- **Hunt Only (Hunt Huntable)**: Only Hunt system classifies as huntable  
- **Neither (Not Huntable)**: Both systems classify as not huntable

### Chart Features
- **Y-axis**: Percentage of chunks (0-100%)
- **X-axis**: Model versions (v0, v1, v2, etc.)
- **Interactive tooltips**: Hover over data points for detailed information
- **Logarithmic scale**: Better visibility of different value ranges

### Interpreting Trends
- **Increasing Agreement**: Model is learning to align with Hunt scoring
- **Decreasing ML Only**: Model is becoming more conservative
- **Stable Neither**: Consistent filtering of non-huntable content

## Model Retraining (Cumulative Learning)

### How Retraining Works
**Important**: The retraining system uses **cumulative learning** - each retraining session builds upon ALL previous data:

1. **Original Training Data** (baseline model)
2. **ALL Previous Feedback** (from all previous retraining sessions)
3. **ALL Previous Annotations** (from all previous retraining sessions)
4. **New Feedback/Annotations** (since last retraining)

### Prerequisites
- **User feedback required**: Must have feedback from chunk debugging corrections
- **Minimum feedback**: System tracks available feedback count
- **Feedback source**: Corrections made during chunk debugging interface

### Retraining Process
1. **Check Feedback Count**: Ensure sufficient feedback is available
2. **Click "Retrain Model"**: Button is disabled if no feedback available
3. **Monitor Progress**: Progress bar shows retraining status
4. **Review Results**: New model version and performance metrics displayed

### Cumulative Learning Benefits
- **No Data Loss**: All previous feedback is preserved and reused
- **Progressive Improvement**: Model accuracy improves with each retraining
- **Stable Learning**: No catastrophic forgetting of previous knowledge
- **Small Batch Friendly**: Even small amounts of new feedback improve the model
- **Efficient Training**: All user corrections contribute to model improvement

### Feedback Tracking
- **Automatic marking**: New feedback is marked as "used" after retraining
- **Preservation**: Previously used feedback remains in the training dataset
- **Cumulative dataset**: Each retraining uses original + all previous + new data
- **Duplicate prevention**: Same feedback cannot be used twice
- **Source tracking**: Feedback comes from chunk debugging corrections
- **Count accuracy**: Real-time feedback count updates

## Model Evaluation

### Evaluation Process
1. **Click "Evaluate Current Model"**: Starts evaluation on test set
2. **Monitor Progress**: Progress bar shows evaluation status
3. **Review Results**: Comprehensive metrics displayed

### Metrics Explained
- **Accuracy**: Overall percentage of correct predictions
- **Precision (Huntable)**: Of predicted huntable, how many were actually huntable
- **Recall (Huntable)**: Of actually huntable, how many were predicted huntable
- **F1 Score (Huntable)**: Harmonic mean of precision and recall
- **Confusion Matrix**: Detailed breakdown of true/false positives/negatives

### Test Set Details
- **Size**: 160 annotated chunks
- **Source**: article_annotations table
- **Quality**: Manually annotated by users
- **Coverage**: Representative sample of content types

## Performance Visualization

### Radar Chart
The radar chart shows 4 key metrics for the latest evaluated model version:
- **Accuracy**: Overall model performance
- **Precision (Huntable)**: How good at identifying huntable content
- **Recall (Huntable)**: How much huntable content is caught
- **F1 (Huntable)**: Balanced metric for huntable detection

### Accuracy Trends Chart
- **Line chart** showing accuracy progression across model versions
- **Y-axis**: Accuracy percentage (0-100%)
- **X-axis**: Model versions
- **Trend analysis**: Shows model improvement over time

## Backfill Processing

### Purpose
Process articles with high hunt scores to populate comparison data for analysis.

### Process
1. **Check Eligible Count**: See how many articles are eligible for processing
2. **Click "Process All Eligible Articles"**: Starts backfill processing
3. **Monitor Progress**: Progress bar shows processing status
4. **Review Results**: Summary of processed articles

### Eligibility Criteria
- **Hunt Score**: Articles must have hunt_score > 50
- **Not Processed**: Articles not already processed for chunk analysis
- **Content Quality**: Articles must meet quality thresholds

## API Endpoints

### Model Management
- `GET /api/model/versions` - List all model versions with performance metrics
- `GET /api/model/classification-timeline` - Get classification trends data
- `POST /api/model/retrain` - Trigger model retraining
- `POST /api/model/evaluate` - Evaluate current model on test set

### Feedback Management
- `GET /api/model/feedback-count` - Get count of available feedback samples
- `POST /api/feedback/chunk-classification` - Submit user feedback

### Data Processing
- `GET /api/ml-hunt-comparison/eligible-count` - Get count of eligible articles
- `POST /api/ml-hunt-comparison/backfill` - Process eligible articles
- `GET /api/ml-hunt-comparison/summary` - Get dashboard summary statistics
- `GET /api/ml-hunt-comparison/stats` - Get detailed comparison statistics

## Configuration

### Content Filter Settings
The dashboard metrics are influenced by three key content filter settings:

1. **min_confidence: 0.7** (70% confidence threshold)
   - Only chunks with ML confidence ≥ 70% are considered "huntable"
   - Primary filter for chunk-level decisions

2. **quality_threshold: 0.5** (50% quality threshold)
   - Articles must pass quality checks to be processed
   - Filters out low-quality content before chunking

3. **cost_threshold: 0.1** (10% cost threshold)
   - Articles with estimated processing costs > 10% are filtered out
   - Prevents expensive articles from being processed

### Data Scope
- **Hunt Score Filter**: Only articles with hunt_score > 50 are included
- **Confidence Filter**: Only chunks with ML confidence ≥ 70% are analyzed
- **Quality Filter**: Only high-quality articles are processed

## Troubleshooting

### Common Issues

#### "Retrain Model" Button Disabled
- **Cause**: No user feedback available for retraining
- **Solution**: Provide feedback through chunk debugging interface
- **Check**: Look at "Available feedback" count in retraining panel

#### Chart Not Loading
- **Cause**: JavaScript errors or missing data
- **Solution**: Refresh page and check browser console
- **Check**: Ensure all containers are running properly

#### Evaluation Fails
- **Cause**: Missing test data or model issues
- **Solution**: Check that article_annotations table has data
- **Check**: Verify model files are present

#### Backfill Processing Fails
- **Cause**: No eligible articles or processing errors
- **Solution**: Check eligible count and review error messages
- **Check**: Ensure articles have hunt_score > 50

### Performance Tips
- **Large datasets**: Charts may take time to load with large amounts of data
- **Browser cache**: Clear cache if charts display incorrectly
- **Network issues**: Check API endpoint responses in browser developer tools

### Data Accuracy
- **Real-time updates**: Data is updated in real-time from database
- **No artificial limits**: All data is included (no 10,000 limit)
- **Accurate counts**: Statistics reflect actual database contents

## Best Practices

### Model Retraining
- **Regular evaluation**: Evaluate model before retraining
- **Sufficient feedback**: Ensure adequate feedback before retraining
- **Monitor trends**: Watch classification trends for improvement
- **Document changes**: Note what changes were made between versions

### Performance Monitoring
- **Regular checks**: Monitor dashboard weekly for trends
- **Anomaly detection**: Watch for sudden changes in metrics
- **Feedback quality**: Ensure high-quality feedback for training
- **Data consistency**: Verify data accuracy and completeness

### Usage Guidelines
- **Access frequency**: Dashboard can be accessed as needed
- **Data interpretation**: Understand what metrics mean for your use case
- **Action planning**: Use insights to plan model improvements
- **Documentation**: Keep records of model performance over time
