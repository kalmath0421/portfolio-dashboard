"""백업 모듈 단위 테스트."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src import backup


@pytest.fixture
def fake_db(tmp_path: Path):
    db = tmp_path / "portfolio.db"
    db.write_bytes(b"FAKE_SQLITE_DATA")
    return db


@pytest.fixture
def backup_dir(tmp_path: Path):
    d = tmp_path / "backup"
    return d


class TestBackupNow:
    def test_creates_dir_if_missing(self, fake_db, backup_dir):
        assert not backup_dir.exists()
        result = backup.backup_now(db_path=fake_db, backup_dir=backup_dir, silent=True)
        assert backup_dir.exists()
        assert result.exists()

    def test_filename_pattern(self, fake_db, backup_dir):
        result = backup.backup_now(db_path=fake_db, backup_dir=backup_dir, silent=True)
        # 형식: portfolio_YYYYMMDD_HHMMSS.db
        assert result.name.startswith("portfolio_")
        assert result.name.endswith(".db")
        stamp = result.name[len("portfolio_"):-len(".db")]
        # 8자리 날짜 + _ + 6자리 시간
        parts = stamp.split("_")
        assert len(parts) == 2
        assert len(parts[0]) == 8 and parts[0].isdigit()
        assert len(parts[1]) == 6 and parts[1].isdigit()

    def test_content_matches(self, fake_db, backup_dir):
        result = backup.backup_now(db_path=fake_db, backup_dir=backup_dir, silent=True)
        assert result.read_bytes() == b"FAKE_SQLITE_DATA"

    def test_missing_db_raises(self, backup_dir, tmp_path):
        with pytest.raises(FileNotFoundError):
            backup.backup_now(
                db_path=tmp_path / "nope.db", backup_dir=backup_dir, silent=True,
            )

    def test_two_backups_have_different_names(self, fake_db, backup_dir):
        b1 = backup.backup_now(db_path=fake_db, backup_dir=backup_dir, silent=True)
        time.sleep(1.1)  # 시간 스탬프가 초 단위라 1초+ 대기
        b2 = backup.backup_now(db_path=fake_db, backup_dir=backup_dir, silent=True)
        assert b1.name != b2.name


class TestPruneOld:
    def test_removes_files_older_than_cutoff(self, backup_dir):
        backup_dir.mkdir(parents=True)
        old = backup_dir / "portfolio_20200101_000000.db"
        recent = backup_dir / "portfolio_20990101_000000.db"
        old.write_bytes(b"x")
        recent.write_bytes(b"y")
        # mtime을 2년 전으로 강제
        two_years_ago = (datetime.now() - timedelta(days=730)).timestamp()
        os.utime(old, (two_years_ago, two_years_ago))

        removed = backup.prune_old(keep_days=30, backup_dir=backup_dir, silent=True)
        assert removed == 1
        assert not old.exists()
        assert recent.exists()

    def test_no_action_when_dir_missing(self, tmp_path):
        result = backup.prune_old(
            keep_days=30, backup_dir=tmp_path / "nope", silent=True
        )
        assert result == 0

    def test_does_not_touch_other_files(self, backup_dir):
        backup_dir.mkdir(parents=True)
        old_unrelated = backup_dir / "other.txt"
        old_unrelated.write_bytes(b"x")
        two_years_ago = (datetime.now() - timedelta(days=730)).timestamp()
        os.utime(old_unrelated, (two_years_ago, two_years_ago))

        backup.prune_old(keep_days=30, backup_dir=backup_dir, silent=True)
        # portfolio_*.db 패턴만 처리하므로 다른 파일은 건드리지 않음
        assert old_unrelated.exists()


class TestListBackups:
    def test_empty_when_no_dir(self, tmp_path):
        result = backup.list_backups(backup_dir=tmp_path / "nope")
        assert result == []

    def test_sorted(self, backup_dir):
        backup_dir.mkdir(parents=True)
        names = ["portfolio_20260101_120000.db", "portfolio_20251231_235959.db",
                 "portfolio_20260102_080000.db"]
        for n in names:
            (backup_dir / n).write_bytes(b"x")
        result = backup.list_backups(backup_dir=backup_dir)
        assert [p.name for p in result] == sorted(names)


class TestCli:
    def test_list_command(self, fake_db, backup_dir, monkeypatch, capsys):
        monkeypatch.setattr(backup, "DB_PATH", fake_db)
        monkeypatch.setattr(backup, "BACKUP_DIR", backup_dir)
        backup_dir.mkdir(parents=True)
        (backup_dir / "portfolio_20260101_000000.db").write_bytes(b"x")

        rc = backup.main(["--list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "백업 목록" in out
        assert "portfolio_20260101_000000.db" in out

    def test_silent_run(self, fake_db, backup_dir, monkeypatch, capsys):
        monkeypatch.setattr(backup, "DB_PATH", fake_db)
        monkeypatch.setattr(backup, "BACKUP_DIR", backup_dir)
        rc = backup.main(["--silent"])
        assert rc == 0
        # silent 모드 → 출력 없음
        out = capsys.readouterr().out
        assert out == ""
        # 백업 파일은 생성됨
        assert len(list(backup_dir.glob("portfolio_*.db"))) == 1

    def test_missing_db_returns_error(self, backup_dir, monkeypatch, capsys):
        monkeypatch.setattr(backup, "DB_PATH", backup_dir / "nope.db")
        monkeypatch.setattr(backup, "BACKUP_DIR", backup_dir)
        rc = backup.main([])
        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
