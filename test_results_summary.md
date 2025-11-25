# Test Execution Summary

**Date**: 2025-11-25 15:08:29

**Total Duration**: 53.88s

## Summary

- **Passed**: 253
- **Failed**: 136
- **Skipped**: 121
- **Errors**: 745
- **Groups Run**: 1
- **Groups Passed**: 0
- **Groups Failed**: 1

## Group Results

| Group | Status | Passed | Failed | Skipped | Errors | Duration |
|-------|--------|--------|--------|----------|--------|----------|
| smoke | ❌ FAIL | 253 | 136 | 121 | 745 | 53.61s |

## Broken Tests

### tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_navigation_menu

**Reason**: FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_sources_page FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_articles_page

### tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_sources_page

**Reason**: FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_articles_page FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_responsive_design

### tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_articles_page

**Reason**: FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_responsive_design FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_accessibility

### tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_responsive_design

**Reason**: FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_accessibility FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_source_management

### tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_accessibility

**Reason**: FAILED tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_source_management FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_switchin

### tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_source_management

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_switching_chatgpt_to_anthropic FAILED tests/integration/test_ai_cross_model_integration.py::TestAIC

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_switching_chatgpt_to_anthropic

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_switching_anthropic_to_ollama FAILED tests/integration/test_ai_cross_model_integration.py::TestAICr

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_switching_anthropic_to_ollama

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_fallback_openai_failure FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossMod

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_fallback_openai_failure

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_fallback_anthropic_failure FAILED tests/integration/test_ai_cross_model_integration.py::TestAICross

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_fallback_anthropic_failure

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_fallback_ollama_failure FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossMod

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_fallback_ollama_failure

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_content_size_limits_per_model FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossMod

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_content_size_limits_per_model

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_specific_feature_support FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossMo

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_specific_feature_support

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_concurrent_model_requests FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIn

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_concurrent_model_requests

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_performance_comparison FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossMode

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_performance_comparison

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_configuration_validation FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossMo

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_configuration_validation

**Reason**: FAILED tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_error_handling_consistency FAILED tests/integration/test_ai_real_api_integration.py::TestAIRealAPII

### tests/integration/test_ai_cross_model_integration.py::TestAICrossModelIntegration::test_model_error_handling_consistency

**Reason**: FAILED tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_ollama_real_api_call FAILED tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_i

### tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_ollama_real_api_call

**Reason**: FAILED tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_ioc_extractor_real_integration FAILED tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegrati

### tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_ioc_extractor_real_integration

**Reason**: FAILED tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_api_error_response_handling FAILED tests/integration/test_lightweight_integration.py::TestDataIngestionPipeline

### tests/integration/test_ai_real_api_integration.py::TestAIRealAPIIntegration::test_api_error_response_handling

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestDataIngestionPipeline::test_rss_to_database_flow FAILED tests/integration/test_lightweight_integration.py::TestDataIngestionPipeline::test

### tests/integration/test_lightweight_integration.py::TestDataIngestionPipeline::test_rss_to_database_flow

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestDataIngestionPipeline::test_content_processing_pipeline FAILED tests/integration/test_lightweight_integration.py::TestContentAnalysisPipel

### tests/integration/test_lightweight_integration.py::TestDataIngestionPipeline::test_content_processing_pipeline

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestContentAnalysisPipeline::test_article_quality_filtering FAILED tests/integration/test_lightweight_integration.py::TestContentAnalysisPipel

### tests/integration/test_lightweight_integration.py::TestContentAnalysisPipeline::test_article_quality_filtering

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestContentAnalysisPipeline::test_analysis_dashboard_data_aggregation FAILED tests/integration/test_lightweight_integration.py::TestSourceMana

### tests/integration/test_lightweight_integration.py::TestContentAnalysisPipeline::test_analysis_dashboard_data_aggregation

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestSourceManagementPipeline::test_source_config_loading FAILED tests/integration/test_lightweight_integration.py::TestSourceManagementPipelin

