"""複数の画面で使う小さな関数"""
import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st


def now_jst() -> dt.datetime:
    # 公開先のサーバーは日本時間ではないので、日本時間を明示的に求める
    return dt.datetime.now(ZoneInfo("Asia/Tokyo"))


def today_jst() -> dt.date:
    return now_jst().date()


def go(page: str, **state) -> None:
    """ほかの画面へ移動する（ボタンの on_click の中で呼ぶこと）。state は移動先に渡す session_state の値"""
    st.session_state["page"] = page
    st.session_state.update(state)


def cards(items: list[tuple[str, str, str]]) -> None:
    """数字を、スマホでも横一列に並ぶ小さなカードで表示する。items は (見出し, 値, 単位)"""
    html = "".join(
        f"<div style='flex:1;min-width:0;border:1px solid rgba(128,128,128,.3);border-radius:8px;padding:8px 2px;text-align:center'>"
        f"<div style='font-size:.72rem;opacity:.7;white-space:nowrap'>{label}</div>"
        f"<div style='font-size:1.35rem;font-weight:600'>{value}<span style='font-size:.7rem'> {unit}</span></div></div>"
        for label, value, unit in items
    )
    st.markdown(f"<div style='display:flex;gap:6px;margin-bottom:8px'>{html}</div>", unsafe_allow_html=True)
