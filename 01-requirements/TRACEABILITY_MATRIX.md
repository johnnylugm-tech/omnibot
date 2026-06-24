# TRACEABILITY_MATRIX — OmniBot 需求可追溯矩陣

> **Source**: SRS.md (Approved Round 2) + SPEC_TRACKING.md (Approved)
> **Authored**: 2026-06-17 — Agent A: REQUIREMENTS_ENGINEER
> **Project**: omnibot
> **Phase**: 1
> **Direction**: FR → SRS Section → Design Component → Test Function(s)

---

## 說明

Phase 1 建立前向可追溯性（Forward Traceability）：每個 FR 連結至：
1. **SRS 章節**（上游）
2. **設計元件**（下游 Phase 2/3 — 以 SRS.md 中的 Implementation Function 為佔位符）
3. **測試函數名稱**（下游 Phase 3 — 以 `test_frNN_xxx` 命名規範定義）

Phase 2 補充：實際程式碼路徑（檔案:行號）。
Phase 3 補充：實際測試通過狀態。

---

## 雙向追溯矩陣

### Module 1: Platform Adapter Layer

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-01 | SRS §2 Module 1 | `TelegramWebhookVerifier.verify()`, `telegram_adapter` | `test_fr01_telegram_webhook_valid_signature`, `test_fr01_telegram_webhook_invalid_signature_401`, `test_fr01_telegram_rate_limit_429` | Pending |
| FR-02 | SRS §2 Module 1 | `LineWebhookVerifier.verify()`, `line_adapter` | `test_fr02_line_webhook_valid_signature`, `test_fr02_line_webhook_invalid_signature_401` | Pending |
| FR-03 | SRS §2 Module 1 | `MessengerWebhookVerifier.verify()`, `messenger_adapter` | `test_fr03_messenger_hub_challenge_returns_challenge`, `test_fr03_messenger_webhook_valid_post_200` | Pending |
| FR-04 | SRS §2 Module 1 | `WhatsAppWebhookVerifier.verify()`, `whatsapp_adapter` | `test_fr04_whatsapp_hub_challenge_returns_challenge`, `test_fr04_whatsapp_invalid_sha256_prefix_401` | Pending |
| FR-05 | SRS §2 Module 1 | `WebAdapter`, `jwt_middleware` | `test_fr05_web_guest_session_returns_jwt`, `test_fr05_web_message_invalid_jwt_401`, `test_fr05_web_message_rate_limit_429` | Pending |
| FR-06 | SRS §2 Module 1 | `A2AAdapter`, `m2m_auth_middleware` | `test_fr06_a2a_valid_m2m_token_200`, `test_fr06_a2a_invalid_m2m_token_401` | Pending |
| FR-07 | SRS §2 Module 1 | `UnifiedMessage` dataclass | `test_fr07_unified_message_telegram_valid`, `test_fr07_unified_message_frozen_immutable` | Pending |
| FR-08 | SRS §2 Module 1 | `UnifiedResponse` dataclass | `test_fr08_unified_response_source_enum_valid`, `test_fr08_unified_response_invalid_source_raises` | Pending |
| FR-09 | SRS §2 Module 1 | `ApiResponse`, `PaginatedResponse` | `test_fr09_api_response_schema_valid`, `test_fr09_paginated_response_has_next_field` | Pending |

### Module 2: Security — PALADIN 五層防禦

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-10 | SRS §2 Module 2 | `InputSanitizer.sanitize()` | `test_fr10_cyrillic_homoglyph_normalized`, `test_fr10_greek_homoglyph_normalized`, `test_fr10_nfkc_normalization_passes`, `test_fr10_control_char_removed`, `test_fr10_latency_under_2ms` | Pending |
| FR-11 | SRS §2 Module 2 | `PromptInjectionDefense.check_input()` | `test_fr11_ignore_previous_instructions_detected`, `test_fr11_system_prefix_detected`, `test_fr11_normal_message_not_flagged`, `test_fr11_latency_under_3ms` | Pending |
| FR-12 | SRS §2 Module 2 | `PromptInjectionDefense.build_sandwich_prompt()` | `test_fr12_sandwich_has_priority_highest_marker`, `test_fr12_sandwich_has_untrusted_boundary`, `test_fr12_l1_l3_combined_under_5ms` | Pending |
| FR-13 | SRS §2 Module 2 | `SemanticInjectionClassifier.classify()` | `test_fr13_classifier_returns_valid_json`, `test_fr13_timeout_returns_unverified_passthrough`, `test_fr13_injection_type_enum_four_values`, `test_fr13_latency_under_200ms` | Pending |
| FR-14 | SRS §2 Module 2 | `GroundingChecker.check()` | `test_fr14_cosine_below_075_grounded_false`, `test_fr14_cosine_above_075_grounded_true`, `test_fr14_no_source_texts_grounded_false`, `test_fr14_latency_under_5ms` | Pending |
| FR-15 | SRS §2 Module 2 | `PALADINPipeline.process()` | `test_fr15_low_risk_skips_l4`, `test_fr15_medium_risk_l4_parallel_l3`, `test_fr15_high_risk_l4_sync_blocks_l3` | Pending |
| FR-16 | SRS §2 Module 2 | `PALADINPipeline.process()` | `test_fr16_retrospective_block_event_in_security_logs`, `test_fr16_l3_result_revoked_on_late_injection` | Pending |
| FR-17 | SRS §2 Module 2 | platform-specific retraction handlers | `test_fr17_telegram_retraction_within_48hr`, `test_fr17_telegram_window_expired_sends_apology`, `test_fr17_messenger_retraction_within_10min`, `test_fr17_web_ws_replace_response`, `test_fr17_a2a_revoked_true`, `test_fr17_retraction_failed_logged` | Pending |

