"""📷 写真から英文を読み取る（表現帳画面の中の1つのモード）

  st.session_state["photo_text"]     … 読み取った英文（手で直したあとのもの。写真そのものは持たない）
  st.session_state["photo_selected"] … 一覧で選んだ文
  st.session_state["ocr_engine"]     … 読み取りの方式（ocr.ENGINES のキー）
"""
import html

import streamlit as st

import ocr
import speech
import storage
from views import expression

TEXT_KEY = "photo_text_box"


def _engine() -> str:
    if "ocr_engine" not in st.session_state:
        saved = storage.load_settings().get("読み取り方式")
        st.session_state["ocr_engine"] = saved if saved in ocr.ENGINES else "browser"
    return st.session_state["ocr_engine"]


def _save_engine() -> None:
    st.session_state["ocr_engine"] = st.session_state["photo_engine"]
    storage.save_settings({**storage.load_settings(), "読み取り方式": st.session_state["ocr_engine"]})


def _set_text(text: str) -> None:
    st.session_state["photo_text"] = text
    st.session_state[TEXT_KEY] = text
    st.session_state["photo_selected"] = None


def _keep_text() -> None:
    st.session_state["photo_text"] = st.session_state[TEXT_KEY]


def _select(sentence: str | None) -> None:
    st.session_state["photo_selected"] = sentence


def _register(sentence: str) -> None:
    st.session_state["prefill"] = {"例文": sentence}
    st.session_state["notebook_mode"] = "＋ 登録"
    expression.reset_form("nb_add")


def _settings() -> None:
    with st.expander("読み取りの設定・うまく読めないとき"):
        st.session_state["photo_engine"] = _engine()
        st.radio("読み取る場所", list(ocr.ENGINES), format_func=ocr.ENGINES.get, key="photo_engine", on_change=_save_engine)
        st.toggle("白黒にしてから読む", value=True, key="photo_binarize", help="薄い文字・影のある写真に効きます。かえって読めなくなるときはオフに")
        st.markdown(
            """
- 英文の部分だけが大きく写るように撮ると、よく読めます（写真アプリの「編集 → 切り取り」で切り取ってから選ぶのもおすすめ）。
- 少しの傾きは自動で直します。横向き・逆さまのときは「↺ ↻」で回してください。
- 写真はこの端末の画面の中だけで使い、どこにも保存しません（サーバーで読む方式でも、白黒にした小さな画像を読み取りに使うだけで保存しません）。
"""
        )


def render() -> None:
    _settings()
    engine = _engine()
    result = ocr.picker(engine, st.session_state.get("photo_binarize", True), key="photo_ocr")

    if result.result:  # 読み取りが終わったとき（この1回だけ値が入る）
        if "paragraphs" in result.result:
            _set_text(ocr.clean_text(ocr.assemble(result.result["paragraphs"])))
        elif "image" in result.result:
            if not ocr.server_available():
                st.error("サーバーに Tesseract が入っていません。「この端末で読む」に切り替えてください。")
            else:
                with st.spinner("サーバーで読み取っています…"):
                    _set_text(ocr.clean_text(ocr.assemble(ocr.read_on_server(result.result["image"]))))

    text = st.session_state.get("photo_text", "")
    if not text:
        st.caption("英文が写った写真を撮るか、写真ライブラリから選んでください。読み取った文を例文として登録できます。")
        return

    # 画面を切り替えると入力欄の中身は消えるので、覚えておいた文字から作り直す
    st.session_state.setdefault(TEXT_KEY, text)
    st.text_area("読み取った英文（読み間違いはここで直せます）", key=TEXT_KEY, height=200, on_change=_keep_text)
    sentences = ocr.split_sentences(st.session_state[TEXT_KEY])
    if not sentences:
        st.info("英文が見つかりませんでした。写真を撮り直すか、上の欄に入力してください。")
        return

    selected = st.session_state.get("photo_selected")
    if selected:
        st.button("↩ 文の一覧に戻る", key="photo_back", on_click=_select, args=(None,))
        st.html(f"<div class='ex-card'><div class='ex-sentence' style='margin-top:0'>{html.escape(selected)}</div></div>")
        speech.buttons([("この文", selected)])
        st.button("＋ 例文として登録", type="primary", width="stretch", key="photo_register", on_click=_register, args=(selected,))
        return

    st.caption(f"{len(sentences)}個の文に分けました。登録・再生したい文を選んでください。")
    with st.container(key="list_photo"):  # この中のボタンは左寄せ（app.py のCSS）
        for i, sentence in enumerate(sentences):
            st.button(
                expression.md_escape(sentence), key=f"photo_sentence_{i}", width="stretch",
                on_click=_select, args=(sentence,),
            )
