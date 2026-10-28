"""表現の表示・登録・編集の部品（検索・表現帳・復習・ホームの画面で共通に使う）"""
import html
import re

import pandas as pd
import streamlit as st

import speech
import storage
from common import today_jst
from textutil import normalize_en

PAGE_SIZE = 20  # 一覧を一度に出す件数


def md_escape(text: str) -> str:
    """ボタンの文字（Markdown）として、記号がそのまま表示されるようにする"""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~<>$])", r"\\\1", str(text))


def short(text: str, n: int = 28) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def label(e: pd.Series) -> str:
    """一覧のボタンの文字（例：**look into**　調べる）"""
    return f"**{md_escape(e['英語'])}**　{md_escape(short(e['日本語訳']))}"


def tags_of(e: pd.Series) -> list[str]:
    return [t.strip() for t in str(e["タグ"]).split(storage.TAG_SEP) if t.strip()]


def all_tags(expressions: pd.DataFrame) -> list[str]:
    tags = expressions["タグ"].str.split(storage.TAG_SEP).explode().dropna().str.strip() if not expressions.empty else []
    return sorted({t for t in tags if t})


# ---------- 表示 ----------

def detail(e: pd.Series, show_schedule: bool = True) -> None:
    """1つの表現をカードで表示し、単語と例文の再生ボタンを付ける"""
    esc = lambda s: html.escape(str(s))  # noqa: E731
    meta = " · ".join(esc(x) for x in [e["品詞"], e["出典"], *tags_of(e)] if x)
    parts = [
        f"<div class='ex-en'>{esc(e['英語'])}</div>",
        f"<div class='ex-ja'>{esc(e['日本語訳'])}</div>",
    ]
    if e["例文"]:
        parts.append(f"<div class='ex-sentence'>{esc(e['例文'])}</div>")
    if e["例文訳"]:
        parts.append(f"<div class='ex-sub'>{esc(e['例文訳'])}</div>")
    if e["メモ"]:
        parts.append(f"<div class='ex-memo'>📝 {esc(e['メモ'])}</div>")
    if meta:
        parts.append(f"<div class='ex-meta'>{meta}</div>")
    if show_schedule and e.get("次回復習日"):
        parts.append(f"<div class='ex-meta'>次回の復習：{e['次回復習日']}（復習{e['復習回数']}回）</div>")
    st.html(f"<div class='ex-card'>{''.join(parts)}</div>")
    speech.buttons([("単語", e["英語"]), ("例文", e["例文"])])


def item_list(df: pd.DataFrame, key: str, on_pick, caption: str | None = None) -> None:
    """表現のボタン一覧（もっと見る付き）。押すと on_pick(ID) が呼ばれる"""
    if caption:
        st.caption(caption)
    limit = st.session_state.get(f"{key}_limit", PAGE_SIZE)
    for expr_id, e in df.head(limit).iterrows():
        st.button(label(e), key=f"{key}_pick_{expr_id}", on_click=on_pick, args=(expr_id,), width="stretch")
    if len(df) > limit:
        st.button(
            f"もっと見る（残り{len(df) - limit}件）", key=f"{key}_more", width="stretch",
            on_click=lambda: st.session_state.update({f"{key}_limit": limit + PAGE_SIZE}),
        )


# ---------- 登録・編集 ----------

def _form_version(key: str) -> int:
    return st.session_state.setdefault(f"{key}_ver", 0)


def reset_form(key: str) -> None:
    """フォームを空（または新しい初期値）の状態で作り直す"""
    st.session_state[f"{key}_ver"] = _form_version(key) + 1
    st.session_state.pop(f"{key}_pending", None)


def duplicates(expressions: pd.DataFrame, english: str, exclude_id: str | None = None) -> pd.DataFrame:
    """同じ英語（大文字小文字・スペースの違いは無視）で登録済みの表現"""
    if expressions.empty:
        return expressions
    same = expressions["英語"].map(normalize_en) == normalize_en(english)
    return expressions[same & (expressions["ID"] != exclude_id)]