### Module 3: PII 去識別化

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-18 | SRS §2 Module 3 | `PIIMasking.mask()` | `test_fr18_phone_tw_format_masked`, `test_fr18_email_masked`, `test_fr18_tw_address_masked`, `test_fr18_credit_card_luhn_valid_masked`, `test_fr18_credit_card_luhn_invalid_not_masked`, `test_fr18_mask_count_correct` | Pending |
| FR-19 | SRS §2 Module 3 | `PIIMasking.should_escalate()` | `test_fr19_password_keyword_triggers_escalate`, `test_fr19_bank_account_triggers_escalate`, `test_fr19_credit_card_keyword_triggers_escalate`, `test_fr19_debit_card_triggers_escalate`, `test_fr19_normal_text_no_escalate` | Pending |
| FR-20 | SRS §2 Module 3 | `pii_audit_log` table, retention job | `test_fr20_mask_event_writes_audit_log`, `test_fr20_audit_log_has_conversation_id`, `test_fr20_90day_anonymize_scheduled` | Pending |

### Module 4: Rate Limiting & IP Whitelist

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-21 | SRS §2 Module 4 | `RateLimiter.allow()` | `test_fr21_telegram_over_30rps_returns_429`, `test_fr21_web_over_10rps_returns_429`, `test_fr21_agent_over_100rps_returns_429`, `test_fr21_lua_atomic_no_race_condition` | Pending |
| FR-22 | SRS §2 Module 4 | `RateLimiter.allow()` | `test_fr22_redis_connection_error_passthrough`, `test_fr22_redis_timeout_passthrough`, `test_fr22_failopen_warning_logged` | Pending |
| FR-23 | SRS §2 Module 4 | `IPWhitelist.is_allowed()` | `test_fr23_whitelisted_ip_passes`, `test_fr23_nonwhitelisted_ip_403_empty_body`, `test_fr23_x_forwarded_for_leftmost_used`, `test_fr23_empty_whitelist_400_warning` | Pending |
| FR-24 | SRS §2 Module 4 | middleware chain | `test_fr24_ip_block_before_signature_validation`, `test_fr24_rate_limit_after_platform_parse` | Pending |
| FR-25 | SRS §2 Module 4 | `IPWhitelist.__init__()`, `IPWhitelist.is_allowed()` | `test_fr25_invalid_cidr_raises_IPWhitelistError_at_startup`, `test_fr25_invalid_ip_returns_false_no_exception` | Pending |

### Module 5: Hybrid Knowledge Layer

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-26 | SRS §2 Module 5 | `HybridKnowledge._rule_match()` | `test_fr26_exact_match_confidence_095_returns_rule`, `test_fr26_confidence_below_080_falls_through_tier2`, `test_fr26_limit_5_applied` | Pending |
| FR-27 | SRS §2 Module 5 | `HybridKnowledge._rag_search()`, `_reciprocal_rank_fusion()` | `test_fr27_rrf_k60_ranking_correct`, `test_fr27_confidence_above_085_returns_rag`, `test_fr27_parent_child_lookup_correct`, `test_fr27_recall_at_3_above_92_percent` | Pending |
| FR-28 | SRS §2 Module 5 | chunking module, `knowledge_chunks` table | `test_fr28_parent_500_token_size`, `test_fr28_child_150_token_size`, `test_fr28_child_vector_indexed_parent_not`, `test_fr28_vector_hit_child_retrieves_parent` | Pending |
| FR-29 | SRS §2 Module 5 | `CREATE INDEX ... USING hnsw` | `test_fr29_hnsw_index_created_m16_ef64`, `test_fr29_partial_index_null_excluded` | Pending |
| FR-30 | SRS §2 Module 5 | `HybridKnowledge._llm_generate()`, `_call_llm_api()` | `test_fr30_gpt4o_failure_triggers_gemini_fallback`, `test_fr30_grounding_below_075_escalates`, `test_fr30_fallback_switch_under_500ms` | Pending |
| FR-31 | SRS §2 Module 5 | `HybridKnowledge._escalate()` | `test_fr31_t1_t3_no_match_triggers_escalate`, `test_fr31_escalate_id_minus1`, `test_fr31_reason_enum_valid_values` | Pending |
| FR-32 | SRS §2 Module 5 | `KnowledgeResult` dataclass | `test_fr32_knowledge_result_frozen`, `test_fr32_source_enum_four_values`, `test_fr32_id_minus1_non_kb_marker` | Pending |
| FR-33 | SRS §2 Module 5 | `HybridKnowledge.query()` | `test_fr33_query_t1_first_t4_last_order`, `test_fr33_embedding_dim_1536_constant` | Pending |

