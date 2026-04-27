"""DB 기반 비밀번호 게이트 — bcrypt 해시 저장/검증."""
from __future__ import annotations

from pathlib import Path

import pytest

from src import auth, db


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """매 테스트마다 임시 DB 로 격리. auth 테이블도 빈 상태로 시작."""
    test_db_path = tmp_path / "test_portfolio.db"
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.initialize()
    yield


class TestPasswordRegistration:
    def test_no_password_initially(self, isolated_db):
        assert auth.is_password_set() is False

    def test_set_password_marks_as_set(self, isolated_db):
        auth.set_password("hello1234")
        assert auth.is_password_set() is True

    def test_set_too_short_rejected(self, isolated_db):
        with pytest.raises(ValueError, match="4자 이상"):
            auth.set_password("ab")
        assert auth.is_password_set() is False

    def test_whitespace_only_rejected(self, isolated_db):
        with pytest.raises(ValueError, match="4자 이상"):
            auth.set_password("   ")

    def test_overwrite_existing(self, isolated_db):
        auth.set_password("first1234")
        auth.set_password("second9876")
        assert auth.verify_password("second9876") is True
        assert auth.verify_password("first1234") is False


class TestPasswordVerification:
    def test_correct_password_passes(self, isolated_db):
        auth.set_password("swordfish")
        assert auth.verify_password("swordfish") is True

    def test_wrong_password_rejected(self, isolated_db):
        auth.set_password("swordfish")
        assert auth.verify_password("salmon") is False

    def test_empty_input_rejected(self, isolated_db):
        auth.set_password("swordfish")
        assert auth.verify_password("") is False

    def test_whitespace_trimmed(self, isolated_db):
        auth.set_password("swordfish")
        assert auth.verify_password("  swordfish  ") is True

    def test_case_sensitive(self, isolated_db):
        auth.set_password("SwordFish")
        assert auth.verify_password("swordfish") is False
        assert auth.verify_password("SwordFish") is True

    def test_unicode_password(self, isolated_db):
        auth.set_password("한글비번123")
        assert auth.verify_password("한글비번123") is True
        assert auth.verify_password("한글비번") is False

    def test_no_password_set_means_verify_false(self, isolated_db):
        assert auth.verify_password("anything") is False


class TestPasswordChange:
    def test_correct_old_changes_password(self, isolated_db):
        auth.set_password("old_pass")
        auth.change_password("old_pass", "new_pass1")
        assert auth.verify_password("new_pass1") is True
        assert auth.verify_password("old_pass") is False

    def test_wrong_old_rejected(self, isolated_db):
        auth.set_password("old_pass")
        with pytest.raises(ValueError, match="이전 비밀번호"):
            auth.change_password("wrong", "new_pass1")
        # 원본 비번 그대로
        assert auth.verify_password("old_pass") is True

    def test_change_to_short_rejected(self, isolated_db):
        auth.set_password("old_pass")
        with pytest.raises(ValueError, match="4자 이상"):
            auth.change_password("old_pass", "ab")
        assert auth.verify_password("old_pass") is True


class TestStorageDoesNotLeakPlaintext:
    def test_db_stores_hash_not_plaintext(self, isolated_db):
        auth.set_password("secret_pw_123")
        stored = db.auth_get_hash()
        assert stored is not None
        # bcrypt 해시는 $2b$ 또는 $2a$ 로 시작하고 평문이 들어가 있지 않음
        assert stored.startswith("$2")
        assert "secret_pw_123" not in stored


class TestAuthClear:
    def test_clear_removes_password(self, isolated_db):
        auth.set_password("hello1234")
        assert auth.is_password_set() is True
        db.auth_clear()
        assert auth.is_password_set() is False
