"""대시보드 커스텀 CSS — 카드 메트릭, Pretendard 한글 폰트, 정돈된 레이아웃."""
from __future__ import annotations

import streamlit as st


_CUSTOM_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
@import url('https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap');

html, body, [class*="css"], button, input, textarea, select,
[data-testid="stSidebar"] *, [data-testid="stMetric"] *,
h1, h2, h3, h4, h5, h6, p, span, div, label {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 'Apple SD Gothic Neo', 'Noto Sans KR',
                 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji',
                 'Segoe UI Symbol', sans-serif !important;
    letter-spacing: -0.01em;
}

/* 이모지를 컬러로 렌더 (CSS4) */
* { font-variant-emoji: emoji; }

/* ---- 본문 배경 톤 다듬기 ---- */
[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at top, #131722 0%, #0F1218 60%);
}

/* ---- 메트릭 카드형 ---- */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1A1F2C 0%, #14171F 100%);
    border: 1px solid #232936;
    border-radius: 14px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02) inset,
                0 4px 12px rgba(0, 0, 0, 0.25);
    transition: transform 0.15s ease, border-color 0.15s ease;
}
[data-testid="stMetric"]:hover {
    border-color: #F5A623;
    transform: translateY(-1px);
}
[data-testid="stMetric"] label {
    color: #94A3B8 !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em;
}
[data-testid="stMetricValue"] {
    color: #F1F5F9 !important;
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    line-height: 1.25 !important;
}
[data-testid="stMetricDelta"] {
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}

/* ---- 사이드바 ---- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #14171F 0%, #0F1218 100%);
    border-right: 1px solid #232936;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 {
    font-size: 1.15rem !important;
    color: #F1F5F9 !important;
    margin-bottom: 0.25rem !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 0.15rem;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: 0.45rem 0.6rem;
    border-radius: 8px;
    transition: background 0.15s ease;
    cursor: pointer;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(245, 166, 35, 0.08);
}

/* ---- 컨테이너 박스 (border=True) ---- */
[data-testid="stVerticalBlock"] > div[style*="border-radius"] {
    border-radius: 14px !important;
    border-color: #232936 !important;
    background: linear-gradient(180deg, #14171F 0%, #11141B 100%) !important;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02) inset,
                0 6px 16px rgba(0, 0, 0, 0.18);
}

/* ---- 헤더 ---- */
h1 {
    color: #F1F5F9 !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}
h2 {
    color: #F1F5F9 !important;
    font-weight: 700 !important;
    border-bottom: 1px solid #232936;
    padding-bottom: 0.5rem;
    margin-top: 1rem;
    margin-bottom: 1rem;
}
h3 {
    color: #E6E9EF !important;
    font-weight: 600 !important;
}

/* ---- 데이터 테이블 ---- */
[data-testid="stDataFrame"] {
    border: 1px solid #232936;
    border-radius: 10px;
    overflow: hidden;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #1A1F2C !important;
    color: #94A3B8 !important;
    font-weight: 600 !important;
    border-bottom: 1px solid #232936 !important;
}

/* ---- 버튼 ---- */
[data-testid="stBaseButton-primary"],
button[kind="primary"] {
    background: linear-gradient(135deg, #F5A623 0%, #E89200 100%) !important;
    border: none !important;
    color: #15181E !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 6px rgba(245, 166, 35, 0.25) !important;
}
[data-testid="stBaseButton-primary"]:hover {
    box-shadow: 0 4px 14px rgba(245, 166, 35, 0.4) !important;
    transform: translateY(-1px);
}
[data-testid="stBaseButton-secondary"],
button[kind="secondary"] {
    background: #1A1F2C !important;
    border: 1px solid #2A3142 !important;
    color: #E6E9EF !important;
    border-radius: 8px !important;
}

/* ---- expander ---- */
[data-testid="stExpander"] {
    border: 1px solid #232936 !important;
    border-radius: 12px !important;
    background: #14171F;
    overflow: hidden;
}
[data-testid="stExpander"] summary {
    padding: 0.65rem 1rem !important;
}

/* ---- 알림 박스 ---- */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border-width: 1px !important;
}

/* ---- 탭 ---- */
[data-baseweb="tab-list"] {
    border-bottom: 1px solid #232936 !important;
    gap: 0.25rem;
}
[data-baseweb="tab"] {
    color: #94A3B8 !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #F5A623 !important;
    font-weight: 700 !important;
}
[data-baseweb="tab-highlight"] {
    background-color: #F5A623 !important;
    height: 2px !important;
}

/* ---- 입력 폼 컴포넌트 ---- */
[data-baseweb="input"], [data-baseweb="select"],
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input,
[data-testid="stDateInput"] input {
    border-radius: 8px !important;
}

/* ---- 캡션 / 도움말 ---- */
[data-testid="stCaptionContainer"] {
    color: #7E8895 !important;
    font-size: 0.82rem !important;
}

/* ---- divider ---- */
hr {
    border-color: #232936 !important;
    margin: 1.25rem 0 !important;
}

/* ---- 모바일 (768px 이하) ---- */
@media (max-width: 768px) {
    /* 가로 오버플로우 방지 */
    html, body, [data-testid="stAppViewContainer"] {
        overflow-x: hidden !important;
        max-width: 100vw !important;
    }
    /* 본문 패딩 축소 */
    [data-testid="stAppViewContainer"] .main .block-container {
        padding: 1rem 0.75rem !important;
        max-width: 100% !important;
    }
    /* 메트릭 카드 폰트 축소 */
    [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
    }
    [data-testid="stMetric"] {
        padding: 0.75rem 0.85rem !important;
    }
    /* 데이터프레임 가로 스크롤 허용 */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }
    /* 헤더 폰트 살짝 축소 */
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }
}
</style>
"""


def apply_theme() -> None:
    """앱 부팅 시 1회 호출 — 전체 화면에 커스텀 CSS 적용."""
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