### tests/integration/test_lightweight_integration.py::TestSourceManagementPipeline::test_source_config_loading

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestSourceManagementPipeline::test_source_health_monitoring FAILED tests/integration/test_lightweight_integration.py::TestCriticalPathIntegrat

### tests/integration/test_lightweight_integration.py::TestSourceManagementPipeline::test_source_health_monitoring

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestCriticalPathIntegration::test_complete_data_flow FAILED tests/integration/test_lightweight_integration.py::TestCriticalPathIntegration::te

### tests/integration/test_lightweight_integration.py::TestCriticalPathIntegration::test_complete_data_flow

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestCriticalPathIntegration::test_error_handling_and_recovery FAILED tests/integration/test_lightweight_integration.py::TestPerformanceCritica

### tests/integration/test_lightweight_integration.py::TestCriticalPathIntegration::test_error_handling_and_recovery

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestPerformanceCriticalPaths::test_concurrent_article_processing FAILED tests/integration/test_lightweight_integration.py::TestPerformanceCrit

### tests/integration/test_lightweight_integration.py::TestPerformanceCriticalPaths::test_concurrent_article_processing

**Reason**: FAILED tests/integration/test_lightweight_integration.py::TestPerformanceCriticalPaths::test_memory_efficient_processing FAILED tests/test_content_filter.py::TestContentFilter::test_filter_articles_ba

### tests/integration/test_lightweight_integration.py::TestPerformanceCriticalPaths::test_memory_efficient_processing

**Reason**: FAILED tests/test_content_filter.py::TestContentFilter::test_filter_articles_batch FAILED tests/test_corruption_stats.py::test_get_corruption_stats - RuntimeErr...

### tests/test_content_filter.py::TestContentFilter::test_filter_articles_batch

**Reason**: FAILED tests/test_corruption_stats.py::test_get_corruption_stats - RuntimeErr... FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_source

### tests/test_corruption_stats.py::test_get_corruption_stats

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_source FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_source_by_id

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_source

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_source_by_id FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_source

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_source_by_id

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_source FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_source

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_source

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_source FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_sources

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_source

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_sources FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_article

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_sources

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_article FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_article_by_id

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_article

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_article_by_id FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_article

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_article_by_id

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_article FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_article

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_article

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_article FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_articles

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_article

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_articles FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_annotation

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_articles

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_annotation FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_annotation_by_id

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_create_annotation

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_annotation_by_id FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_annotation

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_annotation_by_id

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_annotation FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_annotation

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_update_annotation

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_annotation FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_annotations

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_delete_annotation

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_annotations FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_articles_by_source

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_list_annotations

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_articles_by_source FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_annotations_by_article

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_articles_by_source

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_annotations_by_article FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_search_articles

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_annotations_by_article

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_search_articles FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_article_statistics

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_search_articles

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_article_statistics FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_bulk_create_articles

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_article_statistics

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_bulk_create_articles FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_bulk_update_articles

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_bulk_create_articles

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_bulk_update_articles FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_cleanup_old_articles

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_bulk_update_articles

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_cleanup_old_articles FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_database_health

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_cleanup_old_articles

**Reason**: FAILED tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_database_health FAILED tests/test_gpt4o_endpoint.py::TestGPT4oOptimizedEndpoint::test_api_gpt4o_rank_optimized_article_not_

### tests/test_database_operations.py::TestAsyncDatabaseManager::test_get_database_health

**Reason**: FAILED tests/test_gpt4o_endpoint.py::TestGPT4oOptimizedEndpoint::test_api_gpt4o_rank_optimized_article_not_found FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_init_with_model_path

### tests/test_gpt4o_endpoint.py::TestGPT4oOptimizedEndpoint::test_api_gpt4o_rank_optimized_article_not_found

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_init_with_model_path FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_success

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_init_with_model_path

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_success FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_custom_parameters

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_success

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_custom_parameters FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_filtering_failure

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_custom_parameters

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_filtering_failure FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_model_not_loaded

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_filtering_failure

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_model_not_loaded FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_model_already_loaded

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_model_not_loaded

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_model_already_loaded FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_get_optimization_stats_with_data

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_model_already_loaded

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_get_optimization_stats_with_data FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_stats_update

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_get_optimization_stats_with_data

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_stats_update FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_large_content

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_stats_update

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_large_content FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_empty_content

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_large_content

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_empty_content FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizerIntegration::test_end_to_end_optimization

