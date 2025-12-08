#!/bin/bash
# Start LangGraph server for agentic workflow debugging

set -e

# Default port
PORT=${LANGGRAPH_PORT:-2024}

# Check if langgraph.json exists
if [ ! -f "langgraph.json" ]; then
    echo "Error: langgraph.json not found in current directory"
    exit 1
fi

# Check if docker-compose is available and langgraph-server service exists
if command -v docker-compose &> /dev/null || command -v docker &> /dev/null; then
    if docker-compose ps 2>/dev/null | grep -q langgraph-server || docker compose ps 2>/dev/null | grep -q langgraph-server; then
        USE_COMPOSE=true
    else
        USE_COMPOSE=false
    fi
else
    USE_COMPOSE=false
fi

if [ "$USE_COMPOSE" = true ]; then
    echo "🚀 Starting LangGraph server via docker-compose..."
    echo ""
    echo "Graph: agentic_workflow"
    echo "Server URL: http://localhost:$PORT"
    echo ""
    echo "To connect Agent Chat UI:"
    echo "1. Visit https://smith.langchain.com/studio/?baseUrl=http://localhost:$PORT"
    echo "2. Enter graph ID: agentic_workflow"
    echo "3. Enter server URL: http://localhost:$PORT"
    echo ""
    echo "Commands:"
    echo "  Start:   docker-compose up -d langgraph-server"
    echo "  Stop:    docker-compose stop langgraph-server"
    echo "  Logs:    docker-compose logs -f langgraph-server"
    echo "  Status:  docker-compose ps langgraph-server"
    echo ""
    
    # Start the service
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d langgraph-server
    else
        docker compose up -d langgraph-server
    fi
    
    echo "✅ LangGraph server starting..."
    echo "⏳ Waiting for server to be ready..."
    
    # Wait for health check
    for i in {1..30}; do
        if curl -sf http://localhost:$PORT/health > /dev/null 2>&1; then
            echo "✅ LangGraph server is ready at http://localhost:$PORT"
            exit 0
        fi
        sleep 1
    done
    
    echo "⚠️  Server may still be starting. Check logs: docker-compose logs langgraph-server"
else
    # Check if we're in Docker or should run in Docker
    if [ -f "/.dockerenv" ] || [ -n "$DOCKER_CONTAINER" ]; then
        # Already in Docker
        echo "Starting LangGraph server on port $PORT..."
        if ! command -v langgraph &> /dev/null; then
            pip install -q langgraph-cli
        fi
        langgraph dev --port $PORT --host 0.0.0.0
    else
        # Check if Docker container is running
        if docker ps --format '{{.Names}}' | grep -q "^cti_web$"; then
            echo "⚠️  Running LangGraph server in existing Docker container (cti_web)"
            echo "⚠️  Note: For better reliability, consider using docker-compose langgraph-server service"
            echo ""
            echo "Starting LangGraph server on port $PORT..."
            echo "Graph: agentic_workflow"
            echo "Server URL: http://localhost:$PORT"
            echo ""
            echo "To connect Agent Chat UI:"
            echo "1. Visit https://smith.langchain.com/studio/?baseUrl=http://localhost:$PORT"
            echo "2. Enter graph ID: agentic_workflow"
            echo "3. Enter server URL: http://localhost:$PORT"
            echo ""
            
            # Install if needed
            docker exec cti_web pip install -q langgraph-cli || true
            
            # Run in Docker container (foreground)
            docker exec -it -w /app cti_web /home/cti_user/.local/bin/langgraph dev \
                --port $PORT \
                --host 0.0.0.0
        else
            # Run on host
            if ! command -v langgraph &> /dev/null; then
                echo "LangGraph CLI not found. Installing..."
                if command -v pipx &> /dev/null; then
                    pipx install langgraph-cli
                else
                    pip install langgraph-cli
                fi
            fi
            
            echo "Starting LangGraph server on port $PORT..."
            echo "Graph: agentic_workflow"
            echo "Server URL: http://localhost:$PORT"
            echo ""
            echo "To connect Agent Chat UI:"
            echo "1. Visit https://smith.langchain.com/studio/?baseUrl=http://localhost:$PORT"
            echo "2. Enter graph ID: agentic_workflow"
            echo "3. Enter server URL: http://localhost:$PORT"
            echo ""
            echo "Press Ctrl+C to stop the server"
            echo ""
            
            langgraph dev --port $PORT --host 0.0.0.0
        fi
    fi
fi

