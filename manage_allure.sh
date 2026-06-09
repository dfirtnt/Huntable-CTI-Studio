#!/bin/bash

# Allure Reports Container Management Script

set -e

# Pick the available compose invocation (v2 plugin preferred, legacy v1 fallback).
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "❌ Neither 'docker compose' nor 'docker-compose' is available. Install Docker Compose."
    exit 1
fi

case "${1:-help}" in
    "start")
        echo "🚀 Starting Allure Reports container..."
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml up -d
        echo "✅ Allure Reports available at: http://localhost:8080"
        ;;
    "stop")
        echo "🛑 Stopping Allure Reports container..."
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml down
        echo "✅ Allure Reports container stopped"
        ;;
    "restart")
        echo "🔄 Restarting Allure Reports container..."
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml restart
        echo "✅ Allure Reports container restarted"
        ;;
    "logs")
        echo "📋 Showing Allure Reports container logs..."
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml logs -f
        ;;
    "status")
        echo "📊 Allure Reports container status:"
        docker ps | grep allure || echo "❌ Container not running"
        ;;
    "rebuild")
        echo "🔨 Rebuilding Allure Reports container..."
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml down
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml build --no-cache
        $DOCKER_COMPOSE_CMD -f docker-compose.allure.yml up -d
        echo "✅ Allure Reports container rebuilt and started"
        ;;
    "help"|*)
        echo "Allure Reports Container Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|logs|status|rebuild|help}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the Allure Reports container"
        echo "  stop     - Stop the Allure Reports container"
        echo "  restart  - Restart the Allure Reports container"
        echo "  logs     - Show container logs"
        echo "  status   - Show container status"
        echo "  rebuild  - Rebuild and start the container"
        echo "  help     - Show this help message"
        echo ""
        echo "Access: http://localhost:8080"
        ;;
esac