### tests/test_gpt4o_optimizer.py::TestLLMOptimizer::test_optimize_content_empty_content

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizerIntegration::test_end_to_end_optimization FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizerIntegration::test_multiple_optimizations

### tests/test_gpt4o_optimizer.py::TestLLMOptimizerIntegration::test_end_to_end_optimization

**Reason**: FAILED tests/test_gpt4o_optimizer.py::TestLLMOptimizerIntegration::test_multiple_optimizations FAILED tests/test_http_client.py::TestRateLimiter::test_wait_for_token - Runt...

### tests/test_gpt4o_optimizer.py::TestLLMOptimizerIntegration::test_multiple_optimizations

**Reason**: FAILED tests/test_http_client.py::TestRateLimiter::test_wait_for_token - Runt... FAILED tests/test_http_client.py::TestHTTPClient::test_get_success - RuntimeE...

### tests/test_http_client.py::TestRateLimiter::test_wait_for_token

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_get_success - RuntimeE... FAILED tests/test_http_client.py::TestHTTPClient::test_get_with_headers - Run...

### tests/test_http_client.py::TestHTTPClient::test_get_success

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_get_with_headers - Run... FAILED tests/test_http_client.py::TestHTTPClient::test_get_with_params - Runt...

### tests/test_http_client.py::TestHTTPClient::test_get_with_headers

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_get_with_params - Runt... FAILED tests/test_http_client.py::TestHTTPClient::test_post_success - Runtime...

### tests/test_http_client.py::TestHTTPClient::test_get_with_params

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_post_success - Runtime... FAILED tests/test_http_client.py::TestHTTPClient::test_post_with_json - Runti...

### tests/test_http_client.py::TestHTTPClient::test_post_success

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_post_with_json - Runti... FAILED tests/test_http_client.py::TestHTTPClient::test_put_success - RuntimeE...

### tests/test_http_client.py::TestHTTPClient::test_post_with_json

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_put_success - RuntimeE... FAILED tests/test_http_client.py::TestHTTPClient::test_delete_success - Runti...

### tests/test_http_client.py::TestHTTPClient::test_put_success

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_delete_success - Runti... FAILED tests/test_http_client.py::TestHTTPClient::test_head_success - Runtime...

### tests/test_http_client.py::TestHTTPClient::test_delete_success

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_head_success - Runtime... FAILED tests/test_http_client.py::TestHTTPClient::test_request_with_retry - R...

### tests/test_http_client.py::TestHTTPClient::test_head_success

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_request_with_retry - R... FAILED tests/test_http_client.py::TestHTTPClient::test_request_with_rate_limiting

### tests/test_http_client.py::TestHTTPClient::test_request_with_retry

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_request_with_rate_limiting FAILED tests/test_http_client.py::TestHTTPClient::test_request_timeout - Runt...

### tests/test_http_client.py::TestHTTPClient::test_request_with_rate_limiting

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_request_timeout - Runt... FAILED tests/test_http_client.py::TestHTTPClient::test_request_connection_error

### tests/test_http_client.py::TestHTTPClient::test_request_timeout

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_request_connection_error FAILED tests/test_http_client.py::TestHTTPClient::test_http_client_performance

### tests/test_http_client.py::TestHTTPClient::test_request_connection_error

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_http_client_performance FAILED tests/test_http_client.py::TestHTTPClient::test_http_client_edge_cases

### tests/test_http_client.py::TestHTTPClient::test_http_client_performance

**Reason**: FAILED tests/test_http_client.py::TestHTTPClient::test_http_client_edge_cases FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_raw_iocs