def _save(key: str, values: dict, expr_id: str | None) -> None:
    if expr_id:
        storage.update_expression(expr_id, values)
        st.session_state["message"] = f"「{values['英語']}」を保存しました"
    else:
        storage.add_expressions([storage.new_expression(values, today_jst())])
        st.session_state["message"] = f"「{values['英語']}」を登録しました。続けて登録できます"
        st.session_state["last_source"] = values["出典"]
    st.session_state.pop("prefill", None)
    reset_form(key)


def editor(key: str, expressions: pd.DataFrame, initial: dict | None = None, expr_id: str | None = None, on_saved=None) -> None:
    """表現の登録（expr_id なし）・編集（expr_id あり）のフォーム"""
    initial = initial or {}
    v = _form_version(key)
    sources = storage.SOURCES
    default_source = initial.get("出典") or st.session_state.get("last_source", sources[0])
    existing_tags = all_tags(expressions)
    initial_tags = [t.strip() for t in str(initial.get("タグ", "")).split(storage.TAG_SEP) if t.strip()]

    with st.form(f"{key}_form_{v}", border=True):
        english = st.text_input("英語（必須）", value=initial.get("英語", ""), placeholder="例：look into")
        japanese = st.text_input("日本語訳（必須）", value=initial.get("日本語訳", ""), placeholder="例：調べる")
        example = st.text_area("例文", value=initial.get("例文", ""), height=80, placeholder="例：We will look into the matter.")
        example_ja = st.text_area("例文の訳", value=initial.get("例文訳", ""), height=80, placeholder="例：その件を調べます。")
        col1, col2 = st.columns(2)
        pos_options = storage.PARTS_OF_SPEECH
        pos = col1.selectbox(
            "品詞", pos_options, index=pos_options.index(initial["品詞"]) if initial.get("品詞") in pos_options else 0,
            format_func=lambda p: p or "（なし）",
        )
        source = col2.selectbox("出典", sources, index=sources.index(default_source) if default_source in sources else len(sources) - 1)
        memo = st.text_area(
            "メモ（音のつながり・弱形など）", value=initial.get("メモ", ""), height=68,
            placeholder="例：look into はつながって「ルッキントゥ」",
        )
        tags = st.multiselect(
            "タグ", sorted(set(existing_tags) | set(initial_tags)), default=initial_tags, accept_new_options=True,
            placeholder="選ぶか、新しいタグを入力", help="例：Part3、会議、ビジネス",
        )
        submitted = st.form_submit_button("保存する" if expr_id else "登録する", type="primary", width="stretch")

    if submitted:
        values = {
            "英語": english.strip(), "日本語訳": japanese.strip(), "例文": example.strip(), "例文訳": example_ja.strip(),
            "品詞": pos, "出典": source, "メモ": memo.strip(), "タグ": storage.TAG_SEP.join(t.strip() for t in tags if t.strip()),
        }
        if not values["英語"] or not values["日本語訳"]:
            st.error("英語と日本語訳を入れてください")
            return
        if not duplicates(expressions, values["英語"], expr_id).empty:
            st.session_state[f"{key}_pending"] = values  # 重複していることを知らせて、確認してから保存する
        else:
            _save(key, values, expr_id)
            if on_saved:
                on_saved()
            st.rerun()

    pending = st.session_state.get(f"{key}_pending")
    if pending:
        dup = duplicates(expressions, pending["英語"], expr_id)
        names = "、".join(f"「{a}」（{b}）" for a, b in dup[["英語", "日本語訳"]].values)
        st.warning(f"同じ英語がすでに登録されています：{names}。それでも登録しますか？")
        col1, col2 = st.columns(2)
        if col1.button("登録する", key=f"{key}_dup_ok", type="primary", width="stretch"):
            _save(key, pending, expr_id)
            if on_saved:
                on_saved()
            st.rerun()
        if col2.button("やめる", key=f"{key}_dup_cancel", width="stretch"):
            st.session_state.pop(f"{key}_pending", None)
            st.rerun()
