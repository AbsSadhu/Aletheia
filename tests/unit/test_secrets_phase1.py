from aletheia.security.secrets import decrypt_sensitive, encrypt_sensitive, mask_for_logs


def test_encrypt_decrypt_sensitive_round_trip() -> None:
    encrypted = encrypt_sensitive("top-secret-value")
    assert encrypted.startswith("enc:")
    assert decrypt_sensitive(encrypted) == "top-secret-value"


def test_mask_for_logs() -> None:
    assert mask_for_logs("sk-1234567890") == "sk-1...890"
    assert mask_for_logs("") == "<empty>"
