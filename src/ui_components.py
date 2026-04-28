"""HTML 기반 커스텀 메트릭 카드 (Plan B — 폰트 라운드 27).

st.metric 은 Streamlit 의 stMetric/stMetricValue 컴포넌트를 거치는데,
emotion CSS 와 baseweb wrapper 가 라틴 글리프를 wide 하게 렌더링하는 사고
(라운드 26까지 추적, abandon) 를 피하기 위해 직접 HTML 로 렌더한다.

핵심 폰트 속성은 **inline style + !important** 로 박아서:
- 우리 글로벌 룰의 `!important` 도 덮어씀 (specificity 1010+)
- Streamlit 의 어떤 emotion CSS 도 안 닿음
- 결과: Inter 폰트가 100% 보장되어 합성 볼드/wide 글리프 사고가 원천 차단됨

st.metric 과 인자/시각이 호환되어 drop-in 대체 가능.
"""
from __future__ import annotations

import html as _html

import streamlit as st


# 인라인 스타일 — 핵심 폰트 속성을 !important 로 박아 외부 CSS 차단.
# (다음 줄들은 모두 `;` 로 구분된 한 줄 문자열로 합쳐져 element 의 style 속성에 들어감)
_FONT_INLINE = (
    "font-family: 'Inter', 'Pretendard', sans-serif !important;"
    " font-feature-settings: 'tnum' 1, 'pwid' 1, 'fwid' 0, 'kern' 1 !important;"
    " font-variant-numeric: tabular-nums lining-nums !important;"
    " font-synthesis: none !important;"
    " letter-spacing: normal !important;"
    " white-space: nowrap !important;"
)


def _delta_class(delta_str: str, delta_color: str) -> str:
    """+/− 부호 + delta_color 옵션으로 색상 클래스 결정."""
    s = delta_str.lstrip()
    if s.startswith(("+", "↑")):
        cls = "cm-up"
    elif s.startswith(("-", "↓", "−", "–")):
        cls = "cm-down"
    else:
        cls = "cm-flat"
    if delta_color == "inverse":
        cls = {"cm-up": "cm-down", "cm-down": "cm-up"}.get(cls, cls)
    elif delta_color == "off":
        cls = "cm-flat"
    return cls


def metric(
    label: str,
    value,
    delta=None,
    *,
    delta_color: str = "normal",
    help: str | None = None,
) -> None:
    """st.metric drop-in 대체.

    Args:
        label: 카드 상단 라벨 (그대로 표시).
        value: 큰 숫자/문자열. None 이면 '—'.
        delta: 부호 포함 변화량 ('+1,234 원', '+5.55%' 등). None 이면 미표시.
        delta_color: 'normal'(+녹색/-빨강) / 'inverse'(반대) / 'off'(회색).
        help: 라벨 옆 ⓘ 아이콘 hover tooltip.
    """
    label_html = _html.escape(str(label))
    value_html = _html.escape(str(value)) if value is not None else "—"

    help_html = ""
    if help:
        help_html = (
            f' <span class="cm-help" title="{_html.escape(help)}">ⓘ</span>'
        )

    delta_html = ""
    if delta is not None and str(delta).strip() not in ("", "None"):
        delta_str = str(delta)
        cls = _delta_class(delta_str, delta_color)
        delta_html = (
            f'<div class="cm-delta {cls}" style="{_FONT_INLINE}">'
            f'{_html.escape(delta_str)}</div>'
        )

    st.markdown(
        f'<div class="cm-metric">'
        f'<div class="cm-label">{label_html}{help_html}</div>'
        f'<div class="cm-value" style="{_FONT_INLINE}">{value_html}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
