"""앱 비밀번호 게이트 — 환경변수 기반의 가벼운 인증.

환경변수:
- DASHBOARD_PASSWORD: 평문 비밀번호. 빈 문자열이거나 미설정이면 게이트 비활성화
  (개발 환경, 또는 의도적으로 공개로 운영하는 경우).

설계 의도:
- HTTPS 종단 간 암호화로 전송 중 비번이 평문 노출되지 않음.
- 환경변수는 docker-compose 또는 인스턴스 환경에 격리됨.
- session_state 에 인증 결과를 저장 — 브라우저 세션 동안 유지.
- 본격적인 사용자 관리/2FA 가 아닌, "URL 만 알면 누구나" 라는 가장 큰 구멍을 막는
  최소 수준 보호. 강력한 보안이 필요하면 VPN, mTLS, OIDC 등으로 업그레이드.
"""
from __future__ import annotations

import hmac
import os

import streamlit as st


_AUTH_SESSION_KEY = "_dashboard_authenticated"


def _expected_password() -> str:
    return os.getenv("DASHBOARD_PASSWORD", "").strip()


def is_gate_enabled() -> bool:
    """환경변수에 비번이 설정되어 있으면 게이트 활성."""
    return bool(_expected_password())


def verify_password(candidate: str) -> bool:
    """입력값과 환경변수 비번을 상수시간 비교.

    hmac.compare_digest 로 timing attack 회피 (지나친 걱정이긴 하지만 무료에 가깝다).
    """
    expected = _expected_password()
    if not expected:
        # 환경변수 미설정 — 게이트 비활성. 어떤 입력이든 통과 처리.
        return True
    # bytes 로 인코딩 후 상수시간 비교 (compare_digest 는 non-ASCII 문자열 지원 X).
    return hmac.compare_digest(
        candidate.strip().encode("utf-8"),
        expected.encode("utf-8"),
    )


def require_auth() -> None:
    """앱 진입 시 호출. 인증 안 돼 있으면 비번 입력 화면을 띄우고 이후 렌더링 중단.

    이미 통과한 세션이면 즉시 반환해 정상 흐름 진행.
    환경변수 미설정이면 게이트 비활성으로 통과.
    """
    if not is_gate_enabled():
        return
    if st.session_state.get(_AUTH_SESSION_KEY):
        return

    # 인증 폼 — 사이드바 등 다른 UI 는 아직 렌더되지 않은 시점이라 가운데 정렬로 단독 화면.
    st.markdown(
        "<div style='text-align:center; padding-top: 2rem;'>"
        "<h1>🔐 인증 필요</h1>"
        "<p>대시보드 접속을 위해 비밀번호를 입력해주세요.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.form("auth_form", clear_on_submit=False):
        candidate = st.text_input(
            "비밀번호", type="password", key="auth_pw_input",
        )
        submitted = st.form_submit_button("로그인", type="primary")
        if submitted:
            if verify_password(candidate):
                st.session_state[_AUTH_SESSION_KEY] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 일치하지 않습니다.")

    st.stop()
