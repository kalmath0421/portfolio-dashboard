"""대시보드 커스텀 CSS — 카드 메트릭, Pretendard 한글 폰트, 정돈된 레이아웃."""
from __future__ import annotations

import streamlit as st


_CUSTOM_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
/* Inter 공식 CDN (Rasmus Andersson) — Google Fonts 의 unicode-range 쪼개기
   우회. 합성 볼드 차단. */
@import url('https://rsms.me/inter/inter.css');
/* 라운드 34: Roboto Condensed 백업. */
@import url('https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@400;700&display=swap');
/* 라운드 37: Oswald — Roboto Condensed 보다 더 극단적으로 narrow. 디스플레이용
   폰트로 디자인되어 있어 메트릭 카드 같은 large display 텍스트에 적합.
   letter-spacing -0.1em 으로도 시각 변화 미미했던 라운드 36 결과로, 글리프
   자체가 narrow 한 폰트가 필요하다는 결론. */
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined&family=Material+Symbols+Rounded&display=swap');

/* 글로벌 폰트 룰 — DevTools Rendered Fonts 진단으로 확정된 것:
   Pretendard-Bold 의 ASCII glyph 가 wide 하게 디자인되어 있어 숫자가 흩어진
   것처럼 보임. font-family 순서를 'Inter' 우선으로 바꿔 ASCII/Latin 은 Inter
   로, 한글은 Inter 에 글리프 없으니 자동으로 Pretendard 로 fallback.
   emotion 클래스 보강도 유지해야 modern Streamlit 에서 룰이 적용됨. */
html, body,
[class*="css"], [class*="st-emotion"], [class*="emotion-cache"],
button, input, textarea, select,
[data-testid="stSidebar"] *, [data-testid="stMetric"] *,
[data-testid] p, [data-testid] span, [data-testid] div, [data-testid] label,
h1, h2, h3, h4, h5, h6, p, span, div, label {
    font-family: 'Inter', 'Pretendard',
                 -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 'Apple SD Gothic Neo', 'Noto Sans KR',
                 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji',
                 'Segoe UI Symbol', sans-serif !important;
    letter-spacing: -0.01em;
    /* fullwidth 강제를 명시적으로 끔. proportional widths 강제. */
    font-feature-settings: 'pwid' 1, 'fwid' 0, 'tnum' 0, 'kern' 1 !important;
    font-variant-east-asian: normal !important;
    font-stretch: normal !important;
    /* lang="ko" 환경에서 숫자/쉼표가 한글과 어울리려고 임의로 벌어지는 현상 차단. */
    word-break: keep-all !important;
    /* synthetic bold/italic 차단. Inter weight 매칭 실패 시 브라우저가
       Regular 을 강제로 굵게 만드는 (synthetic-bold) 것을 막음 — advance 가
       망가져 wide 처럼 보이는 사고 방지. */
    font-synthesis: none !important;
    -webkit-text-size-adjust: 100% !important;
    text-size-adjust: 100% !important;
}

/* 이모지를 컬러로 렌더 (CSS4) */
* { font-variant-emoji: emoji; }

/* ---- 메트릭 전용 폰트/weight 강제 (라운드 26 Gemini 보강) ----
   Streamlit emotion CSS 가 inner element 에 'font-weight: 600' 같은 애매한
   weight 를 박으면, 우리가 부모에 700 을 걸어도 자식이 600 을 요구하는 사고가
   생김. 600 weight woff2 가 없으면 합성 볼드 발생. → descendants(*) 까지
   font-weight: 700 을 명시 강제해 자식 element 의 weight 미스매치를 차단. */
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] *,
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] * {
    font-family: 'Inter', 'Pretendard', sans-serif !important;
    font-weight: 700 !important;
    font-synthesis: none !important;
}

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

/* ⚠️ 자기모순 수정 (Gemini 진단):
   기존엔 글로벌 룰의 pwid/fwid 설정을 메트릭에서 normal 로 리셋해 버려
   "fwid 0" 강제가 풀리고 → 자릿수가 다시 전각으로 흩어졌음. 정확히 그
   리셋이 흩어짐을 만든 자살골이었던 것.
   대신: tabular-nums 를 명시 + pwid/fwid 를 그대로 강제 + tnum 켜서
   숫자 폭 동일화. letter-spacing 도 normal 로 (글로벌 -0.01em 무력화). */
