#!/bin/bash

# Allure Reports Container Management Script

set -e

case "${1:-help}" in
    "start")
        echo "🚀 Starting Allure Reports container..."
        docker-compose -f docker-compose.allure.yml up -d
        echo "✅ Allure Reports available at: http://localhost:8080"
        ;;
    "stop")
        echo "🛑 Stopping Allure Reports container..."
        docker-compose -f docker-compose.allure.yml down
        echo "✅ Allure Reports container stopped"
        ;;
    "restart")
        echo "🔄 Restarting Allure Reports container..."
        docker-compose -f docker-compose.allure.yml restart
        echo "✅ Allure Reports container restarted"
        ;;
    "logs")
        echo "📋 Showing Allure Reports container logs..."
        docker-compose -f docker-compose.allure.yml logs -f
        ;;
    "status")
        echo "📊 Allure Reports container status:"
        docker ps | grep allure || echo "❌ Container not running"
        ;;
    "rebuild")
        echo "🔨 Rebuilding Allure Reports container..."
        docker-compose -f docker-compose.allure.yml down
        docker-compose -f docker-compose.allure.yml build --no-cache
        docker-compose -f docker-compose.allure.yml up -d
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
