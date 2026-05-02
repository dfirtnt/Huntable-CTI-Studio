"""
Vulture whitelist for known false positives.

Add symbols here that Vulture incorrectly reports as dead code but are
actually used (e.g., via dynamic dispatch, reflection, or external config).
See: https://github.com/jendrikseipp/vulture#handling-false-positives
"""

# pytest fixtures -- injected by parameter name, not called directly in test body
ensure_workflow_config_schema
seed_workflow_execution
mock_empty_db
sample_threat_article
mock_source_config
mock_inference_class
test_database_session
mock_sigma_queue_list

# pytest hook params -- required by hook signature, intentionally unused in body
exitstatus
nextitem

# mock params -- match subprocess.run signature, intentionally unused in mock body
capture_output

# deprecated stub params -- run_ai_tests.py is kept for reference only; params accepted but ignored
test_type