### Module 6: DST 對話狀態追蹤

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-34 | SRS §2 Module 6 | `DialogueState.transition()`, `ALLOWED_TRANSITIONS` | `test_fr34_idle_to_intent_detected_valid`, `test_fr34_illegal_transition_raises_valueerror`, `test_fr34_turn_count_increments_per_transition` | Pending |
| FR-35 | SRS §2 Module 6 | `DialogueSlot`, `INTENT_TO_SLOTS`, `DialogueState.missing_slots()` | `test_fr35_order_status_missing_order_id`, `test_fr35_return_request_missing_both_slots`, `test_fr35_all_slots_filled_no_missing` | Pending |
| FR-36 | SRS §2 Module 6 | DST state machine transitions | `test_fr36_slot_filling_3rounds_escalated`, `test_fr36_confidence_below_065_escalated` | Pending |
| FR-37 | SRS §2 Module 6 | DST transitions | `test_fr37_awaiting_2rounds_unconfirmed_escalated`, `test_fr37_confirm_transitions_to_processing`, `test_fr37_deny_transitions_to_slot_filling` | Pending |
| FR-38 | SRS §2 Module 6 | `ContextWindowManager.manage()` | `test_fr38_token_count_uses_cl100k_base`, `test_fr38_overflow_triggers_summary`, `test_fr38_recent_1_3_messages_preserved`, `test_fr38_gemini_fallback_same_budget` | Pending |

### Module 7: Action Execution Engine (Agentic)

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-39 | SRS §2 Module 7 | `ActionAdapter`, `ToolDefinition`, `ToolExecutionResult` | `test_fr39_adapter_implements_list_tools`, `test_fr39_adapter_implements_execute`, `test_fr39_tool_execution_result_has_success_output_error` | Pending |
| FR-40 | SRS §2 Module 7 | `MCPAdapter` | `test_fr40_mcp_adapter_connects_stdio`, `test_fr40_mcp_adapter_connects_sse`, `test_fr40_mcp_tool_call_returns_result` | Pending |
| FR-41 | SRS §2 Module 7 | `A2AAdapter._discover_agent_card()`, `A2AAdapter.execute()` | `test_fr41_agent_card_discovery_caches_300s`, `test_fr41_json_rpc_2_format_correct`, `test_fr41_timeout_2s_returns_error`, `test_fr41_unreachable_returns_empty_tools_no_exception` | Pending |
| FR-42 | SRS §2 Module 7 | `CLIAdapter` | `test_fr42_cli_success_returns_true`, `test_fr42_cli_failure_returns_false_error_message` | Pending |
| FR-43 | SRS §2 Module 7 | `ToolExecutor`, `_get_shipping_status()`, `_update_shipping_address()` | `test_fr43_unknown_tool_returns_false`, `test_fr43_update_address_blocked_when_shipped`, `test_fr43_get_shipping_status_returns_result` | Pending |
| FR-44 | SRS §2 Module 7 | `/.well-known/agent.json` endpoint | `test_fr44_agent_card_endpoint_200`, `test_fr44_agent_card_methods_include_ask_and_escalate` | Pending |
| FR-45 | SRS §2 Module 7 | `ToolDefinition` shared dataclass | `test_fr45_aee_and_dst_share_tool_definition_import` | Pending |

### Module 8: Emotion Analyzer

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-46 | SRS §2 Module 8 | `EmotionScore`, emotion classification | `test_fr46_classify_positive_neutral_negative_enum`, `test_fr46_intensity_in_0_to_1_range` | Pending |
| FR-47 | SRS §2 Module 8 | `EmotionTracker.current_weighted_score()` | `test_fr47_24hr_weight_50_percent_of_current`, `test_fr47_decay_formula_correct` | Pending |
| FR-48 | SRS §2 Module 8 | `EmotionTracker.should_escalate()` | `test_fr48_3_consecutive_negative_triggers`, `test_fr48_non_negative_interrupts_count` | Pending |
| FR-49 | SRS §2 Module 8 | platform check in pipeline | `test_fr49_agent_platform_skips_emotion_module` | Pending |

