#!/bin/bash
# CTI-to-Hunt Quick Script

echo "🚀 CTI-to-Hunt with Fine-tuned Model"
echo "====================================="
echo ""

if [ $# -eq 0 ]; then
    echo "Usage: $0 \"your threat intelligence text here\""
    echo ""
    echo "Examples:"
    echo "  $0 \"PowerShell malware with encoded commands\""
    echo "  $0 \"Malware drops files in C:\\Windows\\Temp\""
    echo "  $0 \"Suspicious DNS queries to evil-c2.com\""
    exit 1
fi

echo "🔍 Analyzing: $1"
echo ""

# Generate SIGMA rules
ollama run phi3-cti-hunt "$1"

echo ""
echo "✅ SIGMA rules generated!"
echo "💡 Copy the rules above for your detection engineering workflow"
