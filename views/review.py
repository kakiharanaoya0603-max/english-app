"""🧠 復習画面（脳内英作文モード）

日本語を見て英語を考える →「答えを見る」→ 音声で確認 →「言えた／あやしい／言えなかった」で自己評価。
評価から次の復習日を決める（srs.py）。英語→日本語の向きにも切り替えられる。

  st.session_state["rv_queue"]    … これから出す表現IDの並び（「言えなかった」は最後にもう一度足す）
  st.session_state["rv_pos"]      … いま何問目か
  st.session_state["rv_revealed"] … 答えを表示中か
  st.session_state["rv_results"]  … この回の評価の記録
"""
import html
import random

import streamlit as st

import speech
import srs
import storage
from common import now_jst, today_jst
from views import expression

PAGE_LABEL = "🧠 復習"
DIRECTIONS = ["日→英", "英→日"]
PROMPTS = ["例文の訳", "表現の訳"]
RANGES = ["今日の分", "すべて"]
SETUP_KEYS = ["rv_direction", "rv_prompt", "rv_range", "rv_sources", "rv_tags"]


def _filtered(expressions, today):
    df = expressions
    if st.session_state.get("rv_range", RANGES[0]) == "今日の分":
        df = srs.due(df, today)
    sources = st.session_state.get("rv_sources") or []
    tags = st.session_state.get("rv_tags") or []
    if sources:
        df = df[df["出典"].isin(sources)]
    if tags:
        df = df[df["タグ"].map(lambda t: any(x in t.split(storage.TAG_SEP) for x in tags))]
    return df


def _start(ids: list[str]) -> None:
    ids = list(ids)
    random.shuffle(ids)
    # 向き・出題の切り替えボタンは復習中は表示しないので（表示しないボタンの値は消える）、別の名前で覚えておく
    st.session_state.update(
        rv_queue=ids, rv_pos=0, rv_revealed=False, rv_results=[],
        rv_active_direction=st.session_state.get("rv_direction") or DIRECTIONS[0],
        rv_active_prompt=st.session_state.get("rv_prompt") or PROMPTS[0],
        rv_kept={k: st.session_state[k] for k in SETUP_KEYS if k in st.session_state},
    )


def _stop() -> None:
    st.session_state.pop("rv_queue", None)


def _reveal() -> None:
    st.session_state["rv_revealed"] = True


def _grade(e, grade: str, direction: str) -> None:
    stage, next_day = srs.next_schedule(int(e["段階"]), grade, today_jst())
    storage.update_expression(e["ID"], {
        "段階": stage, "次回復習日": next_day, "最終復習日": today_jst(), "復習回数": int(e["復習回数"]) + 1,
    })
    storage.add_log(now_jst(), e["ID"], direction, grade)
    if grade == "言えなかった":
        st.session_state["rv_queue"].append(e["ID"])  # この回の最後にもう一度出す
    st.session_state["rv_results"].append(grade)
    st.session_state["rv_pos"] += 1
    st.session_state["rv_revealed"] = False


def _setup(expressions, today) -> None:
    """復習を始める前の画面（向き・絞り込み）"""
    # 前回の復習のときの選択に戻す（はじめてなら初期値）
    kept = {"rv_direction": DIRECTIONS[0], "rv_prompt": PROMPTS[0], "rv_range": RANGES[0], **st.session_state.get("rv_kept", {})}
    for k, v in kept.items():
        st.session_state.setdefault(k, v)
    st.segmented_control("向き", DIRECTIONS, key="rv_direction", required=True, width="stretch")
    if st.session_state.get("rv_direction") == "日→英":
        st.segmented_control(
            "出題", PROMPTS, key="rv_prompt", required=True, width="stretch",
            help="例文の訳：例文の訳を見て英文を言う（例文がない表現は表現の訳を出します）",
        )
    st.segmented_control(
        "範囲", RANGES, key="rv_range", required=True, width="stretch",
        help="今日の分：復習日が今日までのもの／すべて：予定前のものも含めて全部",
    )
    with st.expander("出典・タグで絞り込む"):
        st.multiselect("出典", storage.SOURCES, key="rv_sources", placeholder="すべて")
        st.multiselect("タグ", expression.all_tags(expressions), key="rv_tags", placeholder="すべて")
    targets = _filtered(expressions, today)
    if targets.empty:
        if expressions.empty:
            st.info("まだ表現が登録されていません。「📒 表現帳」から登録してください。")
        else:
            st.success("今日の復習はありません 🎉　範囲を「すべて」にすると、予定前のものも復習できます。")
        return
    st.button(
        f"▶ 復習をはじめる（{len(targets)}件）", type="primary", width="stretch",
        on_click=_start, args=(targets.index.tolist(),),
    )


