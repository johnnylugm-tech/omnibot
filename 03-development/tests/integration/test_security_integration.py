"""Integration tests: security pipeline — Paladin + GDPR + PII + TDE + RBAC."""


def test_paladin_pipeline_full_flow():
    """PaladinPipeline runs InputSanitizer → PatternDetector → GroundingChecker."""
    from src.security.paladin import (
        PaladinPipeline, InputSanitizer, PatternDetector,
        SemanticInjectionClassifier, GroundingChecker,
    )
    sanitizer = InputSanitizer()
    detector = PatternDetector()
    classifier = SemanticInjectionClassifier()
    checker = GroundingChecker()

    clean_text = sanitizer.sanitize("hello world")
    assert clean_text == "hello world"

    patterns = detector.detect(clean_text)
    assert isinstance(patterns, list)
    assert len(patterns) == 0

    prob = classifier.classify("hello world")
    assert 0.0 <= prob <= 1.0

    grounding_score = checker.check("hello world", "hello world is safe")
    assert isinstance(grounding_score, float)

    pipeline = PaladinPipeline()
    result = pipeline.run("hello world")
    assert isinstance(result, dict)
    assert "blocked" in result
    assert result["blocked"] is False


def test_paladin_sandwich_and_retraction():
    """SandwichPrompter wraps user input; RetractionManager retracts messages."""
    from src.security.paladin import SandwichPrompter, RetractionManager, RetrospectiveBlocker

    prompter = SandwichPrompter()
    wrapped = prompter.wrap("User says: hello", "You are a safe assistant.")
    assert "hello" in wrapped
    assert "You are a safe assistant." in wrapped

    retractor = RetractionManager()
    retracted = retractor.retract("msg-001", "policy violation")
    assert retracted is True

    blocker = RetrospectiveBlocker()
    blocked = blocker.check({"output": "some text", "turn": 1})
    assert isinstance(blocked, bool)


def test_gdpr_vault_and_deletion_integration():
    """PIIVault stores, retrieves, and deletes; GDPRDeletion verifies erasure."""
    from src.security.gdpr import PIIVault, GDPRDeletion, GDPRExport, DataRetentionPolicy

    vault = PIIVault()
    vault.store("user:123:email", "user@example.com")
    assert vault.retrieve("user:123:email") == "user@example.com"

    vault.delete("user:123:email")
    assert vault.retrieve("user:123:email") is None

    deletion = GDPRDeletion()
    deleted = deletion.delete("user:123")
    assert deleted is True

    verified = deletion.verify_deletion("user:123")
    assert verified is True

    export = GDPRExport()
    data = export.export("user:123")
    assert data["user_id"] == "user:123"

    policy = DataRetentionPolicy(category="chat_logs", retention_days=90)
    assert policy.retention_days == 90
    assert policy.auto_delete is True


def test_tde_encrypt_decrypt_roundtrip():
    """TDEManager encrypt + decrypt are inverses (stub implementation)."""
    from src.security.tde import TDEManager

    mgr = TDEManager(key_id="key-001")
    plaintext = "confidential data"
    encrypted = mgr.encrypt(plaintext)
    decrypted = mgr.decrypt(encrypted)
    assert decrypted == plaintext

    new_key = mgr.rotate_key()
    assert isinstance(new_key, str)


def test_pii_masking_pipeline_with_audit():
    """PIIMasker masks text; PIIAuditLogger logs the event; EscalationChecker evaluates."""
    from src.pii.masking import PIIMasker, PIIAuditLogger, PIIEscalationChecker

    masker = PIIMasker()
    masked = masker.mask("Call me at 0912345678 or email me@example.com")
    assert "[PHONE]" in masked
    assert "[EMAIL]" in masked

    escalation_checker = PIIEscalationChecker()
    should_escalate = escalation_checker.should_escalate(masked)
    assert should_escalate is False

    audit_logger = PIIAuditLogger()
    audit_logger.log("mask_event", {"original_len": 50, "masked_len": len(masked)})
    assert audit_logger is not None


def test_redis_security_url_construction():
    """RedisSecurityConfig builds correct URL based on TLS flag."""
    from src.security.redis_security import RedisSecurityConfig

    secure = RedisSecurityConfig(host="redis.example.com", tls_enabled=True, password="secret")
    url = secure.to_url()
    assert url.startswith("rediss://")
    assert "redis.example.com" in url

    insecure = RedisSecurityConfig(host="localhost", tls_enabled=False)
    url2 = insecure.to_url()
    assert url2.startswith("redis://")


def test_rbac_grant_and_enforcement():
    """RBACEnforcer grants permissions to roles and enforces access."""
    from src.rbac.enforcer import RBACEnforcer

    rbac = RBACEnforcer()
    rbac.grant("admin", "read")
    rbac.grant("admin", "write")
    rbac.grant("viewer", "read")

    assert rbac.is_allowed("admin", "read") is True
    assert rbac.is_allowed("admin", "write") is True
    assert rbac.is_allowed("viewer", "read") is True
    assert rbac.is_allowed("viewer", "write") is False
    assert rbac.is_allowed("unknown", "read") is False
