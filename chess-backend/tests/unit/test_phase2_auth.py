"""
Phase 2 unit tests: UserRepository, AuthService (register/login).
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.db.database import get_connection
from server.repositories.user_repository import UserRepository
from server.repositories.base_repository import AbstractUserRepository, UserRecord
from server.services.auth_service import AuthService, AuthSuccess, AuthError
from server.config_loader import load_settings


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_in_memory_repo() -> UserRepository:
    conn = get_connection(":memory:")
    return UserRepository(conn)


def make_auth_service(repo=None) -> AuthService:
    settings = load_settings()
    if repo is None:
        repo = make_in_memory_repo()
    return AuthService(repo=repo, settings=settings)


# ── UserRepository ────────────────────────────────────────────────────────────

class TestUserRepository:
    def test_create_and_get_by_username(self):
        repo = make_in_memory_repo()
        user = repo.create("alice", "hashXYZ", 1200)
        assert user.username == "alice"
        assert user.elo == 1200
        assert user.password_hash == "hashXYZ"
        found = repo.get_by_username("alice")
        assert found is not None
        assert found.id == user.id

    def test_get_by_username_missing(self):
        repo = make_in_memory_repo()
        assert repo.get_by_username("nobody") is None

    def test_duplicate_username_raises(self):
        repo = make_in_memory_repo()
        repo.create("bob", "hash1", 1200)
        with pytest.raises(ValueError, match="already exists"):
            repo.create("bob", "hash2", 1200)

    def test_update_elo(self):
        repo = make_in_memory_repo()
        user = repo.create("charlie", "hash", 1200)
        repo.update_elo(user.id, 1250)
        updated = repo.get_by_id(user.id)
        assert updated.elo == 1250

    def test_update_last_login(self):
        repo = make_in_memory_repo()
        user = repo.create("dan", "hash", 1200)
        assert user.last_login_at is None
        repo.update_last_login(user.id)
        updated = repo.get_by_id(user.id)
        assert updated.last_login_at is not None

    def test_get_by_id_missing(self):
        repo = make_in_memory_repo()
        assert repo.get_by_id(999) is None

    def test_starting_elo_stored(self):
        repo = make_in_memory_repo()
        user = repo.create("eve", "hash", 1400)
        assert user.elo == 1400


# ── AuthService ───────────────────────────────────────────────────────────────

class TestAuthService:
    def test_register_success(self):
        svc = make_auth_service()
        result = svc.register("alice", "strongpass123")
        assert isinstance(result, AuthSuccess)
        assert result.username == "alice"
        assert result.elo == 1200
        assert result.session_token != ""

    def test_register_duplicate_username(self):
        svc = make_auth_service()
        svc.register("alice", "strongpass123")
        result = svc.register("alice", "otherpass123")
        assert isinstance(result, AuthError)
        assert "taken" in result.reason

    def test_register_password_too_short(self):
        svc = make_auth_service()
        result = svc.register("alice", "short")
        assert isinstance(result, AuthError)
        assert "too_short" in result.reason

    def test_register_empty_username(self):
        svc = make_auth_service()
        result = svc.register("", "strongpass123")
        assert isinstance(result, AuthError)

    def test_login_success(self):
        svc = make_auth_service()
        svc.register("alice", "strongpass123")
        result = svc.login("alice", "strongpass123")
        assert isinstance(result, AuthSuccess)
        assert result.username == "alice"
        assert result.session_token != ""

    def test_login_wrong_password(self):
        svc = make_auth_service()
        svc.register("alice", "strongpass123")
        result = svc.login("alice", "wrongpassword")
        assert isinstance(result, AuthError)
        assert "invalid_credentials" in result.reason

    def test_login_unknown_user(self):
        svc = make_auth_service()
        result = svc.login("nobody", "anypassword123")
        assert isinstance(result, AuthError)

    def test_token_is_valid_after_login(self):
        svc = make_auth_service()
        svc.register("alice", "strongpass123")
        result = svc.login("alice", "strongpass123")
        assert isinstance(result, AuthSuccess)
        info = svc.validate_token(result.session_token)
        assert info is not None
        user_id, username, elo = info
        assert username == "alice"
        assert elo == 1200

    def test_invalid_token_returns_none(self):
        svc = make_auth_service()
        assert svc.validate_token("bogus-token") is None

    def test_password_not_in_hash(self):
        """The stored hash must not contain the plaintext password."""
        svc = make_auth_service()
        repo = make_in_memory_repo()
        svc2 = make_auth_service(repo)
        svc2.register("alice", "strongpass123")
        user = repo.get_by_username("alice")
        assert "strongpass123" not in user.password_hash

    def test_different_users_get_different_tokens(self):
        svc = make_auth_service()
        svc.register("alice", "strongpass123")
        svc.register("bob", "bobspass123")
        r1 = svc.login("alice", "strongpass123")
        r2 = svc.login("bob", "bobspass123")
        assert r1.session_token != r2.session_token
