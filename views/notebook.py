"""📒 表現帳画面：登録・一括登録・一覧（編集・削除）

  st.session_state["notebook_mode"] … 「＋ 登録」「📷 写真」「一括登録」「一覧」
  st.session_state["prefill"]       … 検索画面・写真モードから渡された登録の初期値
  st.session_state["nb_selected"]   … 一覧で選んだ表現のID
  st.session_state["nb_editing"]    … 選んだ表現を編集中かどうか
"""
import csv
import io

import pandas as pd
import streamlit as st

import storage
from common import today_jst
from textutil import normalize_en
from views import expression, photo

PAGE_LABEL = "📒 表現帳"
MODES = ["＋ 登録", "📷 写真", "一括登録", "一覧"]
SORTS = {"新しい順": ("登録日", False), "古い順": ("登録日", True), "復習日が近い順": ("次回復習日", True), "ABC順": ("英語", True)}

# 一括登録の見出しとして受け付ける名前
HEADER_NAMES = {
    "英語": ["英語", "english", "単語", "フレーズ", "表現"],
    "日本語訳": ["日本語訳", "日本語", "訳", "意味", "japanese"],
    "例文": ["例文", "example", "sentence"],
    "例文訳": ["例文訳", "例文の訳", "和訳", "translation"],
    "品詞": ["品詞", "pos"],
    "出典": ["出典", "source", "教材"],
    "メモ": ["メモ", "memo", "note"],
    "タグ": ["タグ", "tag", "tags"],
}


# ---------- 状態の操作 ----------

def _pick(expr_id: str) -> None:
    st.session_state["nb_selected"] = expr_id
    st.session_state["nb_editing"] = False


def _back() -> None:
    st.session_state["nb_selected"] = None
    st.session_state["nb_editing"] = False


def _delete(expr_id: str, english: str) -> None:
    storage.delete_expression(expr_id)
    st.session_state["message"] = f"「{english}」を削除しました"
    _back()


# ---------- 一括登録 ----------

def guess_source(text: str) -> str:
    """出典の書き方の違いを吸収する（例：D2000 → Distinction 2000、公式問題集 → TOEIC公式）"""
    t = text.strip().lower()
    if not t:
        return ""
    if "2000" in t:
        return "Distinction 2000"
    if "distinction" in t or t in ("d1", "distinction1"):
        return "Distinction 1"
    if "公式" in t or "toeic" in t:
        return "TOEIC公式"
    if "記事" in t or "article" in t or "news" in t:
        return "記事"
    return "その他"


def parse_table(text: str) -> pd.DataFrame:
    """貼り付けた表（TSV か CSV）を表現の列に直す。1行目が見出しなら名前で、なければ列の順番で読む"""
    text = text.strip("\n")
    if not text.strip():
        return pd.DataFrame(columns=storage.INPUT_COLUMNS)
    delimiter = "\t" if "\t" in text else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    header = [c.strip().lower() for c in rows[0]]
    mapping = {}
    for col, names in HEADER_NAMES.items():
        for i, h in enumerate(header):
            if h in names and i not in mapping.values():
                mapping[col] = i
                break
    if "英語" in mapping:  # 見出し行あり
        rows = rows[1:]
    else:
        mapping = {col: i for i, col in enumerate(storage.INPUT_COLUMNS)}
    data = [{col: (r[i].strip() if i < len(r) else "") for col, i in mapping.items()} for r in rows]
    df = pd.DataFrame(data, columns=storage.INPUT_COLUMNS).fillna("")
    df["出典"] = df["出典"].map(guess_source)
    df["タグ"] = df["タグ"].str.replace(r"\s*[,、/／]\s*", storage.TAG_SEP, regex=True)
    df["品詞"] = df["品詞"].where(df["品詞"].isin(storage.PARTS_OF_SPEECH), "その他").where(df["品詞"] != "", "")
    return df


def check_rows(df: pd.DataFrame, expressions: pd.DataFrame) -> pd.Series:
    """各行の状態（新規・重複・入力不足）"""
    registered = set(expressions["英語"].map(normalize_en)) if not expressions.empty else set()
    seen = set()
    states = []
    for _, r in df.iterrows():
        key = normalize_en(r["英語"])
        if not key or not r["日本語訳"]:
            states.append("⚠️ 英語か訳がない")
        elif key in registered:
            states.append("🔁 登録済み")
        elif key in seen:
            states.append("🔁 貼り付け内で重複")
        else:
            states.append("🆕 新規")
        seen.add(key)
    return pd.Series(states, index=df.index)


