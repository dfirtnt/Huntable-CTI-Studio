# Quickstart

**By the end of this guide you will have:**

1. Ingested a real CTI article (CISA advisory)
2. Run the full agentic workflow (OS detection → extraction → Sigma generation)
3. Viewed extracted huntables and validated Sigma rules
4. Confirmed the stack is healthy with pytest

Total time: ~5 minutes (plus initial Docker image build).

---

End-to-end run using Docker Compose and the built-in workflow. Commands use `python3` explicitly and match the live stack (`./start.sh`, ports 8001/8888).

## 1) Prerequisites
- Docker and the Docker Compose plugin available on your PATH
- `python3` for running tests, `jq` for parsing JSON responses
- Ports `8001` and `8888` free on the host
- `.env` configured (copy from `.env.example` and set `POSTGRES_PASSWORD`; add LLM keys if you want AI features)

## 2) Start the stack
```bash
git clone https://github.com/starlord/CTIScraper.git
cd CTIScraper
cp .env.example .env
echo "POSTGRES_PASSWORD=change_me" >> .env   # replace with a strong password
./start.sh                                    # builds + launches docker-compose
```
Check that services are healthy:
```bash
docker-compose ps
curl http://localhost:8001/health
```
UI entry points:
- Web UI + API docs: http://localhost:8001
- OpenAPI schema: http://localhost:8001/docs

## 3) Ingest a CTI article
Use the manual scrape endpoint to pull a real article into the database and capture its ID:
```bash
ARTICLE_ID=$(curl -s -X POST http://localhost:8001/api/scrape-url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-214a","force_scrape":true}' | jq -r '.article_id')
echo "Article ID: ${ARTICLE_ID}"
```

## 4) Run the agentic workflow
Trigger the full pipeline (OS detection → junk filter → ranking → Extract Agent → Sigma → similarity search):
```bash
TRIGGER=$(curl -s -X POST "http://localhost:8001/api/workflow/articles/${ARTICLE_ID}/trigger")
EXECUTION_ID=$(echo "$TRIGGER" | jq -r '.execution_id')
```
If an execution is already running for the article, the API returns an error; wait for it to finish or clear the stuck run before retrying.

## 5) Monitor and view huntables
Watch execution status and counts:
```bash
curl -s "http://localhost:8001/api/workflow/executions?article_id=${ARTICLE_ID}" | jq '.executions[0] | {id,status,extraction_counts}'
```
When `status` is `completed`, pull the detailed payload to see extracted observables (huntables):
```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, discrete_huntables:.extraction_result.discrete_huntables_count, observables:.extraction_result.observables}'
```
You can also review the article page at `http://localhost:8001/articles/${ARTICLE_ID}` (the "Send to Workflow" button mirrors the trigger above and the page surfaces extraction outputs).

## 6) Review Sigma generation
The workflow writes validated Sigma rules to the same execution record. Inspect them via API or UI:
```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, sigma_rules:.sigma_rules}'
```
In the UI, open `http://localhost:8001/articles/${ARTICLE_ID}#sigma` to jump to the Sigma section; logs and similarity matches are also surfaced on the Workflow page.

## 7) Verify with pytest
Run a lightweight API health test from the running web container:
```bash
docker-compose exec web python3 -m pytest tests/api/test_endpoints.py::TestHealthEndpoints::test_health_endpoints -q
```
A zero exit code confirms the stack and core health endpoints are working.

Stack shutdown (optional):
```bash
docker-compose down
```
