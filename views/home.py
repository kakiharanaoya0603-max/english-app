"""🏠 ホーム画面：今日の復習数・残り数・登録数・連続学習日数"""
import streamlit as st

import srs
import storage
from common import cards, go, today_jst
from views import expression

PAGE_LABEL = "🏠 ホーム"


def render() -> None:
    expressions = storage.load_expressions()
    logs = storage.load_logs()
    today = today_jst()

    remaining = len(srs.due(expressions, today))
    cards([
        ("今日の復習", str(srs.reviewed_today(logs, today)), "語"),
        ("残り", str(remaining), "語"),
        ("登録数", str(len(expressions)), "語"),
        ("連続学習", str(srs.streak(logs, today)), "日"),
    ])

    if expressions.empty:
        st.info("まずは「📒 表現帳」から、教材で拾った単語・表現を登録しましょう。")
        st.button("＋ 表現を登録する", type="primary", width="stretch", on_click=go, args=("📒 表現帳",), kwargs={"notebook_mode": "＋ 登録"})
        return
    if remaining:
        st.button(f"🧠 復習をはじめる（残り{remaining}語）", type="primary", width="stretch", on_click=go, args=("🧠 復習",))
    else:
        st.success("今日の復習は終わりました 🎉")

    st.caption("最近登録した表現")
    recent = expressions.iloc[::-1].head(5)
    with st.container(key="list_home"):
        expression.item_list(
            recent, "home_recent",
            lambda i: go("📒 表現帳", notebook_mode="一覧", nb_selected=i, nb_editing=False),
        )
