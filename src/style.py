"""대시보드 커스텀 CSS — 카드 메트릭, Pretendard 한글 폰트, 정돈된 레이아웃."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


# Inter Latin subset woff2 를 base64 로 inline.
# 17턴 디버깅 끝에 도달한 결론: 모바일에서 외부 웹폰트 다운로드가 불규칙적이라
# 어떤 fallback chain 을 짜도 한글 폰트의 fullwidth ASCII glyph 로 대체되어
# 글자폭이 두 배가 되는 사고가 발생. base64 inline 으로 외부 의존 0 만들면
# CSP / 네트워크 / fallback 어떤 변수도 문제 안 됨.
_INTER_LATIN_B64 = (
    Path(__file__).parent / "fonts" / "inter-latin.woff2.b64"
).read_text().strip()


_FONT_LINKS = """
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
"""


# 한국어 locale 환경에서 브라우저가 ASCII 를 fullwidth glyph 로 자동 substitute
# 하는 것을 차단하기 위해 document lang 을 영어로 설정. translate="no" 까지
# 추가해 자동 번역도 비활성화. iframe 안에서 실행되어 Streamlit 앱 자체의
# documentElement 만 영향 받음.
_BOOT_JS = """
<script>
    document.documentElement.lang = 'en';
    document.documentElement.setAttribute('translate', 'no');

    // 마지막 보루: CSS specificity 게임으로 못 이기는 케이스를 위해 inline
    // style 로 직접 박는다. Streamlit emotion CSS 가 어떻게 강제하든 inline
    // !important 가 다 이긴다. MutationObserver 로 동적 element 도 처리.
    (function() {
        const FEATURES = '"hwid" 1, "pwid" 1, "kern" 1, "tnum" 0, "fwid" 0';
        const VARIANT_EA = 'half-width';
        const SELECTORS = 'p, span, div, h1, h2, h3, h4, h5, h6, td, th, input, button, label, li, a, small, strong, em, b, i';

        function applyTo(root) {
            const target = (root || document);
            // 자기 자신도 처리
            if (target.style && typeof target.style.setProperty === 'function') {
                target.style.setProperty('font-feature-settings', FEATURES, 'important');
                target.style.setProperty('font-variant-east-asian', VARIANT_EA, 'important');
            }
            target.querySelectorAll && target.querySelectorAll(SELECTORS).forEach(el => {
                el.style.setProperty('font-feature-settings', FEATURES, 'important');
                el.style.setProperty('font-variant-east-asian', VARIANT_EA, 'important');
            });
        }

        // 즉시 + DOMContentLoaded + load 단계마다 적용
        applyTo();
        document.addEventListener('DOMContentLoaded', () => applyTo());
        window.addEventListener('load', () => applyTo());
        // 안전망: Streamlit hot reload 등으로 시점이 늦은 경우 대비
        setTimeout(() => applyTo(), 500);
        setTimeout(() => applyTo(), 2000);

        // 동적 element 추가될 때마다 처리. attributes 는 관찰 안 함 → 우리가
        // 박는 inline style 자체가 observer 를 다시 trigger 하는 무한 루프 방지.
        function startObserver() {
            if (!document.body) {
                setTimeout(startObserver, 50);
                return;
            }
            const obs = new MutationObserver(mutations => {
                mutations.forEach(m => {
                    m.addedNodes.forEach(node => {
                        if (node.nodeType === 1) applyTo(node);
                    });
                });
            });
            obs.observe(document.body, { childList: true, subtree: true });
        }
        startObserver();
    })();