def _bulk(expressions: pd.DataFrame) -> None:
    st.caption(
        "Excel・スプレッドシートからコピーした表（タブ区切り）か、カンマ区切り（CSV）を貼り付けてください。"
        "1行目に見出し（英語・日本語訳・例文・例文訳・品詞・出典・メモ・タグ）があれば名前で読み取り、"
        "見出しがなければこの順番の列として読み取ります。"
    )
    st.code("英語\t日本語訳\t例文\t例文訳\t品詞\t出典\tメモ\tタグ\nlook into\t調べる\tWe will look into it.\tそれを調べます。\t句動詞\tDistinction 2000\t\t会議", language=None)
    text = st.text_area("ここに貼り付け", key="bulk_text", height=180)
    if not text.strip():
        return
    df = parse_table(text)
    if df.empty:
        st.warning("読み取れる行がありませんでした")
        return
    default_source = st.selectbox("出典が空の行の出典", storage.SOURCES, key="bulk_source")
    df["出典"] = df["出典"].replace("", default_source)
    df.insert(0, "状態", check_rows(df, expressions))

    counts = df["状態"].value_counts()
    st.markdown(" ／ ".join(f"{k}：**{v}件**" for k, v in counts.items()))
    st.dataframe(df, hide_index=True, width="stretch", height=min(400, 38 + 35 * len(df)))

    duplicated = df["状態"].str.startswith("🔁")
    include_dup = False
    if duplicated.any():
        st.warning(f"重複が{duplicated.sum()}件あります（上の表の 🔁）。ふつうは登録せずに飛ばします。")
        include_dup = st.checkbox("重複しているものも登録する", key="bulk_include_dup")
    target = df[df["状態"].eq("🆕 新規") | (duplicated & include_dup)]
    st.button(
        f"{len(target)}件を登録する", type="primary", width="stretch", disabled=target.empty,
        on_click=_register_bulk, args=(target[storage.INPUT_COLUMNS].to_dict("records"),),
    )


def _register_bulk(records: list[dict]) -> None:
    today = today_jst()
    storage.add_expressions([storage.new_expression(r, today) for r in records])
    st.session_state["message"] = f"{len(records)}件を登録しました"
    st.session_state["bulk_text"] = ""  # 貼り付け欄を空にする（ボタンの on_click の中なので変更できる）


# ---------- 一覧 ----------

def _list(expressions: pd.DataFrame) -> None:
    selected = st.session_state.get("nb_selected")
    if selected and selected in expressions.index:
        e = expressions.loc[selected]
        st.button("↩ 一覧に戻る", key="nb_back", on_click=_back)
        if st.session_state.get("nb_editing"):
            expression.editor(f"nb_edit_{selected}", expressions, initial=e.to_dict(), expr_id=selected, on_saved=_back)
            return
        expression.detail(e)
        col1, col2 = st.columns(2)
        col1.button("✏️ 編集", width="stretch", on_click=lambda: st.session_state.update(nb_editing=True))
        with col2.popover("🗑️ 削除", width="stretch"):
            st.write(f"「{e['英語']}」を削除しますか？")
            st.button("削除する", type="primary", key="nb_delete", on_click=_delete, args=(selected, e["英語"]), width="stretch")
        return

    if expressions.empty:
        st.info("まだ表現が登録されていません。「＋ 登録」か「一括登録」から登録してください。")
        return
    with st.expander("絞り込み・並び順"):
        sources = st.multiselect("出典", storage.SOURCES, key="nb_sources", placeholder="すべて")
        tags = st.multiselect("タグ", expression.all_tags(expressions), key="nb_tags", placeholder="すべて")
        sort = st.segmented_control("並び順", list(SORTS), key="nb_sort", default="新しい順", required=True)
    df = expressions
    if sources:
        df = df[df["出典"].isin(sources)]
    if tags:
        df = df[df["タグ"].map(lambda t: any(x in t.split(storage.TAG_SEP) for x in tags))]
    column, ascending = SORTS[sort or "新しい順"]
    df = df.assign(_order=range(len(df))).sort_values([column, "_order"], ascending=[ascending, ascending], na_position="first")
    with st.container(key="list_notebook"):  # この中のボタンは左寄せ（app.py のCSS）
        expression.item_list(df, "nb_list", _pick, caption=f"{len(df)}件")


def render() -> None:
    expressions = storage.load_expressions()
    st.session_state.setdefault("notebook_mode", MODES[0])
    mode = st.segmented_control(
        "表現帳", MODES, key="notebook_mode", required=True, label_visibility="collapsed", width="stretch",
    )
    if mode == "＋ 登録":
        prefill = st.session_state.get("prefill")
        if prefill and prefill.get("例文") and not prefill.get("英語"):
            st.caption("写真の文を例文に入れました。覚えたい表現（英語）と日本語訳を入れて登録してください。")
        elif prefill:
            st.caption("検索した内容を入れました。例文やメモを足して登録してください。")
        expression.editor("nb_add", expressions, initial=prefill)
    elif mode == "📷 写真":
        photo.render()
    elif mode == "一括登録":
        _bulk(expressions)
    else:
        _list(expressions)