[data-testid="stMetricValue"] p,
[data-testid="stMetricDelta"] p {
    font-variant-numeric: tabular-nums lining-nums !important;
    font-feature-settings: 'pwid' 1, 'fwid' 0, 'tnum' 1, 'kern' 1 !important;
    letter-spacing: normal !important;
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
   (예: keyboard_double_arrow_right, arrow_left) 가 그대로 노출되는 걸 방지.
   ⚠️ specificity 주의: 글로벌 룰의 `[data-testid] span` 은 specificity 11
   (속성+요소). `[data-testid="stIconMaterial"]` 단독은 10 이라 글로벌이 이김 →
   아이콘이 글로벌 Inter 폰트로 떨어져 ligature 가 풀리는 사고. 따라서 모든 아이콘
   selector 에 element 또는 추가 selector 를 붙여 specificity ≥ 11 로 끌어올림. */
body [data-testid="stIconMaterial"],
span[data-testid="stIconMaterial"],
[data-testid="stSidebarCollapseButton"] span,
[data-testid="stExpandSidebarButton"] span,
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
    /* 위에서 글로벌로 'pwid'/'fwid' 를 강제했지만 아이콘은 ligature 가 핵심
       이라 'liga' 1 만 켜야 함. 명시적으로 다시 적용. */
    -webkit-font-feature-settings: 'liga' 1 !important;
    font-feature-settings: 'liga' 1 !important;
    font-variant-east-asian: normal !important;
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

/* ---- 커스텀 메트릭 카드 (Plan B — ui_components.metric) ----
   st.metric 의 stMetric/stMetricValue 가 emotion CSS + baseweb wrapper 로
   라틴 글리프를 wide 하게 그리는 사고 (라운드 26 까지 abandon) 를 피하기 위해
   HTML 마크다운으로 직접 렌더. 핵심 폰트 속성은 ui_components.metric 에서
   inline style 로 박아 어떤 외부 CSS 도 안 닿음. 여기 CSS 는 단순 외형만. */
.cm-metric {
    background: linear-gradient(135deg, #1A1F2C 0%, #14171F 100%);
    border: 1px solid #232936;
    border-radius: 14px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02) inset,
                0 4px 12px rgba(0, 0, 0, 0.25);
    transition: transform 0.15s ease, border-color 0.15s ease;
    margin-bottom: 0.5rem;
}
.cm-metric:hover {
    border-color: #F5A623;
    transform: translateY(-1px);
}
.cm-label {
    color: #94A3B8;
    font-size: 0.82rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    margin-bottom: 0.4rem;
}
/* cm-value 는 색·크기·무게만. 폰트는 내부 .cm-latin / .cm-hangul span 이 결정.
   (한 노드에 ASCII + 한글이 섞이지 않도록 ui_components._split_by_script 에서
   span 분리 → Chrome CJK text shaper 의 전각폭 강제 회피.) */
.cm-value {
    color: #F1F5F9;
    font-size: 1.65rem;
    font-weight: 700;
    line-height: 1.25;
    white-space: nowrap;
}
.cm-delta {
    font-size: 0.85rem;
    font-weight: 600;
    margin-top: 0.25rem;
    white-space: nowrap;
}

/* ---- 라운드 32: 인라인 style 무력화 우회 ----
   라운드 28~31 동안 ui_components 가 span 에 inline style 을 박았는데
   DevTools Computed 가 글로벌 룰 값을 표시 (= inline 이 적용 안 됨).
   Streamlit markdown 의 sanitizer 가 style 속성을 strip 하는 것으로 추정.
   해법: inline 을 버리고 .cm-latin / .cm-hangul 클래스 + 고 specificity
   selector 로 재구성. .cm-value .cm-latin = specificity 20, 글로벌 룰의
   [data-testid] span (11) 을 깔끔히 이김. */
.cm-value .cm-latin,
.cm-delta .cm-latin {
    /* 라운드 37+38: Oswald 1순위 + 합성 볼드 제거.
       라운드 37 후 Rendered Fonts 에 'Oswald-Regular_Bold' 표시 — Bold (700)
       weight 가 매핑 실패해 Regular 을 합성. Inter 때와 같은 패턴.
       해법: .cm-value 의 font-weight: 700 을 .cm-latin 에서 500 으로 강제
       오버라이드. Oswald Medium (500) 은 정확 로드되므로 합성 불필요. 시각적
       으로도 500 자체가 충분히 두꺼움 (Oswald 디자인 자체가 condensed display). */
    font-family: 'Oswald',
                 'Roboto Condensed',
                 -apple-system, BlinkMacSystemFont,
                 'Segoe UI', sans-serif !important;
    font-weight: 500 !important;  /* 라운드 38: 합성 볼드 차단 */
    font-variant-numeric: proportional-nums lining-nums !important;
    font-feature-settings: 'pwid' 1, 'fwid' 0, 'pnum' 1, 'tnum' 0,
                           'kern' 1, 'liga' 1 !important;
    font-synthesis: none !important;
    letter-spacing: -0.02em !important;
    font-variant-east-asian: normal !important;
    font-stretch: normal !important;
    font-kerning: normal !important;
    text-rendering: optimizeLegibility !important;
}
.cm-value .cm-hangul,
.cm-delta .cm-hangul {
    font-family: 'Pretendard', 'Apple SD Gothic Neo',
                 'Noto Sans KR', sans-serif !important;
    font-synthesis: none !important;
    letter-spacing: normal !important;
}
.cm-up { color: #22C55E; }
.cm-down { color: #EF4444; }
.cm-flat { color: #94A3B8; }
.cm-help {
    cursor: help;
    color: #7E8895;
    font-size: 0.75rem;
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

/* ---- 모바일/태블릿 (1024px 이하) ---- */
/* 라운드 40: 라운드 39 의 768px breakpoint 가 사용자 device (태블릿/큰폰
   ~1024px) 에 안 잡힘. 1024px 까지로 broader. 9자리 숫자가 들어갈 수 있는
   카드 너비 확보가 핵심이므로 조금 큰 화면도 stacking 으로 처리. */
@media (max-width: 1024px) {
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

    /* st.columns 강제 stacking — 다중 selector 로 Streamlit 버전 호환성 확보.
       display: flex 도 명시 (혹시 block 으로 떨어진 경우 대비). */
    [data-testid="stHorizontalBlock"],
    div[class*="HorizontalBlock"],
    div.row-widget.stHorizontal {
        display: flex !important;
        flex-direction: column !important;
        gap: 0.5rem !important;
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"] > [data-testid="column"],
    [data-testid="stHorizontalBlock"] > div,
    div[class*="HorizontalBlock"] > div {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* 카드 폰트 — full width 확보됐으니 좀 키워도 OK */
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
    }
    [data-testid="stMetric"] {
        padding: 0.85rem 1rem !important;
    }
    .cm-value { font-size: 1.4rem !important; }
    .cm-metric { padding: 0.85rem 1rem !important; }

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
