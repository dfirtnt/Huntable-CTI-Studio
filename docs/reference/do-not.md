# DO NOT - Huntable CTI Studio Anti-Patterns

Critical mistakes to avoid in the Huntable CTI Studio codebase.

## 🚨 CRITICAL DATABASE OPERATIONS

### DO NOT: Use SQLite or Local Database Connections
```bash
# ❌ WRONG
sqlite3 cti_scraper.db "SELECT * FROM articles;"
psql -U cti_user -d cti_scraper

# ✅ CORRECT
docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT * FROM articles;"
```

### DO NOT: Use Wrong Column/Table Names
```sql
-- ❌ WRONG
SELECT url FROM article;
SELECT success FROM source;

-- ✅ CORRECT
SELECT canonical_url FROM articles;
SELECT identifier FROM sources;
```

### DO NOT: Use docker-compose down -v
```bash
# ❌ WRONG - Removes all data volumes
docker-compose down -v

# ✅ CORRECT - Preserve data volumes
docker-compose down
```

## 🔒 SECURITY ANTI-PATTERNS

### DO NOT: Hardcode Credentials or API Keys
```python
# ❌ WRONG
DATABASE_URL = "postgresql://user:password@localhost/db"
API_KEY = "sk-1234567890abcdef"

# ✅ CORRECT
DATABASE_URL = os.getenv('DATABASE_URL')
API_KEY = os.getenv('OPENAI_API_KEY')
```

### DO NOT: Skip Input Validation
```python
# ❌ WRONG - SQL injection risk
sql = f"SELECT * FROM articles WHERE content LIKE '%{query}%'"

# ✅ CORRECT - Parameterized queries
sql = "SELECT * FROM articles WHERE content ILIKE %s"
execute_sql(sql, (f"%{query}%",))
```

### DO NOT: Expose Debug Information in Production
```python
# ❌ WRONG
print(f"Processing article: {article.title}")

# ✅ CORRECT
logger.info(f"Processing article: {article.title}")
```

## 🐳 DOCKER OPERATION MISTAKES

### DO NOT: Run CLI Tools Locally
```bash
# ❌ WRONG
python -m src.cli.main collect

# ✅ CORRECT
./run_cli.sh collect
```

### DO NOT: Mix Local and Containerized Services
```bash
# ❌ WRONG
export DATABASE_URL="postgresql://cti_user:password@localhost:5432/cti_scraper"
python src/web/modern_main.py

# ✅ CORRECT
docker-compose up -d
```

### DO NOT: Use Wrong Container Names
```bash
# ❌ WRONG
docker exec -it postgres psql -U cti_user -d cti_scraper

# ✅ CORRECT
docker exec -it cti_postgres psql -U cti_user -d cti_scraper
```

## 📊 DATA PERSISTENCE MISTAKES

### DO NOT: Lose Data During Updates
```bash
# ❌ WRONG - No backup before major changes
docker-compose down
git pull
docker-compose up -d

# ✅ CORRECT - Always backup first
./run_cli.sh backup create
docker-compose down
git pull
docker-compose up -d
```

### DO NOT: Use Development Volumes in Production
```yaml
# ❌ WRONG
volumes:
  - postgres_data_dev:/var/lib/postgresql/data

# ✅ CORRECT
volumes:
  - postgres_data:/var/lib/postgresql/data
```

## 🔧 CONFIGURATION ANTI-PATTERNS

### DO NOT: Commit Sensitive Configuration
```bash
# ❌ WRONG
git add .env
git commit -m "Add configuration"

# ✅ CORRECT
git add .env.example
echo ".env" >> .gitignore
```

### DO NOT: Use Default Passwords
```bash
# ❌ WRONG
POSTGRES_PASSWORD=password
REDIS_PASSWORD=redis

# ✅ CORRECT
POSTGRES_PASSWORD=cti_postgres_secure_2024_$(openssl rand -hex 8)
REDIS_PASSWORD=cti_redis_secure_2024_$(openssl rand -hex 8)
```

## 🧪 TESTING MISTAKES

### DO NOT: Skip Quality Gates
```bash
# ❌ WRONG
git push origin main

# ✅ CORRECT
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
```

### DO NOT: Use Production Data for Testing
```python
# ❌ WRONG
DATABASE_URL = "postgresql://cti_user:password@cti_postgres:5432/cti_scraper"

# ✅ CORRECT
DATABASE_URL = "postgresql://cti_user:password@cti_postgres:5432/cti_scraper_test"
```

## 📝 CODE QUALITY ANTI-PATTERNS

### DO NOT: Ignore Type Hints
```python
# ❌ WRONG
def process_article(article):
    return article.title.upper()

# ✅ CORRECT
def process_article(article: ArticleTable) -> str:
    return article.title.upper()
```