### Module 9: Response Generator

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-50 | SRS §2 Module 9 | `ResponseGenerator.DEFAULT_TEMPLATES` | `test_fr50_rule_default_template_exists`, `test_fr50_rag_default_has_knowledge_suffix`, `test_fr50_escalate_template_has_case_number` | Pending |
| FR-51 | SRS §2 Module 9 | `ResponseGenerator._apply_emotion_tone()` | `test_fr51_negative_intensity_above_07_apology_prefix`, `test_fr51_positive_adds_positive_prefix`, `test_fr51_repeat_negative_suppresses_apology` | Pending |
| FR-52 | SRS §2 Module 9 | `ResponseGenerator._apply_ab_variant()`, `ABTestManager.get_variant()` | `test_fr52_sha256_deterministic_same_variant_cross_process`, `test_fr52_variant_a_suffix_correct`, `test_fr52_variant_b_suffix_correct`, `test_fr52_control_no_injection` | Pending |
| FR-53 | SRS §2 Module 9 | platform format adapters | `test_fr53_telegram_4096_char_limit`, `test_fr53_line_5000_char_limit`, `test_fr53_messenger_2000_char_truncation`, `test_fr53_agent_pure_json_format` | Pending |

### Module 10: Human Escalation

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-54 | SRS §2 Module 10 | `EscalationManager.create()`, `.assign()`, `.resolve()` | `test_fr54_create_inserts_escalation_queue`, `test_fr54_assign_updates_assigned_agent`, `test_fr54_resolve_sets_resolved_at` | Pending |
| FR-55 | SRS §2 Module 10 | `EscalationManager.SLA_BY_PRIORITY`, `get_sla_breaches()` | `test_fr55_normal_sla_30min`, `test_fr55_high_sla_15min`, `test_fr55_urgent_sla_5min`, `test_fr55_breach_query_correct` | Pending |
| FR-56 | SRS §2 Module 10 | `EscalationManager` + WebSocket push | `test_fr56_escalation_new_ws_event_sent`, `test_fr56_payload_has_all_required_fields` | Pending |

### Module 11: WebSocket 端點

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-57 | SRS §2 Module 11 | `/ws/agent` WebSocket handler | `test_fr57_agent_ws_escalation_new_event`, `test_fr57_agent_ws_invalid_jwt_rejected`, `test_fr57_agent_ws_agent_takeover_event` | Pending |
| FR-58 | SRS §2 Module 11 | `/ws/user` WebSocket handler | `test_fr58_user_ws_message_reply_pushed`, `test_fr58_user_ws_jwt_verified` | Pending |
| FR-59 | SRS §2 Module 11 | WebSocket lifecycle | `test_fr59_ping_sent_every_30s`, `test_fr59_no_pong_within_10s_disconnect`, `test_fr59_subscribe_returns_subscribed` | Pending |

### Module 12: RBAC 權限管理

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-60 | SRS §2 Module 12 | `ROLE_PERMISSIONS` | `test_fr60_7_roles_defined`, `test_fr60_dpo_has_pii_decrypt`, `test_fr60_auditor_lacks_pii_decrypt` | Pending |
| FR-61 | SRS §2 Module 12 | `ROLE_PERMISSIONS` | `test_fr61_auditor_pii_decrypt_returns_403`, `test_fr61_permission_matrix_complete`, `test_fr61_admin_has_all_resources` | Pending |
| FR-62 | SRS §2 Module 12 | `RBACEnforcer.require()`, `check()` | `test_fr62_unauthorized_role_returns_403`, `test_fr62_authorized_role_passes`, `test_fr62_error_code_authz_insufficient_role` | Pending |

### Module 13: A/B Testing

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-63 | SRS §2 Module 13 | `ABTestManager.get_variant()`, `run_experiment()` | `test_fr63_sha256_same_user_same_experiment_same_variant`, `test_fr63_variant_deterministic_cross_process` | Pending |
| FR-64 | SRS §2 Module 13 | `ABTestManager.auto_promote()` | `test_fr64_sample_below_100_returns_none`, `test_fr64_diff_above_005_promotes_best_variant`, `test_fr64_promoted_status_set_completed` | Pending |

### Module 14: LLM-as-a-Judge

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-65 | SRS §2 Module 14 | `LLMJudge.evaluate()` | `test_fr65_two_judges_called_in_parallel`, `test_fr65_temperature_0_in_config` | Pending |
| FR-66 | SRS §2 Module 14 | `LLMJudge.evaluate()` aggregation | `test_fr66_politeness_equals_max_of_both_judges` | Pending |
| FR-67 | SRS §2 Module 14 | `LLMJudge.evaluate()` aggregation | `test_fr67_accuracy_equals_min_of_both_judges` | Pending |
| FR-68 | SRS §2 Module 14 | `LLMJudge.evaluate()` | `test_fr68_csat_formula_04_02_02_02_weights`, `test_fr68_csat_score_in_0_5_range` | Pending |
| FR-69 | SRS §2 Module 14 | calibration pipeline | `test_fr69_kappa_above_07_on_golden_set`, `test_fr69_15_percent_deviation_triggers_recalibration` | Pending |

