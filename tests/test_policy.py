from mediaorchard.shared.security import hash_api_key, redact_secrets, verify_api_key


def test_api_key_hash_verifies_without_storing_raw_key():
    raw_key = "mo_dev_secret"

    digest = hash_api_key(raw_key)

    assert raw_key not in digest
    assert verify_api_key(raw_key, digest) is True
    assert verify_api_key("wrong", digest) is False


def test_redact_secrets_removes_sensitive_values_recursively():
    payload = {
        "authorization": "Bearer secret",
        "node": {
            "api_key": "secret",
            "token": "secret",
            "safe": "visible",
        },
        "items": [{"secret": "hidden"}, {"name": "kept"}],
    }

    redacted = redact_secrets(payload)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["node"]["api_key"] == "[REDACTED]"
    assert redacted["node"]["token"] == "[REDACTED]"
    assert redacted["node"]["safe"] == "visible"
    assert redacted["items"][0]["secret"] == "[REDACTED]"
    assert redacted["items"][1]["name"] == "kept"