### tests/test_http_client.py::TestHTTPClient::test_http_client_edge_cases

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_raw_iocs FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_without_llm

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_raw_iocs

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_without_llm FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_with_llm_validation

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_without_llm

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_with_llm_validation FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_empty_content

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_with_llm_validation

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_empty_content FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_no_iocs_found

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_empty_content

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_no_iocs_found FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_validate_with_llm_success

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_no_iocs_found

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_validate_with_llm_success FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_validate_with_llm_failure

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_validate_with_llm_success

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_validate_with_llm_failure FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_performance

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_validate_with_llm_failure

**Reason**: FAILED tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_performance FAILED tests/test_ioc_extractor.py::TestIOCExtractorIntegration::test_ioc_extraction_api_endpoint

### tests/test_ioc_extractor.py::TestHybridIOCExtractor::test_extract_iocs_performance

**Reason**: FAILED tests/test_ioc_extractor.py::TestIOCExtractorIntegration::test_ioc_extraction_api_endpoint FAILED tests/test_ioc_extractor.py::TestIOCExtractorIntegration::test_ioc_extraction_with_database_upd

### tests/test_ioc_extractor.py::TestIOCExtractorIntegration::test_ioc_extraction_api_endpoint

**Reason**: FAILED tests/test_ioc_extractor.py::TestIOCExtractorIntegration::test_ioc_extraction_with_database_update FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_listing_strategy

### tests/test_ioc_extractor.py::TestIOCExtractorIntegration::test_ioc_extraction_with_database_update

**Reason**: FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_listing_strategy FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_sitemap_strategy

### tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_listing_strategy

**Reason**: FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_sitemap_strategy FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_no_strategies

### tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_sitemap_strategy

**Reason**: FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_no_strategies FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_strategy_failure

### tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_no_strategies

**Reason**: FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_strategy_failure FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_scope_filtering

### tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_strategy_failure

**Reason**: FAILED tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_scope_filtering FAILED tests/test_modern_scraper.py::TestStructuredDataExtractor::test_extract_from_jsonld_minimal

### tests/test_modern_scraper.py::TestURLDiscovery::test_discover_urls_scope_filtering

**Reason**: FAILED tests/test_modern_scraper.py::TestStructuredDataExtractor::test_extract_from_jsonld_minimal FAILED tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_success

### tests/test_modern_scraper.py::TestStructuredDataExtractor::test_extract_from_jsonld_minimal

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_success FAILED tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_no_urls

### tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_success

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_no_urls FAILED tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_extraction_failure

### tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_no_urls

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_extraction_failure FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_success

### tests/test_modern_scraper.py::TestModernScraper::test_scrape_source_extraction_failure

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_success FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_not_modified

### tests/test_modern_scraper.py::TestModernScraper::test_extract_article_success

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_not_modified FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_http_error

### tests/test_modern_scraper.py::TestModernScraper::test_extract_article_not_modified

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_http_error FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_jsonld_preference

### tests/test_modern_scraper.py::TestModernScraper::test_extract_article_http_error

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_article_jsonld_preference FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_with_selectors_basic

### tests/test_modern_scraper.py::TestModernScraper::test_extract_article_jsonld_preference

**Reason**: FAILED tests/test_modern_scraper.py::TestModernScraper::test_extract_with_selectors_basic FAILED tests/test_modern_scraper.py::TestLegacyScraper::test_scrape_source_success

### tests/test_modern_scraper.py::TestModernScraper::test_extract_with_selectors_basic

**Reason**: FAILED tests/test_modern_scraper.py::TestLegacyScraper::test_scrape_source_success FAILED tests/test_modern_scraper.py::TestLegacyScraper::test_scrape_source_http_error

### tests/test_modern_scraper.py::TestLegacyScraper::test_scrape_source_success

**Reason**: FAILED tests/test_modern_scraper.py::TestLegacyScraper::test_scrape_source_http_error FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_success - Run...

### tests/test_modern_scraper.py::TestLegacyScraper::test_scrape_source_http_error

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_success - Run... FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_no_rss_url - ...

### tests/test_rss_parser.py::TestRSSParser::test_parse_feed_success

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_no_rss_url - ... FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_http_error - ...