### Module 15: 可觀測性

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-70 | SRS §2 Module 15 | `StructuredLogger.log()` | `test_fr70_log_json_parseable`, `test_fr70_timestamp_iso8601_z_format`, `test_fr70_all_log_levels_routed_correctly` | Pending |
| FR-71 | SRS §2 Module 15 | Prometheus metrics definitions | `test_fr71_all_9_metrics_scraped`, `test_fr71_knowledge_hit_total_has_tier_label` | Pending |
| FR-72 | SRS §2 Module 15 | `setup_tracing()`, tracer spans | `test_fr72_span_tree_complete_per_request`, `test_fr72_trace_id_in_response_header`, `test_fr72_span_attributes_include_platform` | Pending |
| FR-73 | SRS §2 Module 15 | Prometheus alert rules | `test_fr73_4_alert_rules_defined`, `test_fr73_slabreach_for_0m_immediate`, `test_fr73_high_latency_threshold_0_8s`, `test_fr73_high_error_rate_threshold_0_5pct` | Pending |
| FR-74 | SRS §2 Module 15 | Grafana dashboard config | `test_fr74_grafana_dashboard_4_panels_exist` | Pending |

### Module 16: Background Job System

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-75 | SRS §2 Module 16 | SAQ worker configuration | `test_fr75_embedding_queue_high_concurrency_3`, `test_fr75_notification_queue_high_concurrency_5`, `test_fr75_sigterm_waits_30s_grace` | Pending |
| FR-76 | SRS §2 Module 16 | `EmbeddingJob`, `process_embedding_job()` | `test_fr76_max_retries_3_then_stop`, `test_fr76_backoff_has_jitter`, `test_fr76_p95_under_30s` | Pending |
| FR-77 | SRS §2 Module 16 | `create_knowledge_with_chunks()` | `test_fr77_first_chunk_searchable_within_25s`, `test_fr77_timeout_does_not_block_main_flow` | Pending |
| FR-78 | SRS §2 Module 16 | `batch_import_knowledge()` | `test_fr78_batch_mode_skips_sync_wait`, `test_fr78_per_entry_under_50ms` | Pending |
| FR-79 | SRS §2 Module 16 | `knowledge_base.embedding_synced_at`, WebUI | `test_fr79_ui_shows_syncing_status`, `test_fr79_embedding_synced_at_set_after_all_chunks` | Pending |

### Module 17: High Availability

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-80 | SRS §2 Module 17 | `AsyncMessageProcessor` | `test_fr80_consumer_group_created`, `test_fr80_busygroup_error_silently_ignored`, `test_fr80_xclaim_processes_pending_messages`, `test_fr80_unknown_fields_ignored` | Pending |
| FR-81 | SRS §2 Module 17 | `RetryStrategy.execute_with_retry()` | `test_fr81_3_retries_then_stop`, `test_fr81_delay_capped_at_30s`, `test_fr81_jitter_applied` | Pending |

### Module 18: Data Layer

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-82 | SRS §2 Module 18 | SQL DDL, Alembic migrations | `test_fr82_all_20_tables_created`, `test_fr82_fk_constraints_valid`, `test_fr82_hnsw_index_exists`, `test_fr82_gin_tsvector_index_exists` | Pending |
| FR-83 | SRS §2 Module 18 | Alembic migration files | `test_fr83_upgrade_migration_succeeds`, `test_fr83_downgrade_migration_succeeds`, `test_fr83_roundtrip_no_data_loss` | Pending |

### Module 19: API 端點

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-84 | SRS §2 Module 19 | FastAPI routers | `test_fr84_all_6_webhook_endpoints_exist`, `test_fr84_error_codes_consistent` | Pending |
| FR-85 | SRS §2 Module 19 | FastAPI management routes | `test_fr85_knowledge_list_rbac_protected`, `test_fr85_health_returns_postgres_redis_uptime`, `test_fr85_paginated_response_has_next` | Pending |
| FR-86 | SRS §2 Module 19 | auth module | `test_fr86_login_returns_jwt_and_refresh`, `test_fr86_login_failure_401`, `test_fr86_role_management_requires_system_write` | Pending |
| FR-87 | SRS §2 Module 19 | M2M token management | `test_fr87_token_shown_once_on_create`, `test_fr87_list_hides_token_value`, `test_fr87_revoke_invalidates_immediately` | Pending |
| FR-88 | SRS §2 Module 19 | GDPR compliance module | `test_fr88_data_export_returns_json`, `test_fr88_data_export_csv_downloadable`, `test_fr88_deletion_clears_pii_fields`, `test_fr88_deletion_logs_gdpr_deletion_event` | Pending |

### Module 20: 安全基礎設施

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-89 | SRS §2 Module 20 | PostgreSQL TDE config | `test_fr89_tde_enabled`, `test_fr89_key_rotation_scheduled_90d`, `test_fr89_pii_vault_direct_read_blocked` | Pending |
| FR-90 | SRS §2 Module 20 | Redis security config | `test_fr90_redis_rejects_plaintext_connection`, `test_fr90_auth_from_env_var`, `test_fr90_default_user_disabled` | Pending |

