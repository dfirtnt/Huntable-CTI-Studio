#!/bin/bash
# Extract CmdlineExtract prompts for multiple config versions

AGENT_NAME="CmdlineExtract"
VERSIONS="${@:-598 599 928 941 978}"  # Default to highlighted versions if none provided

echo "Extracting prompts for versions: $VERSIONS"
echo "=========================================="

for version in $VERSIONS; do
    echo ""
    echo "--- Config Version $version ---"
    docker exec cti_postgres psql -U cti_user -d cti_scraper -t -c \
        "SELECT agent_prompts->'$AGENT_NAME'->>'prompt' FROM agentic_workflow_config WHERE version = $version;" \
        | python3 -c "import sys, json; data=sys.stdin.read().strip(); print(json.loads(data).get('role', data[:200]) if data.startswith('{') else data[:200])" 2>/dev/null || \
        docker exec cti_postgres psql -U cti_user -d cti_scraper -t -c \
        "SELECT LEFT(agent_prompts->'$AGENT_NAME'->>'prompt', 200) FROM agentic_workflow_config WHERE version = $version;"
done