### tests/test_rss_parser.py::TestRSSParser::test_parse_feed_no_rss_url

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_http_error - ... FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_bozo_warning

### tests/test_rss_parser.py::TestRSSParser::test_parse_feed_http_error

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_feed_bozo_warning FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_success - Ru...

### tests/test_rss_parser.py::TestRSSParser::test_parse_feed_bozo_warning

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_success - Ru... FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_missing_title

### tests/test_rss_parser.py::TestRSSParser::test_parse_entry_success

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_missing_title FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_missing_url

### tests/test_rss_parser.py::TestRSSParser::test_parse_entry_missing_title

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_missing_url FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_filtered_title

### tests/test_rss_parser.py::TestRSSParser::test_parse_entry_missing_url

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_filtered_title FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_no_content

### tests/test_rss_parser.py::TestRSSParser::test_parse_entry_filtered_title

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_parse_entry_no_content FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_published

### tests/test_rss_parser.py::TestRSSParser::test_parse_entry_no_content

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_published FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_parsed

### tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_published

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_parsed FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_page

### tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_parsed

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_page FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_from_feed

### tests/test_rss_parser.py::TestRSSParser::test_extract_date_from_page

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_from_feed FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_rss_only_mode

### tests/test_rss_parser.py::TestRSSParser::test_extract_content_from_feed

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_rss_only_mode FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_modern_scraping_fallback

### tests/test_rss_parser.py::TestRSSParser::test_extract_content_rss_only_mode

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_modern_scraping_fallback FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_red_canary_skip

### tests/test_rss_parser.py::TestRSSParser::test_extract_content_modern_scraping_fallback

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_red_canary_skip FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_hacker_news_modern_scraping

### tests/test_rss_parser.py::TestRSSParser::test_extract_content_red_canary_skip

**Reason**: FAILED tests/test_rss_parser.py::TestRSSParser::test_extract_content_hacker_news_modern_scraping FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_success

### tests/test_rss_parser.py::TestRSSParser::test_extract_content_hacker_news_modern_scraping

**Reason**: FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_success FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_bozo_warning

### tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_success

**Reason**: FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_bozo_warning FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_no_entries

### tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_bozo_warning

**Reason**: FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_no_entries FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_invalid_entries

### tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_no_entries

**Reason**: FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_invalid_entries FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_http_error

### tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_invalid_entries

**Reason**: FAILED tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_http_error FAILED tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_score_threat_hunting_content_intelligence_in

### tests/test_rss_parser.py::TestFeedValidator::test_validate_feed_http_error

**Reason**: FAILED tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_score_threat_hunting_content_intelligence_indicators FAILED tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test

### tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_score_threat_hunting_content_intelligence_indicators

**Reason**: FAILED tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_keyword_matches_regex_escape FAILED tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_score_threat_hunting_co

### tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_keyword_matches_regex_escape

**Reason**: FAILED tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_score_threat_hunting_content_realistic_example FAILED tests/test_utils.py::TestContentFilter::test_quality_scoring - assert ..

### tests/test_threat_hunting_scorer.py::TestThreatHuntingScorer::test_score_threat_hunting_content_realistic_example

**Reason**: FAILED tests/test_utils.py::TestContentFilter::test_quality_scoring - assert ... FAILED tests/ui/test_prompt_sync_ui.py::TestPromptSynchronization::test_sigma_help_matches_sigma_generation_prompt

### tests/test_utils.py::TestContentFilter::test_quality_scoring

**Reason**: FAILED tests/ui/test_prompt_sync_ui.py::TestPromptSynchronization::test_sigma_help_matches_sigma_generation_prompt ERROR tests/api/test_annotations_api.py::TestCreateAnnotation::test_create_annotation

### tests/ui/test_prompt_sync_ui.py::TestPromptSynchronization::test_sigma_help_matches_sigma_generation_prompt

**Reason**: ERROR tests/api/test_annotations_api.py::TestCreateAnnotation::test_create_annotation_success ERROR tests/api/test_annotations_api.py::TestCreateAnnotation::test_create_annotation_text_too_short