### Module 21: GDPR & Data Lifecycle

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-91 | SRS §2 Module 21 | data retention scheduled jobs | `test_fr91_180d_messages_archived`, `test_fr91_2yr_archive_deleted`, `test_fr91_pii_audit_90d_anonymized`, `test_fr91_emotion_90d_deleted` | Pending |
| FR-92 | SRS §2 Module 21 | `execute_data_deletion()` | `test_fr92_pii_fields_null_after_deletion`, `test_fr92_messages_redacted`, `test_fr92_gdpr_deletion_event_in_audit_log` | Pending |
| FR-93 | SRS §2 Module 21 | data export endpoint | `test_fr93_export_contains_all_personal_data`, `test_fr93_csv_format_downloadable` | Pending |
| FR-94 | SRS §2 Module 21 | `pii_vault` table, KMS integration | `test_fr94_plaintext_not_in_db`, `test_fr94_dpo_can_decrypt`, `test_fr94_non_dpo_decrypt_fails_403` | Pending |

### Module 22: Deployment

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-95 | SRS §2 Module 22 | docker-compose.yml | `test_fr95_all_7_services_healthy`, `test_fr95_health_endpoint_200_after_compose_up` | Pending |
| FR-96 | SRS §2 Module 22 | K8s manifests | `test_fr96_deployment_3_replicas`, `test_fr96_hpa_scales_to_10`, `test_fr96_pdb_prevents_disruption`, `test_fr96_secrets_not_in_plaintext_configmap` | Pending |
| FR-97 | SRS §2 Module 22 | backup scripts | `test_fr97_pg_basebackup_restore_under_5min`, `test_fr97_redis_rdb_restore_works` | Pending |
| FR-98 | SRS §2 Module 22 | rollback procedures | `test_fr98_knowledge_soft_delete_rollback`, `test_fr98_schema_downgrade_no_data_loss`, `test_fr98_experiment_abort_restores_control` | Pending |

### Module 23: 降級策略

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-99 | SRS §2 Module 23 | circuit breaker implementation | `test_fr99_level1_triggers_on_llm_p95_800ms`, `test_fr99_level3_triggers_on_5_consecutive_failures`, `test_fr99_embedding_down_uses_tsvector_fallback`, `test_fr99_classifier_down_bypasses_l4`, `test_fr99_recovery_auto_rises_on_success_count` | Pending |

### Module 24: 多媒體處理

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-100 | SRS §2 Module 24 | media handling pipeline, ClamAV service | `test_fr100_image_auto_escalate`, `test_fr100_sticker_fixed_reply`, `test_fr100_location_extracts_coordinates`, `test_fr100_file_above_10mb_rejected`, `test_fr100_clamav_down_503_file_scan_unavailable` | Pending |

### Module 25: 管理 WebUI

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-101 | SRS §2 Module 25 | WebUI frontend (React) | `test_fr101_knowledge_crud_correct`, `test_fr101_csv_import_succeeds`, `test_fr101_embedding_status_updates_realtime` | Pending |
| FR-102 | SRS §2 Module 25 | RAG Debugger UI | `test_fr102_debugger_shows_tier1_tier2_flow`, `test_fr102_slider_adjustment_not_persisted` | Pending |
| FR-103 | SRS §2 Module 25 | Operations Dashboard UI | `test_fr103_fcr_below_90_triggers_yellow_alert`, `test_fr103_time_range_switching_works` | Pending |
| FR-104 | SRS §2 Module 25 | Agent Portal UI | `test_fr104_inbox_ws_realtime_update`, `test_fr104_priority_colors_correct`, `test_fr104_takeover_shows_emotion_dst_context` | Pending |

### Module 26: ODD SQL

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-105 | SRS §2 Module 26 | ODD SQL scripts, judge sampling config | `test_fr105_all_sql_execute_on_staging`, `test_fr105_fcr_query_in_scope_only`, `test_fr105_cost_per_tier_correct`, `test_fr105_judge_sample_rate_default_020` | Pending |

### Module 27: 負載測試

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-106 | SRS §2 Module 27 | k6 load test scripts | `test_fr106_smoke_10vu_baseline`, `test_fr106_load_p95_under_1000ms`, `test_fr106_load_error_rate_below_1pct`, `test_fr106_stress_2000tps_no_crash`, `test_fr106_spike_recovery_normal` | Pending |

### Module 28: 測試策略