</script>
"""


_CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined&family=Material+Symbols+Rounded&display=swap');

/* Inter Latin (subset) — base64 inline. 외부 다운로드 없이 즉시 사용.
   unicode-range 로 ASCII / Latin-Extended 만 매칭. 한글은 시스템 폰트. */
@font-face {
    font-family: 'InterApp';
    src: url(data:font/woff2;base64,___INTER_B64___) format('woff2');
    unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6,
                   U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F,
                   U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215,
                   U+FEFF, U+FFFD;
    font-weight: 100 900;
    font-style: normal;
    font-display: swap;
}

*, *::before, *::after,
[data-testid], [data-testid] *,
[class*="st-emotion-cache"], [class*="st-emotion-cache"] *,
[class*="st-"], [class*="st-"] * {
    /* InterApp 가 ASCII / Latin 을 잡고, 한글은 OS 시스템 폰트로 자동 fallback.
       universal selector 만으로는 Streamlit emotion CSS 의 font-feature-settings:
       normal / font-variant-east-asian: normal 을 못 이김 (DevTools 진단으로
       확인). attribute selector ([data-testid], [class*=...]) 를 같이 둬서
       specificity 보강. */
    font-family: 'InterApp',
                 system-ui, -apple-system, BlinkMacSystemFont,
                 "Segoe UI", "Helvetica Neue", Arial,
                 "Apple SD Gothic Neo", "Noto Sans KR",
                 "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji",
                 sans-serif !important;
    letter-spacing: 0 !important;
    word-spacing: 0 !important;
    font-variant-numeric: proportional-nums lining-nums !important;
    font-variant-east-asian: half-width !important;
    -webkit-font-feature-settings: "hwid" 1, "pwid" 1, "kern" 1, "tnum" 0, "fwid" 0 !important;
    -moz-font-feature-settings: "hwid" 1, "pwid" 1, "kern" 1, "tnum" 0, "fwid" 0 !important;
    font-feature-settings: "hwid" 1, "pwid" 1, "kern" 1, "tnum" 0, "fwid" 0 !important;
}

/* 이모지를 컬러로 렌더 (CSS4) */
* { font-variant-emoji: emoji; }

/* ---- st.metric value 의 폭 강제 해제 (숫자 흩어짐 fix) ----
   진짜 원인이었던 것: column 레이아웃에서 메트릭 카드가 좁아질 때 metric value
   내부 box 가 컨테이너 너비에 맞춰 글자를 균등 분배 (text-align justify 효과).
   letter-spacing 은 'normal' 로 잡혀 있어 자간 fix 가 무력했던 이유.
   해결: width 자동 + max-content 로 글자가 자연스러운 폭만 차지하게 + nowrap
   으로 분배 차단. */
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] [data-testid="stMarkdownContainer"],
[data-testid="stMetricValue"] p,
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] [data-testid="stMarkdownContainer"],
[data-testid="stMetricDelta"] p,
[data-testid="stMetricDelta"] div {
    width: auto !important;
    min-width: max-content !important;
    max-width: none !important;
    white-space: nowrap !important;
    overflow: visible !important;
}

[data-testid="stMetricValue"] p,
[data-testid="stMetricDelta"] p {
    font-variant-numeric: normal !important;
    font-feature-settings: normal !important;
}

/* caption 텍스트도 같은 분배 효과로 흩어지므로 text-align 명시 + word-spacing
   reset. caption 은 줄바꿈이 가능해야 자연스러우니 white-space 는 normal 유지. */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] *,
small {
    text-align: left !important;
    word-spacing: normal !important;
    letter-spacing: normal !important;
    font-variant-numeric: normal !important;
    font-feature-settings: normal !important;
}

/* ---- Material Symbols 아이콘 ---- */
/* 글로벌 font-family !important 룰이 아이콘 폰트를 덮어버려 ligature 텍스트
   (예: keyboard_double_arrow_right) 가 그대로 노출되는 걸 방지. */
[data-testid="stIconMaterial"],
span.material-symbols-rounded,
span.material-symbols-outlined,
span.material-icons,
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons {
    font-family: 'Material Symbols Rounded',
                 'Material Symbols Outlined',
                 'Material Icons' !important;
    font-weight: normal !important;
    font-style: normal !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    line-height: 1 !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: 'liga' !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-smoothing: antialiased;
    font-variant-emoji: text !important;
}

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

/* ---- 좁은 데스크탑 (sidebar + 4-column 메트릭이 좁아지는 구간) ---- */
@media (min-width: 769px) and (max-width: 1366px) {
    [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;  /* 1.65 → 1.25, column 폭 안에 들어가도록 */
    }
    [data-testid="stMetric"] {
        padding: 0.75rem 0.85rem !important;
    }
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
    """앱 부팅 시 1회 호출 — 전체 화면에 커스텀 CSS 적용.

    렌더 순서:
    1. _BOOT_JS  — document.lang='en' 으로 한글 locale 의 fullwidth ASCII
       substitute 차단 (이게 가장 결정적인 것일 수도)
    2. _FONT_LINKS — preconnect 만 (실제 폰트는 base64 inline)
    3. _CUSTOM_CSS — base64 InterApp + half-width 강제 + 전체 스타일
    """
    css = _CUSTOM_CSS.replace("___INTER_B64___", _INTER_LATIN_B64)
    st.markdown(_BOOT_JS, unsafe_allow_html=True)
    st.markdown(_FONT_LINKS, unsafe_allow_html=True)
    st.markdown(css, unsafe_allow_html=True)
