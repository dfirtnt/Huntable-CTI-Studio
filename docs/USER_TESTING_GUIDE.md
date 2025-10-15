# User Testing Guide for CTI Scraper

## 🎯 Testing Overview

The CTI Scraper system includes multiple components ready for user testing! This guide covers both the GPT-4o content filtering system and the enhanced annotation system for ML training data creation.

## 🌐 Web Interface Testing (Primary Method)

### Prerequisites
- ✅ Application is running (confirmed: containers are up)
- ✅ Access to web interface at `http://localhost:8001`
- ✅ OpenAI API key configured in Settings

## 📝 Enhanced Annotation System Testing

### Step-by-Step Annotation Testing

#### 1. Access the Web Interface
```bash
# Application is already running
# Navigate to: http://localhost:8001
```

#### 2. Navigate to Article Detail Page
1. Go to **Articles** section
2. Click on any article to view details
3. **Select text** in the article content area

#### 3. Test Enhanced Annotation Modal
When you select text, you should see:
- **Character counter** (e.g., "186/1000 chars")
- **Length guidance** with color coding:
  - 🟢 Green: Excellent (950-1000 chars)
  - 🟡 Yellow: Too short (<800 chars)
  - 🔵 Blue: Acceptable (800-950 chars)
  - 🔴 Red: Too long (>1000 chars)
- **Expand/contract buttons**: -200, -100, -50, +50, +100, +200 chars
- **🎯 Auto 1000** button for automatic expansion

#### 4. Test Auto-Expand Functionality
1. **Select a short text** (e.g., 200-300 characters)
2. **Click 🎯 Auto 1000** button
3. **Verify**:
   - Character counter updates to ~1000/1000
   - Status changes to "✅ Excellent length for evaluation"
   - Text selection expands in the article (highlighted in blue)
   - Modal shows expanded text preview

#### 5. Test Smart Boundary Detection
1. **Use manual expand buttons** (+100, +200 chars)
2. **Verify** expansion respects sentence/word boundaries
3. **Check** that text doesn't cut mid-word or mid-sentence

#### 6. Test Classification
1. **Expand text** to optimal length (950-1000 chars)
2. **Click 🎯 Huntable** or **❌ Not Huntable**
3. **Verify**:
   - Text gets highlighted in the article
   - Annotation is saved to database
   - Success message appears

## 🤖 GPT-4o Content Filtering Testing

#### 1. Navigate to Article Detail Page
1. Go to **Articles** section
2. Click on any article to view details
3. Look for the **"Rank with GPT4o"** button

#### 3. Test Optimization Dialog
When you click "Rank with GPT4o", you should see:
- **Cost estimation** with filtering preview
- **Optimization options** dialog
- **Confidence threshold** selection (0.5, 0.7, 0.8)
- **Enable/disable filtering** checkbox

#### 4. Test Different Scenarios

**Scenario A: Filtering Enabled (0.7 threshold)**
1. Check "Enable content filtering"
2. Select confidence threshold 0.7
3. Click "Analyze"
4. Observe cost savings in results

**Scenario B: Filtering Disabled**
1. Uncheck "Enable content filtering"
2. Click "Analyze"
3. Compare cost with Scenario A

**Scenario C: Different Confidence Thresholds**
1. Test with 0.5 (aggressive filtering)
2. Test with 0.8 (conservative filtering)
3. Compare results and cost savings

#### 5. Verify Results
After analysis, check for:
- **Optimization metadata** in the response
- **Cost savings** displayed
- **Technical content preserved**
- **Non-technical content filtered**

## 🔧 API Testing (Direct Method)

### Test the New Endpoint

```bash
# Test with filtering enabled
curl -X POST http://localhost:8001/api/articles/1/gpt4o-rank-optimized \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "sk-your-openai-key",
    "use_filtering": true,
    "min_confidence": 0.7
  }'

# Test with filtering disabled
curl -X POST http://localhost:8001/api/articles/1/gpt4o-rank-optimized \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "sk-your-openai-key",
    "use_filtering": false
  }'
```

### Expected Response Format
```json
{
  "success": true,
  "article_id": 1,
  "analysis": "SIGMA HUNTABILITY SCORE: 8...",
  "optimization": {
    "enabled": true,
    "cost_savings": 0.0019,
    "tokens_saved": 388,
    "chunks_removed": 3,
    "min_confidence": 0.7
  }
}
```

## 🐍 Python Testing (Development)

### Run Comprehensive Tests
```bash
# Test the filtering system
python3 scripts/test_filter_comprehensive.py

# Train/retrain the model
python3 scripts/train_content_filter.py --verbose
```

### Test Individual Components
```python
import sys
sys.path.insert(0, 'src')
from utils.content_filter import ContentFilter

# Test with your content
filter_system = ContentFilter('models/content_filter.pkl')
result = filter_system.filter_content(your_content, min_confidence=0.7)
print(f"Cost savings: {result.cost_savings:.1%}")
```

