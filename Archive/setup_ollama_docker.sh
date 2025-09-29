#!/bin/bash

echo "============================================================"
echo "🤖 Setting up Ollama with GPT OSS 20B in Docker"
echo "============================================================"
echo

# Start Ollama container
echo "🚀 Starting Ollama container..."
docker-compose up -d ollama

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
sleep 30

# Check if Ollama is running
echo "🔍 Checking Ollama status..."
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "✅ Ollama is running and accessible"
else
    echo "❌ Ollama is not responding. Please check the container logs:"
    echo "   docker logs cti_ollama"
    exit 1
fi

# Download GPT OSS 20B model
echo "📥 Downloading GPT OSS 20B model..."
echo "⚠️  This will take a while (several GB download)..."
echo "💡 You can monitor progress with: docker logs -f cti_ollama"
echo

# Pull the model
docker exec cti_ollama ollama pull gpt-oss:20b

if [ $? -eq 0 ]; then
    echo "✅ GPT OSS 20B model downloaded successfully"
else
    echo "❌ Failed to download GPT OSS 20B model"
    echo "💡 Check the logs: docker logs cti_ollama"
    exit 1
fi

# Test the model
echo "🧪 Testing GPT OSS 20B model..."
docker exec cti_ollama ollama run gpt-oss:20b "Hello! Can you confirm you're working?" > /tmp/test_response.txt

if [ $? -eq 0 ]; then
    echo "✅ GPT OSS 20B model is working correctly"
    echo "📝 Test response preview:"
    head -3 /tmp/test_response.txt
    rm /tmp/test_response.txt
else
    echo "❌ GPT OSS 20B model test failed"
    exit 1
fi

echo
echo "============================================================"
echo "🎉 Setup Complete! GPT OSS 20B is ready to use"
echo "============================================================"
echo
echo "🌐 Access your chatbot at: http://localhost:8000/chat"
echo
echo "📊 Monitor Ollama:"
echo "   • Container logs: docker logs cti_ollama"
echo "   • Model list: docker exec cti_ollama ollama list"
echo "   • API status: curl http://localhost:11434/api/tags"
echo
echo "🔧 Useful commands:"
echo "   • Restart Ollama: docker-compose restart ollama"
echo "   • Stop Ollama: docker-compose stop ollama"
echo "   • Remove model: docker exec cti_ollama ollama rm gpt-oss:20b"
echo
