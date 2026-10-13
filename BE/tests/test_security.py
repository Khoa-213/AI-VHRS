from datetime import timedelta

import bcrypt
import pytest

from app.core import security
from app.core.errors import AppError


def test_hash_roundtrip_and_wrong_password():
    h = security.hash_password("Passw0rd!x")
    assert security.verify_password("Passw0rd!x", h)
    assert not security.verify_password("nope", h)


def test_verifies_pgcrypto_bcrypt_seed_format():
    # '$2a$' hashes are what crypt(..., gen_salt('bf')) writes in the SQL seed.
    h = bcrypt.hashpw(b"ChangeMe@123", bcrypt.gensalt(10, prefix=b"2a")).decode()
    assert h.startswith("$2a$") and security.verify_password("ChangeMe@123", h)


@pytest.mark.parametrize("pw", ["short1", "allletters", "12345678", "x" * 80 + "1"])
def test_weak_passwords_rejected(pw):
    with pytest.raises(AppError) as e:
        security.validate_password_strength(pw)
    assert e.value.code == "WEAK_PASSWORD"


def test_token_type_is_enforced():
    t = security.create_token(7, security.REFRESH, timedelta(minutes=1))
    assert security.decode_token(t, security.REFRESH)["sub"] == "7"
    with pytest.raises(AppError) as e:
        security.decode_token(t, security.ACCESS)
    assert e.value.code == "TOKEN_INVALID"


def test_expired_token():
    t = security.create_token(7, security.ACCESS, timedelta(seconds=-5))
    with pytest.raises(AppError) as e:
        security.decode_token(t, security.ACCESS)
    assert e.value.code == "TOKEN_EXPIRED"
