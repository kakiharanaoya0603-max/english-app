"""英語学習アプリ（入口）

起動方法: python -m streamlit run app.py
"""
import streamlit as st

import speech
import storage
from views import home, notebook, review, search, settings

st.set_page_config(page_title="英語表現帳", page_icon="🔤", layout="centered")

st.markdown(
    """
<style>
/* 上のツールバー（Share・︙などのボタン、高さ約60px）とタブが重ならないよう上の余白を確保 */
[data-testid="stMainBlockContainer"] { padding-top: 4.5rem; padding-bottom: 4rem; }

/* 音声用の JavaScript を入れた入れ物は見せない */
.st-key-speech_js { display: none; }

/* 検索結果や一覧のボタン（キーが results_ / list_ で始まる入れ物の中）は、読みやすいよう左寄せにする */
[class*="st-key-results_"] button, [class*="st-key-list_"] button { justify-content: flex-start; text-align: left; }
[class*="st-key-results_"] button > div, [class*="st-key-list_"] button > div { width: 100%; justify-content: flex-start; }
[class*="st-key-results_"] button p, [class*="st-key-list_"] button p { text-align: left; }

/* 復習の評価ボタン3つは、スマホでも横並びのままにする */
.st-key-grade_buttons [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: .4rem; }
.st-key-grade_buttons [data-testid="stColumn"] { min-width: 0; }
.st-key-grade_buttons button p { white-space: nowrap; font-size: .9rem; }

/* 表現のカード */
.ex-card { border: 1px solid rgba(128,128,128,.3); border-radius: 10px; padding: 12px 14px; margin-bottom: 4px; overflow-wrap: anywhere; }
.ex-en { font-size: 1.5rem; font-weight: 700; line-height: 1.3; }
.ex-ja { font-size: 1.05rem; margin-top: 2px; }
.ex-sentence { font-size: 1.1rem; margin-top: 10px; line-height: 1.45; }
.ex-sub { font-size: .92rem; opacity: .75; margin-top: 2px; }
.ex-memo { font-size: .9rem; margin-top: 8px; padding: 6px 8px; border-radius: 6px; background: rgba(128,128,128,.12); }
.ex-meta { font-size: .78rem; opacity: .65; margin-top: 8px; }
.rv-q { font-size: 1.25rem; font-weight: 600; line-height: 1.45; margin-top: 4px; }

/* 🔊 再生ボタン（speech.py が作るHTMLのボタン） */
.spk { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.spk-btn {
    min-height: 44px; padding: 0 18px; border-radius: 22px; font-size: 1rem; cursor: pointer;
    border: 1px solid rgba(128,128,128,.45); background: transparent; color: inherit;
    -webkit-tap-highlight-color: transparent; touch-action: manipulation;
}
.spk-btn:active { background: rgba(255,75,75,.18); }
.spk-msg { font-size: .8rem; color: #d33; flex-basis: 100%; }
.spk-msg:empty { display: none; }
.voice-box { font-size: .9rem; }
.voice-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.voice-row span { white-space: nowrap; }
.voice-row select { flex: 1; min-width: 0; min-height: 40px; font-size: 16px; color: inherit; background: transparent; border: 1px solid rgba(128,128,128,.45); border-radius: 6px; }
.voice-row select option { color: initial; }
.voice-info { font-size: .8rem; opacity: .75; }

/* スマホ（画面幅が狭いとき）だけの調整 */
@media (max-width: 640px) {
    /* 左右の余白を狭くして画面を広く使う */
    [data-testid="stMainBlockContainer"] { padding-left: .75rem; padding-right: .75rem; }
    /* ボタンを指で押しやすい高さにする（Appleの推奨は44px以上） */
    button[data-testid^="stBaseButton"] { min-height: 44px; }
    /* iPhoneは16px未満の入力欄をタップすると画面が勝手に拡大されるので16pxにする */
    input, textarea { font-size: 16px !important; }
    /* 上の画面切り替えボタンは5つあるので、文字を少し小さくして1行に収める */
    .st-key-page button p { font-size: .8rem; white-space: nowrap; }
    .st-key-page button { padding-left: 2px; padding-right: 2px; }
    /* 復習の進み具合と「やめる」は横並びのまま */
    .st-key-rv_top [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
    .st-key-rv_top [data-testid="stColumn"]:first-child { min-width: 0; flex: 1 1 auto; }
    .st-key-rv_top [data-testid="stColumn"]:last-child { min-width: 88px; flex: 0 0 88px; }
    /* 検索欄と「×」は横並びのまま */
    .st-key-search_row [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
    .st-key-search_row [data-testid="stColumn"]:first-child { min-width: 0; flex: 1 1 auto; }
    .st-key-search_row [data-testid="stColumn"]:last-child { min-width: 48px; flex: 0 0 48px; }
}
</style>
""",
    unsafe_allow_html=True,
)

speech.install()
speech.load_settings()

if not storage.use_gsheets():
    st.info("いまはパソコン内のファイル（data フォルダ）に保存しています。")

# 保存・削除したあとのメッセージ（画面を再読み込みしても残るように session_state に入れる）
if "message" in st.session_state:
    st.success(st.session_state.pop("message"))

PAGES = {m.PAGE_LABEL: m for m in [home, search, review, notebook, settings]}
# 初期値は session_state で与える（ほかの画面から「表現帳へ移動」のように切り替えることがあるため）
st.session_state.setdefault("page", home.PAGE_LABEL)
page = st.segmented_control(
    "画面", list(PAGES), key="page", label_visibility="collapsed",
    required=True,  # 選択中のボタンを押しても選択が外れないようにする
    width="stretch",
)
PAGES[page].render()
