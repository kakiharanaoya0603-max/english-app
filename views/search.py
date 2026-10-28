"""🔍 検索画面：マイ表現帳 → 英和辞書（EJDict-hand）の順に探す

  st.session_state["search_query"]    … 検索欄の文字
  st.session_state["search_selected"] … 選んだもの ("expr", 表現ID) / ("dict", 辞書の行番号) / None
"""
import html
import re

import pandas as pd
import streamlit as st

import dictionary
import speech
import storage
from common import go
from textutil import is_english
from views import expression

PAGE_LABEL = "🔍 検索"
DICT_PAGE_SIZE = 15


def _select(kind: str, item_id) -> None:
    st.session_state["search_selected"] = (kind, item_id)


def _unselect() -> None:
    st.session_state["search_selected"] = None


def _clear() -> None:
    st.session_state["search_query"] = ""
    st.session_state["search_selected"] = None


def clean_meaning(meaning: str) -> str:
    """辞書の訳を、表現帳に入れやすい形にする（『』や《+『of』》のような文法の印を取る）"""
    meaning = re.sub(r"《[^》]*\+[^》]*》", "", meaning)
    return re.sub(r"\s+", " ", meaning.replace("『", "").replace("』", "")).strip()


def first_spelling(word: str) -> str:
    return word.split(",")[0].strip()


def _dict_label(row: pd.Series) -> str:
    return f"**{expression.md_escape(row['英語'])}**　{expression.md_escape(expression.short(clean_meaning(row['意味']), 34))}"


def _register_from_dict(row: pd.Series) -> None:
    prefill = {"英語": first_spelling(row["英語"]), "日本語訳": clean_meaning(row["意味"])}
    go("📒 表現帳", prefill=prefill, notebook_mode="＋ 登録")
    expression.reset_form("nb_add")


def _register_new(query: str) -> None:
    prefill = {"英語": query} if is_english(query) else {"日本語訳": query}
    go("📒 表現帳", prefill=prefill, notebook_mode="＋ 登録")
    expression.reset_form("nb_add")


def _edit(expr_id: str) -> None:
    go("📒 表現帳", notebook_mode="一覧", nb_selected=expr_id, nb_editing=True)


def _show_dict_detail(row: pd.Series, expressions: pd.DataFrame) -> None:
    st.html(
        f"<div class='ex-card'><div class='ex-en'>{html.escape(row['英語'])}</div>"
        f"<div class='ex-ja'>{html.escape(clean_meaning(row['意味']))}</div>"
        f"<div class='ex-meta'>📖 英和辞書（EJDict-hand）</div></div>"
    )
    speech.buttons([("発音", first_spelling(row["英語"]))])
    if not expression.duplicates(expressions, first_spelling(row["英語"])).empty:
        st.caption("⭐ この単語はすでに表現帳に登録されています")
    st.button("＋ 表現帳に登録", type="primary", width="stretch", on_click=_register_from_dict, args=(row,))


def render() -> None:
    expressions = storage.load_expressions()
    st.session_state.setdefault("search_selected", None)

    col1, col2 = st.container(key="search_row").columns([5, 1], vertical_alignment="bottom")
    query = col1.text_input(
        "英語・日本語で検索", key="search_query",
        placeholder="例：procure／調達／ちょうたつ",
        help="英語でも日本語（ひらがな・カタカナ・漢字）でも検索できます。自分の表現帳 → 英和辞書の順に出ます",
    )
    col2.button("×", key="search_clear", on_click=_clear, help="検索欄を空にする", width="stretch")
    if st.session_state.get("search_last_query") != query:  # 言葉が変わったら選択と表示件数を戻す
        st.session_state["search_last_query"] = query
        st.session_state["search_selected"] = None
        st.session_state["search_dict_limit"] = DICT_PAGE_SIZE
        st.session_state["search_expr_limit"] = expression.PAGE_SIZE

    selected = st.session_state["search_selected"]
    if selected:
        kind, item_id = selected
        st.button("↩ 一覧に戻る", on_click=_unselect)
        if kind == "expr" and item_id in expressions.index:
            expression.detail(expressions.loc[item_id])
            st.button("✏️ 編集する", width="stretch", on_click=_edit, args=(item_id,))
        elif kind == "dict":
            _show_dict_detail(dictionary.load().loc[item_id], expressions)
        st.caption(dictionary.CREDIT)
        return

    if not query.strip():
        st.caption("英単語・フレーズ・日本語の訳を入れてください。")
        st.caption(dictionary.CREDIT)
        return

    mine = dictionary.search_expressions(expressions, query)
    found = dictionary.search(query)
    if mine.empty and found.empty:
        st.info(f"「{query}」は見つかりませんでした。")
        st.button("＋ 自分で登録する", type="primary", width="stretch", on_click=_register_new, args=(query.strip(),))
        st.caption(dictionary.CREDIT)
        return

    # 候補一覧（選ぶと閉じる。外をタップしても閉じる：speech.py の JavaScript）
    with st.container(key="results_search"):
        if not mine.empty:
            expression.item_list(mine, "search_expr", lambda i: _select("expr", i), caption=f"⭐ マイ表現帳（{len(mine)}件）")
        if not found.empty:
            st.caption(f"📖 英和辞書（{len(found)}件）")
            limit = st.session_state.get("search_dict_limit", DICT_PAGE_SIZE)
            for idx, row in found.head(limit).iterrows():
                st.button(_dict_label(row), key=f"search_dict_{idx}", on_click=_select, args=("dict", idx), width="stretch")
            if len(found) > limit:
                st.button(
                    f"もっと見る（残り{len(found) - limit}件）", key="search_dict_more", width="stretch",
                    on_click=lambda: st.session_state.update(search_dict_limit=limit + DICT_PAGE_SIZE),
                )
        st.button("＋ 自分で登録する", key="search_register", width="stretch", on_click=_register_new, args=(query.strip(),))
    st.caption(dictionary.CREDIT)
