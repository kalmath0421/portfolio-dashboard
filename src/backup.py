"""DB 백업 모듈 — 시간 스탬프 백업 + 보관 기한 초과 자동 삭제."""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "portfolio.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backup"
DEFAULT_KEEP_DAYS = 30


def backup_now(
    db_path: Path | None = None,
    backup_dir: Path | None = None,
    silent: bool = False,
) -> Path:
    """DB를 시간 스탬프 붙여 백업 폴더에 복사. 백업 경로 반환."""
    src = db_path or DB_PATH
    dest_dir = backup_dir or BACKUP_DIR

    if not src.exists():
        raise FileNotFoundError(f"DB 파일이 없습니다: {src}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = dest_dir / f"portfolio_{stamp}.db"
    shutil.copy2(src, target)

    if not silent:
        size_kb = target.stat().st_size / 1024
        print(f"[OK] 백업 생성: {target.name} ({size_kb:,.1f} KB)")
    return target


def prune_old(
    keep_days: int = DEFAULT_KEEP_DAYS,
    backup_dir: Path | None = None,
    silent: bool = False,
) -> int:
    """N일 이전 백업 파일 삭제. 삭제된 개수 반환."""
    dest_dir = backup_dir or BACKUP_DIR
    if not dest_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    for f in dest_dir.glob("portfolio_*.db"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            removed += 1
            if not silent:
                print(f"[CLEAN] {f.name} 삭제 (보관 기한 {keep_days}일 초과)")
    return removed


def list_backups(backup_dir: Path | None = None) -> list[Path]:
    dest_dir = backup_dir or BACKUP_DIR
    if not dest_dir.exists():
        return []
    return sorted(dest_dir.glob("portfolio_*.db"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="포트폴리오 DB 백업")
    parser.add_argument(
        "--silent", action="store_true", help="출력 없이 실행 (스케줄러용)"
    )
    parser.add_argument(
        "--keep-days", type=int, default=DEFAULT_KEEP_DAYS,
        help=f"보관 기간 일수 (기본 {DEFAULT_KEEP_DAYS}일)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="백업 목록만 출력하고 종료",
    )
    args = parser.parse_args(argv)

    if args.list:
        backups = list_backups()
        if not backups:
            print("백업이 없습니다.")
            return 0
        print(f"백업 목록 ({len(backups)}개):")
        for b in backups:
            mtime = datetime.fromtimestamp(b.stat().st_mtime)
            size_kb = b.stat().st_size / 1024
            print(f"  {b.name}  {size_kb:>8,.1f} KB  {mtime:%Y-%m-%d %H:%M}")
        return 0

    try:
        backup_now(silent=args.silent)
        prune_old(keep_days=args.keep_days, silent=args.silent)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
