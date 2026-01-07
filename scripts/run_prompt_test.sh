#!/bin/bash
# Helper script to run prompt testing in Docker container

# Check if we're already in Docker
if [ -f /.dockerenv ]; then
    # Already in Docker, run directly
    exec python3 /app/scripts/test_prompt_with_models.py "$@"
else
    # Check if Docker container is running
    if ! docker ps | grep -q cti_workflow_worker; then
        echo "ERROR: cti_workflow_worker container is not running."
        echo "Please start the Docker containers first."
        exit 1
    fi
    
    # Copy script to container if it doesn't exist or is newer
    docker cp scripts/test_prompt_with_models.py cti_workflow_worker:/app/scripts/ 2>/dev/null || true
    
    # Run in Docker container (use -i only if stdin is a TTY, otherwise non-interactive)
    if [ -t 0 ]; then
        docker exec -it cti_workflow_worker python3 /app/scripts/test_prompt_with_models.py "$@"
    else
        docker exec cti_workflow_worker python3 /app/scripts/test_prompt_with_models.py "$@"
    fi
fi

