"""대시보드 프로파일 모드 — 환경변수 기반.

같은 코드베이스를 두 가지 모드로 운영하기 위한 작은 모듈.

환경변수:
- DASHBOARD_PROFILE: "corp" (기본) | "personal"
    - corp: 법인 유보금 운용 모드. 법인 계좌·세금 페이지 노출, 계좌 종류 선택 가능.
    - personal: 개인 투자자 모드. 법인 계좌·세금 페이지 숨김, 계좌 종류는 개인 자동 고정.
- DASHBOARD_TITLE: 사이드바·페이지 타이틀에 노출할 문자열. 미지정 시 모드별 기본값.
- DASHBOARD_SUBTITLE: 사이드바 캡션 (선택). 미지정 시 모드별 기본값.

기본값(미지정 시):
- corp 모드: "법인 포트폴리오 대시보드", "법인 투자 모니터링 (모니터링 보조 도구)"
- personal 모드: "포트폴리오 대시보드", "개인 투자 모니터링 (모니터링 보조 도구)"

기존 corp 인스턴스는 환경변수를 주지 않아도 100% 동일하게 동작합니다.
"""
from __future__ import annotations

import os

PROFILE_CORP = "corp"
PROFILE_PERSONAL = "personal"

_VALID_PROFILES = {PROFILE_CORP, PROFILE_PERSONAL}


def get_profile() -> str:
    """현재 실행 중인 프로파일을 반환. 잘못된 값이 들어오면 corp로 안전 복구."""
    raw = os.getenv("DASHBOARD_PROFILE", PROFILE_CORP).strip().lower()
    return raw if raw in _VALID_PROFILES else PROFILE_CORP


def is_personal() -> bool:
    return get_profile() == PROFILE_PERSONAL


def is_corp() -> bool:
    return get_profile() == PROFILE_CORP


def get_page_title() -> str:
    """브라우저 탭 + 사이드바 헤더에 쓸 타이틀."""
    custom = os.getenv("DASHBOARD_TITLE")
    if custom:
        return custom
    return "포트폴리오 대시보드" if is_personal() else "법인 포트폴리오 대시보드"


def get_subtitle() -> str:
    """사이드바 캡션."""
    custom = os.getenv("DASHBOARD_SUBTITLE")
    if custom:
        return custom
    if is_personal():
        return "개인 투자 모니터링 (모니터링 보조 도구)"
    return "법인 투자 모니터링 (모니터링 보조 도구)"
