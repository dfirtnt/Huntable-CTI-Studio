#!/bin/bash
# Helper script to run prompt testing in Docker container

# Check if we're already in Docker
if [ -f /.dockerenv ]; then
    # Already in Docker, run directly
    exec python3 /app/scripts/test_prompt_with_models.py "$@"
else
    # Run in Docker container
    docker exec -it cti_workflow_worker python3 /app/scripts/test_prompt_with_models.py "$@"
fi