| FR ID | SRS Section | Design Component | Primary Test Function(s) | Status |
|-------|-------------|------------------|--------------------------|--------|
| FR-107 | SRS §2 Module 28 | pytest test suite, k6 | `test_fr107_unit_coverage_70pct`, `test_fr107_integration_coverage_20pct`, `test_fr107_e2e_faq_exact_match`, `test_fr107_e2e_semantic_search`, `test_fr107_e2e_multi_turn_dst`, `test_fr107_e2e_emotion_escalation`, `test_fr107_e2e_prompt_injection_blocked`, `test_fr107_e2e_fallback_escalation` | Pending |
| FR-108 | SRS §2 Module 28 | golden dataset, `edge_cases` table | `test_fr108_edge_cases_count_500`, `test_fr108_6_categories_present`, `test_fr108_regression_auto_executable` | Pending |

---

## 反向追溯索引 (Reverse Traceability)

每個測試函數前綴 `test_frNN_` 可反向定位至 FR-NN。以下為主要反向連結示例：

| Test Function Prefix | Maps Back To | SRS Module |
|---------------------|-------------|------------|
| `test_fr01_*` | FR-01 | Module 1 — Telegram Adapter |
| `test_fr10_*` | FR-10 | Module 2 — PALADIN L1 |
| `test_fr18_*` | FR-18 | Module 3 — PII Masking |
| `test_fr26_*` | FR-26 | Module 5 — Knowledge T1 |
| `test_fr34_*` | FR-34 | Module 6 — DST FSM |
| `test_fr46_*` | FR-46 | Module 8 — Emotion |
| `test_fr60_*` | FR-60 | Module 12 — RBAC |
| `test_fr65_*` | FR-65 | Module 14 — LLM Judge |
| `test_fr82_*` | FR-82 | Module 18 — DB Schema |
| `test_fr99_*` | FR-99 | Module 23 — Circuit Breaker |
| `test_fr107_*` | FR-107 | Module 28 — Test Strategy |

---

## 完整性驗證

| Check | Target | Phase 1 Status |
|-------|--------|----------------|
| FR → SRS 章節映射 | 100% (108/108 FRs) | ✅ 108/108 |
| FR → 設計元件映射 | 100% (每 FR ≥ 1 個元件) | ✅ 108/108 |
| FR → 測試函數映射 | 100% (每 FR ≥ 1 個測試名稱) | ✅ 108/108 |
| NFR → 測試方法映射 | 100% (38/38 NFRs in SRS) | ✅ 38/38 (測試方法在 SRS §3) |
| 孤立 FR（未追溯） | 0 | ✅ 0 orphans |
| 測試覆蓋率目標 | Unit 70% + Integration 20% + E2E 10% | 📋 Phase 3 驗證 |

---

## 測試命名規範

- **Format**: `test_fr{NN}_{brief_description}` (Python pytest)
- **FR 編號**: 零填充至兩位 (e.g., FR-01 → `test_fr01_*`, FR-108 → `test_fr108_*`)
- **描述**: snake_case, 動詞開頭, 描述預期行為
- **測試類型標記**: 透過目錄結構區分 (unit/ / integration/ / e2e/)
- **NFR 測試**: 依附於相關 FR 測試 (e.g., 延遲 NFR 在 `test_fr10_latency_under_2ms`)

---

## Phase 3 Source Implementation Index

Phase 3 補充：實際程式碼路徑（含 src/ 全路徑）。 ✅

