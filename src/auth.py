"""DB 기반 비밀번호 게이트.

설계 의도:
- 비밀번호 평문은 어디에도 저장 X — bcrypt 해시만 DB 에 저장.
- 사용자(NAS 운영자)가 평문 비번을 모름. DB 파일을 봐도 해시만 보이며,
  bcrypt 의 work factor 로 brute force 저항.
- 첫 접속 시 비번이 미등록이면 "등록" 화면 노출 — 그 화면에서 사용자가
  직접 비번 정함.
- 한 번 등록되면 이후 접속은 "로그인" 화면. 변경은 사이드바의 "비밀번호 변경"
  expander 에서 가능 (이전 비번 + 새 비번 + 확인).
- 환경변수 DASHBOARD_PASSWORD 는 사용 안 함 (deprecated).

세션 인증 상태는 st.session_state 에만 저장 — 브라우저 세션 동안 유지.
"""
from __future__ import annotations

import bcrypt
import streamlit as st

from src import db


_AUTH_SESSION_KEY = "_dashboard_authenticated"
_BCRYPT_ROUNDS = 12  # 적당한 강도 (work factor) — 너무 높으면 로그인이 느림


# --- 비밀번호 저장/검증 ---

def is_password_set() -> bool:
    """DB 에 비밀번호 등록되어 있으면 True."""
    return db.auth_has_password()


def set_password(plain: str) -> None:
    """평문 비밀번호를 bcrypt 해시로 저장. 기존 해시는 덮어씀."""
    plain = (plain or "").strip()
    if len(plain) < 4:
        raise ValueError("비밀번호는 4자 이상이어야 합니다.")
    hashed = bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    )
    db.auth_set_hash(hashed.decode("utf-8"))


def verify_password(plain: str) -> bool:
    """입력값을 DB 해시와 bcrypt 검증."""
    stored = db.auth_get_hash()
    if not stored:
        return False
    plain = (plain or "").strip()
    if not plain:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def change_password(old: str, new: str) -> None:
    """이전 비번 확인 후 새 비번으로 교체. 실패 시 ValueError."""
    if not verify_password(old):
        raise ValueError("이전 비밀번호가 일치하지 않습니다.")
    set_password(new)


# --- 세션 상태 ---

def is_authenticated() -> bool:
    return bool(st.session_state.get(_AUTH_SESSION_KEY))


def _mark_authenticated() -> None:
    st.session_state[_AUTH_SESSION_KEY] = True


def logout() -> None:
    st.session_state.pop(_AUTH_SESSION_KEY, None)


# --- UI 화면들 ---

def _register_form() -> None:
    """비밀번호 미등록 상태 — 사용자가 첫 비번 직접 등록."""
    st.markdown(
        "<div style='text-align:center; padding-top: 2rem;'>"
        "<h1>🔐 비밀번호 등록</h1>"
        "<p>처음 접속하셨습니다. 사용할 비밀번호를 직접 정해주세요.<br/>"
        "이 비밀번호는 NAS 운영자도 알 수 없습니다 (해시로만 저장).</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.form("auth_register_form", clear_on_submit=False):
        pw = st.text_input(
            "비밀번호 (4자 이상)", type="password", key="auth_register_pw",
        )
        pw_confirm = st.text_input(
            "비밀번호 확인", type="password", key="auth_register_pw_confirm",
        )
        submitted = st.form_submit_button("등록", type="primary")
        if submitted:
            if pw != pw_confirm:
                st.error("❌ 비밀번호가 서로 다릅니다.")
            else:
                try:
                    set_password(pw)
                    _mark_authenticated()
                    st.success("✅ 비밀번호 등록 완료. 잠시 후 대시보드로 이동합니다.")
                    st.rerun()
                except ValueError as e:
                    st.error(f"❌ {e}")

    st.stop()


def _login_form() -> None:
    """이미 등록된 비번에 대한 로그인 화면."""
    st.markdown(
        "<div style='text-align:center; padding-top: 2rem;'>"
        "<h1>🔐 로그인</h1>"
        "<p>대시보드 접속을 위해 비밀번호를 입력해주세요.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.form("auth_login_form", clear_on_submit=False):
        pw = st.text_input(
            "비밀번호", type="password", key="auth_login_pw",
        )
        submitted = st.form_submit_button("로그인", type="primary")
        if submitted:
            if verify_password(pw):
                _mark_authenticated()
                st.rerun()
            else:
                st.error("❌ 비밀번호가 일치하지 않습니다.")

    st.stop()


def require_auth() -> None:
    """앱 진입 시 호출. 라우팅:

    - DB 비번 미등록 → 등록 화면
    - 세션 미인증 → 로그인 화면
    - 세션 인증 → 통과
    """
    if is_authenticated():
        return
    if not is_password_set():
        _register_form()
    else:
        _login_form()


def render_sidebar_change_password() -> None:
    """사이드바 footer 에 '비밀번호 변경' expander 렌더.

    이미 인증된 사용자만 호출 가정 (require_auth 후).
    """
    with st.sidebar.expander("🔐 비밀번호 변경", expanded=False):
        with st.form("auth_change_form", clear_on_submit=True):
            old = st.text_input(
                "현재 비밀번호", type="password", key="auth_change_old",
            )
            new = st.text_input(
                "새 비밀번호 (4자 이상)", type="password", key="auth_change_new",
            )
            new_confirm = st.text_input(
                "새 비밀번호 확인", type="password", key="auth_change_new_confirm",
            )
            submitted = st.form_submit_button("변경", type="primary")
            if submitted:
                if new != new_confirm:
                    st.error("❌ 새 비밀번호가 서로 다릅니다.")
                else:
                    try:
                        change_password(old, new)
                        st.success("✅ 비밀번호가 변경되었습니다.")
                    except ValueError as e:
                        st.error(f"❌ {e}")

        if st.button("로그아웃", key="auth_logout_btn"):
            logout()
            st.rerun()
