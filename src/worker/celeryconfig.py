"""
Celery Configuration for CTI Scraper

Configures Redis as the message broker and result backend.
"""

import os

# Broker settings
broker_url = os.getenv('REDIS_URL', 'redis://:cti_redis_2024@redis:6379/0')
result_backend = os.getenv('REDIS_URL', 'redis://:cti_redis_2024@redis:6379/0')

# Task settings
task_serializer = 'json'
accept_content = ['json']
result_serializer = 'json'
timezone = 'UTC'
enable_utc = True

# Worker settings
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 1000
worker_disable_rate_limits = False

# Task routing
task_routes = {
    'src.worker.celery_app.check_all_sources': {'queue': 'source_checks'},
    'src.worker.celery_app.check_tier1_sources': {'queue': 'priority_checks'},
    'src.worker.celery_app.cleanup_old_data': {'queue': 'maintenance'},
    'src.worker.celery_app.generate_daily_report': {'queue': 'reports'},
    'src.worker.celery_app.test_source_connectivity': {'queue': 'connectivity'},
    'src.worker.celery_app.collect_from_source': {'queue': 'collection'},
}

# Queue definitions
task_default_queue = 'default'
task_queues = {
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
    },
    'source_checks': {
        'exchange': 'source_checks',
        'routing_key': 'source_checks',
    },
    'priority_checks': {
        'exchange': 'priority_checks',
        'routing_key': 'priority_checks',
    },
    'maintenance': {
        'exchange': 'maintenance',
        'routing_key': 'maintenance',
    },
    'reports': {
        'exchange': 'reports',
        'routing_key': 'reports',
    },
    'connectivity': {
        'exchange': 'connectivity',
        'routing_key': 'connectivity',
    },
    'collection': {
        'exchange': 'collection',
        'routing_key': 'collection',
    },
}

# Task execution settings
task_always_eager = False
task_eager_propagates = True
task_ignore_result = False
task_store_errors_even_if_ignored = True

# Result backend settings
result_expires = 3600  # 1 hour
result_persistent = True

# Monitoring
worker_send_task_events = True
task_send_sent_event = True

# Logging
worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s'

# Security
worker_direct = False
worker_redirect_stdouts = True
worker_redirect_stdouts_level = 'INFO'

# Performance
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 1000
worker_disable_rate_limits = False

# Error handling
task_acks_late = True
task_reject_on_worker_lost = True
task_remote_tracebacks = True
