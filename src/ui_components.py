"""HTML 기반 커스텀 메트릭 카드 (Plan B — 폰트 라운드 28).

라운드 27 (Plan B / HTML 마크다운) 후에도 디지트 흩어짐 지속.
Gemini 진단: 같은 텍스트 노드 안에 ASCII 숫자 + 한글이 같이 있으면 Chrome
의 CJK text shaper 가 ASCII 까지 전각 폭으로 강제로 늘리는 알려진 동작이
있음. <html lang="ko"> 환경에서 더 두드러짐. 인라인 letter-spacing 조정도
무력 — 셰이퍼 단계는 CSS 보다 먼저 일어남.

라운드 28 해법: HTML 노드 수준에서 Latin 과 Hangul 을 별도 <span> 으로
분리 → 각 노드가 독립된 셰이퍼 컨텍스트를 갖게 됨 → ASCII 글리프가 더 이상
CJK 규칙에 맞춰 늘어나지 않음.

값 예: "728,766,333 원" →
  <span class="cm-latin">728,766,333 </span><span class="cm-hangul">원</span>
"""
from __future__ import annotations

import html as _html
import re

import streamlit as st


# Hangul 음절 + 자모 + 호환 자모 범위. 한자는 별도지만 우리 앱에선 안 씀.
_HANGUL_RE = re.compile(r'[가-힯ᄀ-ᇿ㄰-㆏]+')

# Latin 전용 인라인 — Pretendard 를 fallback chain 에서 완전 제거.
# Inter 가 안 잡히면 시스템 sans (SF Pro / Segoe UI) 로 폴백, 둘 다 디지트
# 폭이 정상이라 Pretendard 의 wide ASCII 가 그려질 여지가 0%.
_LATIN_INLINE = (
    "font-family: 'Inter', -apple-system, BlinkMacSystemFont,"
    " 'Segoe UI', 'Helvetica Neue', sans-serif !important;"
    " font-variant-numeric: tabular-nums lining-nums !important;"
    " font-feature-settings: 'tnum' 1, 'pwid' 1, 'fwid' 0, 'kern' 1 !important;"
    " font-synthesis: none !important;"
    " letter-spacing: normal !important;"
    " font-variant-east-asian: normal !important;"
)

# Hangul 전용 — 한글은 Pretendard 가 가장 정돈되어 있으므로 그대로 사용.
_HANGUL_INLINE = (
    "font-family: 'Pretendard', 'Apple SD Gothic Neo',"
    " 'Noto Sans KR', sans-serif !important;"
    " font-synthesis: none !important;"
    " letter-spacing: normal !important;"
)


def _split_by_script(text: str) -> str:
    """문자열을 Latin / Hangul 단위로 잘라 별도 <span> 으로 wrap.

    CJK text shaper 가 동일 텍스트 노드 안의 ASCII 를 전각으로 강제 늘리는
    Chrome 의 동작을 회피하기 위해, 노드 경계로 셰이퍼 컨텍스트를 분리한다.
    """
    if not text:
        return ""
    pieces: list[str] = []
    last_end = 0
    for m in _HANGUL_RE.finditer(text):
        if m.start() > last_end:
            latin_part = text[last_end:m.start()]
            pieces.append(
                f'<span style="{_LATIN_INLINE}">'
                f'{_html.escape(latin_part)}</span>'
            )
        pieces.append(
            f'<span style="{_HANGUL_INLINE}">'
            f'{_html.escape(m.group())}</span>'
        )
        last_end = m.end()
    if last_end < len(text):
        latin_part = text[last_end:]
        pieces.append(
            f'<span style="{_LATIN_INLINE}">'
            f'{_html.escape(latin_part)}</span>'
        )
    return ''.join(pieces)


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
    # 라벨은 Korean 위주라 분리 안 해도 wide 사고가 안 일어남 (디지트가 거의 없음).
    label_html = _html.escape(str(label))

    # 값은 디지트 + "원" 같은 한글이 섞이는 경우가 대부분 → script 별 분리 필수.
    if value is None:
        value_html = (
            f'<span style="{_LATIN_INLINE}">—</span>'
        )
    else:
        value_html = _split_by_script(str(value))

    help_html = ""
    if help:
        help_html = (
            f' <span class="cm-help" title="{_html.escape(help)}">ⓘ</span>'
        )

    delta_html = ""
    if delta is not None and str(delta).strip() not in ("", "None"):
        delta_str = str(delta)
        cls = _delta_class(delta_str, delta_color)
        delta_inner = _split_by_script(delta_str)
        delta_html = f'<div class="cm-delta {cls}">{delta_inner}</div>'

    st.markdown(
        f'<div class="cm-metric">'
        f'<div class="cm-label">{label_html}{help_html}</div>'
        f'<div class="cm-value">{value_html}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
