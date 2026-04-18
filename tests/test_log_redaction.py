from modules.log_redaction import redact_sensitive_text


def test_redact_sensitive_text_mask_senha_anydesk_e_login():
    raw = "Anydesk:123456789 Senha Anydesk: senha-teste Login: usuario_teste Senha: senha123"
    redacted = redact_sensitive_text(raw)
    assert "123456789" not in redacted
    assert "senha-teste" not in redacted
    assert "senha123" not in redacted
    assert "usuario_teste" not in redacted
    assert "***" in redacted


def test_redact_sensitive_text_mask_password_and_token():
    raw = "password=abc123 token: xyz987 api_key=minha-chave"
    redacted = redact_sensitive_text(raw)
    assert "abc123" not in redacted
    assert "xyz987" not in redacted
    assert "minha-chave" not in redacted