| Layer | Source File | FRs Covered |
|-------|-------------|-------------|
| api | 03-development/src/app/api/webhooks.py | FR-01, FR-02, FR-03, FR-04, FR-05, FR-06 ✅ |
| api | 03-development/src/app/api/m2m.py | FR-07, FR-08, FR-09 ✅ |
| api | 03-development/src/app/api/auth.py | FR-06, FR-07 ✅ |
| api | 03-development/src/app/api/webhook_routes.py | FR-01–FR-06 ✅ |
| api | 03-development/src/app/api/websocket.py | FR-05 ✅ |
| api | 03-development/src/app/api/management.py | FR-107, FR-108 ✅ |
| api | 03-development/src/app/api/agent_card.py | FR-108 ✅ |
| api | 03-development/src/app/api/gdpr.py | FR-93, FR-94 ✅ |
| core | 03-development/src/app/core/paladin.py | FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17 ✅ |
| core | 03-development/src/app/core/pii.py | FR-18, FR-19, FR-20 ✅ |
| core | 03-development/src/app/core/knowledge.py | FR-26, FR-27, FR-28, FR-29, FR-30, FR-31, FR-32 ✅ |
| core | 03-development/src/app/core/chunking.py | FR-33, FR-34, FR-35, FR-36 ✅ |
| core | 03-development/src/app/core/dst.py | FR-37, FR-38, FR-39, FR-40, FR-41, FR-42, FR-43, FR-44, FR-45, FR-46 ✅ |
| core | 03-development/src/app/core/emotion.py | FR-47, FR-48, FR-49 ✅ |
| core | 03-development/src/app/core/response_generator.py | FR-50, FR-51, FR-52 ✅ |
| core | 03-development/src/app/core/retraction.py | FR-53, FR-97 ✅ |
| core | 03-development/src/app/core/unified_message.py | FR-07, FR-08 ✅ |
| core | 03-development/src/app/core/unified_response.py | FR-09 ✅ |
| core | 03-development/src/app/core/pipeline.py | FR-37, FR-53 ✅ |
| core | 03-development/src/app/core/api_response.py | FR-09 ✅ |
| core | 03-development/src/app/core/golden_dataset.py | FR-98 ✅ |
| services | 03-development/src/app/services/telegram_verifier.py | FR-01 ✅ |
| services | 03-development/src/app/services/telegram_adapter.py | FR-01 ✅ |
| services | 03-development/src/app/services/line_verifier.py | FR-02 ✅ |
| services | 03-development/src/app/services/line_adapter.py | FR-02 ✅ |
| services | 03-development/src/app/services/messenger_verifier.py | FR-03 ✅ |
| services | 03-development/src/app/services/messenger_adapter.py | FR-03 ✅ |
| services | 03-development/src/app/services/whatsapp_verifier.py | FR-04 ✅ |
| services | 03-development/src/app/services/whatsapp_adapter.py | FR-04 ✅ |
| services | 03-development/src/app/services/web_verifier.py | FR-05 ✅ |
| services | 03-development/src/app/services/web_adapter.py | FR-05 ✅ |
| services | 03-development/src/app/services/escalation.py | FR-54, FR-55, FR-56, FR-57 ✅ |
| services | 03-development/src/app/services/media.py | FR-58 ✅ |
| services | 03-development/src/app/services/llm_judge.py | FR-63, FR-64, FR-65, FR-66, FR-67, FR-68, FR-69 ✅ |
| services | 03-development/src/app/services/ab_testing.py | FR-98 ✅ |
| services | 03-development/src/app/services/aee/adapter.py | FR-59 ✅ |
| services | 03-development/src/app/services/aee/a2a_adapter.py | FR-60 ✅ |
| services | 03-development/src/app/services/aee/mcp_adapter.py | FR-61 ✅ |
| services | 03-development/src/app/services/aee/cli_adapter.py | FR-62 ✅ |
| services | 03-development/src/app/services/aee/tool_executor.py | FR-59–FR-62 ✅ |
| infra | 03-development/src/app/infra/rate_limit.py | FR-21, FR-22, FR-23, FR-24 ✅ |
| middleware | 03-development/src/app/middleware/ip_whitelist.py | FR-25 ✅ |
| middleware | 03-development/src/app/middleware/chain.py | FR-21–FR-25 ✅ |
| infra | 03-development/src/app/infra/redis_streams.py | FR-80, FR-81, FR-90 ✅ |
| infra | 03-development/src/app/infra/redis_security.py | FR-83 ✅ |
| infra | 03-development/src/app/infra/database.py | FR-82, FR-84, FR-85 ✅ |
| infra | 03-development/src/app/infra/vector_index.py | FR-86, FR-87, FR-88 ✅ |
| infra | 03-development/src/app/infra/tracing.py | FR-70, FR-72 ✅ |
| infra | 03-development/src/app/infra/observability.py | FR-71, FR-73 ✅ |
| infra | 03-development/src/app/infra/grafana_dashboard.py | FR-74 ✅ |
| infra | 03-development/src/app/infra/prometheus_metrics.py | FR-71, FR-73, FR-74 ✅ |
| infra | 03-development/src/app/infra/alert_rules.py | FR-73 ✅ |
| infra | 03-development/src/app/infra/k8s_deployment.py | FR-89, FR-91 ✅ |
| infra | 03-development/src/app/infra/compose.py | FR-89, FR-91 ✅ |
| infra | 03-development/src/app/infra/jobs.py | FR-31 ✅ |
| infra | 03-development/src/app/infra/config_store.py | FR-92 ✅ |
| infra | 03-development/src/app/infra/schema.py | FR-82, FR-84 ✅ |
| infra | 03-development/src/app/infra/migrations.py | FR-82 ✅ |
| infra | 03-development/src/app/infra/tde.py | FR-83 ✅ |
| infra | 03-development/src/app/infra/circuit_breaker.py | FR-95 ✅ |
| infra | 03-development/src/app/infra/retry.py | FR-96 ✅ |
| infra | 03-development/src/app/infra/rollback_strategy.py | FR-97 ✅ |
| infra | 03-development/src/app/infra/backup_strategy.py | FR-97 ✅ |
| infra | 03-development/src/app/infra/data_retention.py | FR-93, FR-94 ✅ |
| infra | 03-development/src/app/infra/data_deletion.py | FR-93 ✅ |
| admin | 03-development/src/app/admin/odd_sql.py | FR-100, FR-105 ✅ |
| admin | 03-development/src/app/admin/rbac.py | FR-101, FR-102 ✅ |
| admin | 03-development/src/app/admin/portal.py | FR-103, FR-104 ✅ |
| admin | 03-development/src/app/admin/webui.py | FR-106 ✅ |
| admin | 03-development/src/app/admin/gdpr.py | FR-93, FR-94, FR-107 ✅ |