def _finished() -> None:
    results = st.session_state["rv_results"]
    st.success("おつかれさまでした！")
    st.markdown("　".join(f"{g}：**{results.count(g)}**" for g in srs.GRADES))
    st.button("戻る", type="primary", width="stretch", on_click=_stop)


def _card(e, direction: str, prompt_kind: str) -> None:
    esc = lambda s: html.escape(str(s))  # noqa: E731
    if direction == "日→英":
        if prompt_kind == "例文の訳" and e["例文訳"] and e["例文"]:
            question = f"<div class='rv-q'>{esc(e['例文訳'])}</div><div class='ex-sub'>使う表現：{esc(e['日本語訳'])}</div>"
        else:
            question = f"<div class='rv-q'>{esc(e['日本語訳'])}</div>"
        st.html(f"<div class='ex-card'><div class='ex-meta'>英語で言ってみよう</div>{question}</div>")
        if st.session_state["rv_revealed"]:
            expression.detail(e, show_schedule=False)
    else:
        sentence = f"<div class='ex-sentence'>{esc(e['例文'])}</div>" if e["例文"] else ""
        st.html(
            f"<div class='ex-card'><div class='ex-meta'>日本語の意味は？</div>"
            f"<div class='rv-q'>{esc(e['英語'])}</div>{sentence}</div>"
        )
        speech.buttons([("単語", e["英語"]), ("例文", e["例文"])])
        if st.session_state["rv_revealed"]:
            answer = f"<div class='ex-ja'>{esc(e['日本語訳'])}</div>"
            if e["例文訳"]:
                answer += f"<div class='ex-sub'>{esc(e['例文訳'])}</div>"
            if e["メモ"]:
                answer += f"<div class='ex-memo'>📝 {esc(e['メモ'])}</div>"
            st.html(f"<div class='ex-card'>{answer}</div>")


def render() -> None:
    expressions = storage.load_expressions()
    today = today_jst()

    if "rv_queue" not in st.session_state:
        _setup(expressions, today)
        return

    queue, pos = st.session_state["rv_queue"], st.session_state["rv_pos"]
    while pos < len(queue) and queue[pos] not in expressions.index:  # 復習中に削除された表現は飛ばす
        pos += 1
    st.session_state["rv_pos"] = pos
    if pos >= len(queue):
        _finished()
        return

    e = expressions.loc[queue[pos]]
    direction = st.session_state["rv_active_direction"]
    col1, col2 = st.container(key="rv_top").columns([3, 1], vertical_alignment="center")
    col1.progress(pos / len(queue), text=f"{pos + 1} / {len(queue)}")
    col2.button("やめる", width="stretch", on_click=_stop)
    _card(e, direction, st.session_state["rv_active_prompt"])

    if not st.session_state["rv_revealed"]:
        st.button("答えを見る", type="primary", width="stretch", on_click=_reveal)
    else:
        with st.container(key="grade_buttons"):  # スマホでも3つ横並びにする（app.py のCSS）
            cols = st.columns(3)
            for col, grade, kind in zip(cols, srs.GRADES, ["primary", "secondary", "secondary"]):
                col.button(grade, key=f"rv_{grade}", type=kind, width="stretch", on_click=_grade, args=(e, grade, direction))

    with st.expander("🔊 音声の速さ・アクセント"):
        speech.controls("rv")