## 📊 Testing Scenarios

### 1. Content Type Testing

**Test Articles with Different Content Types:**

**A. Technical-Heavy Articles**
- Look for articles with PowerShell commands
- File paths, IP addresses, CVE references
- **Expected:** High huntability, minimal filtering

**B. Mixed Content Articles**
- Technical content + acknowledgments
- Commands + contact information
- **Expected:** Moderate filtering (50-70% reduction)

**C. Non-Technical Articles**
- Mostly acknowledgments and general statements
- Marketing content, contact information
- **Expected:** High filtering (80-90% reduction)

### 2. Confidence Threshold Testing

| Threshold | Expected Behavior | Use Case |
|-----------|-------------------|----------|
| 0.5 | Aggressive filtering | Maximum cost savings |
| 0.7 | Balanced filtering | Recommended default |
| 0.8 | Conservative filtering | Preserve more content |

### 3. Cost Savings Validation

**Calculate Expected Savings:**
```python
# Example calculation
original_tokens = 1000
filtered_tokens = 300
tokens_saved = 700
cost_savings = (tokens_saved / 1000000) * 5.00  # $0.0035
```

## 🔍 What to Look For

### ✅ Success Indicators

1. **Cost Reduction**
   - 20-80% cost savings displayed
   - Tokens saved counter increases
   - Cost estimation accuracy

2. **Content Quality**
   - Technical commands preserved
   - File paths and IPs kept
   - Acknowledgments filtered out

3. **User Experience**
   - Smooth optimization dialog
   - Clear cost preview
   - Responsive interface

4. **System Performance**
   - Fast filtering (< 1 second)
   - Reliable API responses
   - Proper error handling

### ❌ Issues to Report

1. **Over-Filtering**
   - Technical content incorrectly removed
   - Commands or IOCs filtered out

2. **Under-Filtering**
   - Acknowledgments not removed
   - High cost with minimal savings

3. **Interface Issues**
   - Dialog not appearing
   - Cost estimates incorrect
   - API errors

4. **Performance Issues**
   - Slow filtering (> 5 seconds)
   - Timeout errors
   - Memory issues

## 📝 Testing Checklist

### Pre-Testing Setup
- [ ] Application running (`docker ps` shows healthy containers)
- [ ] OpenAI API key configured in Settings
- [ ] Model trained (`models/content_filter.pkl` exists)
- [ ] Test articles available

### Web Interface Testing
- [ ] Navigate to article detail page
- [ ] "Rank with GPT4o" button visible
- [ ] Optimization dialog appears
- [ ] Cost estimation shows
- [ ] Different confidence thresholds work
- [ ] Filtering enable/disable works
- [ ] Results show cost savings
- [ ] Technical content preserved

### API Testing
- [ ] New endpoint responds correctly
- [ ] Filtering parameters work
- [ ] Response includes optimization data
- [ ] Error handling works
- [ ] Cost calculations accurate

### Content Quality Testing
- [ ] PowerShell commands preserved
- [ ] File paths kept
- [ ] IP addresses maintained
- [ ] Acknowledgments filtered
- [ ] Contact info removed
- [ ] Marketing content filtered

## 🐛 Troubleshooting

### Common Issues

**1. "Rank with GPT4o" Button Not Visible**
```bash
# Check if endpoint is integrated
grep -r "gpt4o-rank-optimized" src/web/
```

**2. Optimization Dialog Not Appearing**
```bash
# Check JavaScript console for errors
# Verify gpt4o_optimized_js.js is loaded
```

**3. Model Not Found Error**
```bash
# Train the model
python3 scripts/train_content_filter.py
```

**4. API Key Issues**
- Verify API key in Settings
- Check OpenAI API key validity
- Ensure sufficient credits

### Debug Commands

```bash
# Check application logs
docker logs cti_web

# Test model directly
python3 -c "
import sys; sys.path.insert(0, 'src')
from utils.content_filter import ContentFilter
filter_system = ContentFilter('models/content_filter.pkl')
print('Model loaded successfully')
"

# Test API endpoint
curl -X GET http://localhost:8001/api/articles/1
```

## 📈 Success Metrics

### Target Performance
- **Cost Savings:** 20-80% reduction
- **Accuracy:** 80%+ correct classification
- **Speed:** < 1 second filtering time
- **User Satisfaction:** Clear cost preview and results

### Data to Collect
1. **Cost savings per analysis**
2. **Content reduction percentages**
3. **User preference for thresholds**
4. **Technical content preservation rate**
5. **System performance metrics**

## 🎉 Ready to Test!

The system is fully implemented and ready for user testing. Start with the web interface at `http://localhost:8001/articles/{article_id}` and test the "Rank with GPT4o" button with different optimization settings.

**Happy Testing!** 🚀