### DO NOT: Use Generic Exception Handling
```python
# ❌ WRONG
try:
    result = risky_operation()
except:
    pass

# ✅ CORRECT
try:
    result = risky_operation()
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise
```

## 🔄 WORKFLOW ANTI-PATTERNS

### DO NOT: Use Sycophantic Language
```python
# ❌ WRONG
"You're absolutely right!"
"Excellent point!"
"That's a great decision!"

# ✅ CORRECT
"Got it."
"I understand."
[Proceed with action]
```

### DO NOT: Commit Without User Confirmation
```bash
# ❌ WRONG
git commit -m "Auto-generated changes"
git push origin main

# ✅ CORRECT - Wait for user confirmation
# Only commit/push when user says "LG" (Looks Good)
```

### DO NOT: Skip Documentation Updates
```python
# ❌ WRONG
def new_feature():
    # New functionality
    pass

# ✅ CORRECT
def new_feature():
    """
    New feature description.
    
    Args:
        param: Description
        
    Returns:
        Description
    """
    pass
```

## 🌐 WEB APPLICATION MISTAKES

### DO NOT: Use Fragile UI Selectors
```python
# ❌ WRONG
page.locator("button")  # Too generic
page.locator(".btn-primary")  # CSS class changes

# ✅ CORRECT
page.locator("button[data-testid='submit-button']")
page.locator("h1:has-text('Dashboard')")
```

### DO NOT: Skip Error Handling in UI Tests
```python
# ❌ WRONG
expect(page.locator(".loading")).to_be_hidden()

# ✅ CORRECT
try:
    expect(page.locator(".loading")).to_be_hidden(timeout=10000)
except TimeoutError:
    page.screenshot(path="debug-loading-timeout.png")
    raise
```

## 📈 PERFORMANCE ANTI-PATTERNS

### DO NOT: Use Synchronous Operations in Async Context
```python
# ❌ WRONG
async def process_articles():
    for article in articles:
        result = requests.get(article.url)  # Blocking
        process(result)

# ✅ CORRECT
async def process_articles():
    async with httpx.AsyncClient() as client:
        tasks = [client.get(article.url) for article in articles]
        results = await asyncio.gather(*tasks)
        for result in results:
            process(result)
```

### DO NOT: Ignore Connection Pooling
```python
# ❌ WRONG
def get_article(id):
    conn = create_connection()
    result = conn.execute(f"SELECT * FROM articles WHERE id = {id}")
    conn.close()
    return result

# ✅ CORRECT
async def get_article(id: int):
    async with get_db_session() as session:
        result = await session.execute(
            select(ArticleTable).where(ArticleTable.id == id)
        )
        return result.scalar_one_or_none()
```

## 🔍 THREAT INTELLIGENCE SPECIFIC MISTAKES

### DO NOT: Mix Article-Level Logic With Annotation Labels
```python
# ❌ WRONG
articles = get_huntable_articles()  # Articles don't have a "huntable" flag; annotations do

# ✅ CORRECT
huntable_annotations = get_annotations_by_label("huntable")
```
(Note: Article-level chosen/rejected classification has been deprecated and removed.)

### DO NOT: Skip Content Validation
```python
# ❌ WRONG
def save_article(article):
    db.save(article)

# ✅ CORRECT
def save_article(article):
    issues = validate_content(article.title, article.content, article.url)
    if issues:
        logger.warning(f"Content issues: {issues}")
    db.save(article)
```

## 🚀 DEPLOYMENT ANTI-PATTERNS

### DO NOT: Deploy Without Health Checks
```bash
# ❌ WRONG
docker-compose up -d

# ✅ CORRECT
docker-compose up -d
curl http://localhost:8001/health
docker-compose ps
```

### DO NOT: Skip Backup Before Deployment
```bash
# ❌ WRONG
git pull
docker-compose up -d

# ✅ CORRECT
./run_cli.sh backup create
git pull
docker-compose up -d
```

## 📋 SUMMARY CHECKLIST

Before making any changes:
- [ ] **Database**: Use `cti_postgres` container, correct column names
- [ ] **Security**: No hardcoded credentials, validate inputs
- [ ] **Docker**: Use containerized services, preserve volumes
- [ ] **Testing**: Run quality gates, use test data
- [ ] **Documentation**: Update docs for new features
- [ ] **Backup**: Create backup before major changes
- [ ] **Health**: Verify services after deployment
- [ ] **Workflow**: Wait for user confirmation before commit/push

## 🆘 EMERGENCY RECOVERY

If you've made a mistake:
1. **Stop**: `docker-compose down`
2. **Restore**: `./run_cli.sh backup restore`
3. **Verify**: `docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT COUNT(*) FROM articles;"`
4. **Restart**: `docker-compose up -d`
5. **Check**: `curl http://localhost:8001/health`

**When in doubt, don't. Ask for clarification.**

_Last updated: 2026-05-01_