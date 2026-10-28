"""⚙️ 設定画面：音声の方式・速度・アクセントと、データ・辞書の情報"""
import streamlit as st

import auth
import dictionary
import speech
import storage
from common import APP_VERSION

PAGE_LABEL = "⚙️ 設定"
TEST_WORD = "procurement"
TEST_SENTENCE = "We need to look into the procurement schedule by Friday."


def render() -> None:
    st.subheader("🔊 音声")
    speech.controls("settings", engine=True)
    st.caption("声の選択（ブラウザの読み上げのとき。選んだ声はこの端末に覚えます）")
    speech.voice_picker()
    st.caption("テスト再生")
    speech.buttons([("単語", TEST_WORD), ("例文", TEST_SENTENCE)])
    with st.expander("iPhoneで音が出ないとき"):
        st.markdown(
            """
- **消音モード（本体横のスイッチ／アクションボタン）をオフ**にしてください。
  ブラウザの読み上げは消音モードだと鳴らないことがあります。
- 音量ボタンで音量を上げてください（着信音量ではなく、再生中の音量）。
- それでも鳴らない・声がおかしいときは、上の「音声の方式」を **gTTS** にしてください。
  gTTSは音声ファイルとして再生するので、消音モードでも鳴ることが多いです（少し待ち時間があります）。
- 声の一覧に名前が出ないときは、iPhoneの「設定 → アクセシビリティ → 読み上げコンテンツ → 声 → 英語」で声を追加できます。
"""
        )

    st.subheader("💾 データ")
    if storage.use_gsheets():
        st.caption("表現・復習の記録は Googleスプレッドシートに保存しています。")
    else:
        st.caption("いまはパソコン内のファイル（data フォルダ）に保存しています。")
    if st.button("スプレッドシートから読み直す", help="ほかの端末で登録した内容をすぐ反映したいときに"):
        st.cache_data.clear()
        st.rerun()

    st.subheader("🔒 ログイン")
    st.button("ログアウト", on_click=auth.logout, help="この端末で覚えたパスワードも消します")

    st.caption(f"バージョン {APP_VERSION}")

    st.subheader("📖 辞書")
    st.caption(dictionary.CREDIT)
    st.caption(f"収録語数：{len(dictionary.load()):,}語。辞書データは改変せずに検索用の読みを付けて使っています。")
