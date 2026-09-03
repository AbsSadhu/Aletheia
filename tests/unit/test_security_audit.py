from aletheia.security.audit import _redact, redact_secrets


def test_redact_masks_sensitive_dict_keys() -> None:
    result = _redact({"api_key": "sk-1234567890", "username": "trader"})
    assert result["api_key"] == "sk-1...890"
    assert result["username"] == "trader"


def test_redact_masks_password_secret_token_session_markers() -> None:
    result = _redact(
        {
            "password": "hunter1234",
            "client_secret": "abcd1234efgh",
            "access_token": "tok_abcdefghij",
            "session_id": "sess_abcdefghij",
        }
    )
    assert result["password"] == "hunt...234"
    assert result["client_secret"] == "abcd...fgh"
    assert result["access_token"] == "tok_...hij"
    assert result["session_id"] == "sess...hij"


def test_redact_is_case_insensitive_on_marker() -> None:
    result = _redact({"API_KEY": "sk-1234567890", "Password": "hunter1234"})
    assert result["API_KEY"] == "sk-1...890"
    assert result["Password"] == "hunt...234"


def test_redact_masks_short_sensitive_value_as_asterisks() -> None:
    result = _redact({"token": "short"})
    assert result["token"] == "*****"


def test_redact_masks_none_sensitive_value_as_empty_marker() -> None:
    result = _redact({"password": None})
    assert result["password"] == "<empty>"


def test_redact_leaves_non_sensitive_values_untouched() -> None:
    original = {"symbol": "RELIANCE", "quantity": 100, "price": 2500.5}
    assert _redact(original) == original


def test_redact_recurses_into_nested_dicts() -> None:
    result = _redact({"config": {"api_key": "sk-1234567890", "region": "ap-south-1"}})
    assert result["config"]["api_key"] == "sk-1...890"
    assert result["config"]["region"] == "ap-south-1"


def test_redact_recurses_into_list_of_dicts() -> None:
    result = _redact([{"token": "tok_abcdefghij"}, {"symbol": "TCS"}])
    assert result[0]["token"] == "tok_...hij"
    assert result[1]["symbol"] == "TCS"


def test_redact_recurses_into_tuple_and_preserves_type() -> None:
    result = _redact(({"secret": "abcd1234efgh"}, "unchanged"))
    assert isinstance(result, tuple)
    assert result[0]["secret"] == "abcd...fgh"
    assert result[1] == "unchanged"


def test_redact_recurses_into_set() -> None:
    result = _redact({"plain-value"})
    assert result == {"plain-value"}


def test_redact_passes_through_scalars_unchanged() -> None:
    assert _redact("just a string") == "just a string"
    assert _redact(42) == 42
    assert _redact(None) is None


def test_redact_secrets_decorator_redacts_kwargs() -> None:
    @redact_secrets
    def call(**kwargs):
        return kwargs

    result = call(api_key="sk-1234567890", symbol="INFY")
    assert result["api_key"] == "sk-1...890"
    assert result["symbol"] == "INFY"


def test_redact_secrets_decorator_does_not_redact_positional_args() -> None:
    # Documents current behavior/limitation: only **kwargs are redacted, not
    # positional args, so callers passing secrets positionally bypass this.
    @redact_secrets
    def call(secret_value):
        return secret_value

    assert call("sk-1234567890") == "sk-1234567890"


def test_redact_secrets_decorator_preserves_wrapped_function_metadata() -> None:
    @redact_secrets
    def call(**kwargs):
        """Docstring."""
        return kwargs

    assert call.__name__ == "call"
    assert call.__doc__ == "Docstring."


def test_redact_secrets_decorator_preserves_return_value() -> None:
    @redact_secrets
    def call(**kwargs):
        return {"status": "ok", **kwargs}

    result = call(token="tok_abcdefghij")
    assert result["status"] == "ok"
    assert result["token"] == "tok_...hij"
