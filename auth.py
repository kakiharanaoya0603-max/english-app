"""パスワード画面。パスワードは secrets.toml（Streamlit Cloud では Secrets）の app_password に書く。

ログインすると、この端末のブラウザに「合言葉（パスワードから作った値）」を覚えさせ、次からはパスワードを聞かない。
覚え方は2つ（どちらかが残っていればよい）。
  localStorage … ブラウザの保存場所。部品（st.components.v2）でアプリに送る。iPhone＋Streamlit Cloud でも確実に届く
  クッキー     … 1年間。Streamlit Cloud の iPhone では、アプリまで届かないことがある
パスワードそのものは覚えさせない。パスワードを変えると全端末でログアウトになる。
※ iPhoneのSafariは、7日以上開かなかったサイトの保存内容を消すことがある（そのときはもう一度パスワードを入れる）
"""
import hashlib
import hmac

import streamlit as st

from common import APP_VERSION

COOKIE = "english_app_auth"
MAX_AGE = 60 * 60 * 24 * 365  # 1年

# ブラウザの localStorage に合言葉を書く・消す・読んでアプリに送る部品
_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  if (parentElement.__done) return;  // 画面が描き直されても1回だけ動かす
  parentElement.__done = true;
  const KEY = "englishAppLogin";
  try {
    if (data.save) localStorage.setItem(KEY, data.save);
    else if (data.clear) localStorage.removeItem(KEY);
    else setTriggerValue("token", localStorage.getItem(KEY) || "");
  } catch (e) {
    if (!data.save && !data.clear) setTriggerValue("token", "");  // 保存場所が使えない（プライベートブラウズなど）
  }
}
"""
_storage = st.components.v2.component("remember_login", js=_JS)


def _password() -> str | None:
    try:
        return st.secrets.get("app_password") or None
    except Exception:  # secrets.toml が無いとき
        return None


def _token(password: str) -> str:
    return hmac.new(password.encode(), b"english-app-login", hashlib.sha256).hexdigest()


def _remember(value: str) -> None:
    """この端末に合言葉を覚えさせる（value が空なら消す）"""
    max_age = MAX_AGE if value else 0
    # Streamlit Cloud ではアプリが iframe の中で動くので、SameSite=None; Secure にしないと覚えてもらえない
    secure = "; SameSite=None; Secure" if (st.context.url or "").startswith("https") else "; SameSite=Lax"
    with st.container(key="auth_js"):  # 見た目には何も出さない（app.py のCSSで隠す）
        st.html(
            f"<script>document.cookie = '{COOKIE}={value}; max-age={max_age}; path=/{secure}';</script>",
            unsafe_allow_javascript=True,
        )
        _storage(data={"save": value} if value else {"clear": True}, key="auth_store")


def logout() -> None:
    """ログアウト（ボタンの on_click の中で呼ぶ）"""
    st.session_state["authed"] = False
    st.session_state["logout"] = True


def require_login() -> None:
    """パスワードが合うまで、ここから先（アプリ本体）を表示しない"""
    password = _password()
    if password is None:
        st.error("パスワードが設定されていません。Secrets に app_password を追加してください。")
        st.stop()
    token = _token(password)
    if st.session_state.pop("logout", False):
        _remember("")
        st.session_state["authed"] = False
        # この画面を開いたときに届いた合言葉は消したあとも残って見えるので、以後は使わない
        st.session_state["ignore_saved"] = True
    elif st.session_state.get("authed") or (
        not st.session_state.get("ignore_saved")
        and hmac.compare_digest(st.context.cookies.get(COOKIE, ""), token)
    ):
        st.session_state["authed"] = True
        if st.session_state.pop("remember", False):  # ログインした直後の1回だけ覚えさせる
            _remember(token)
        return
    elif not st.session_state.get("ignore_saved"):
        # localStorage に覚えてある合言葉を読む（届くまでの一瞬はパスワード欄が見える）
        with st.container(key="auth_js"):
            saved = _storage(data={}, key="auth_read", on_token_change=lambda: None).token
        if saved and hmac.compare_digest(saved, token):
            st.session_state["authed"] = True
            st.rerun()

    st.markdown("### 🔤 英語表現帳")
    with st.form("login"):
        entered = st.text_input("パスワード", type="password")
        remember = st.checkbox("この端末ではパスワードを覚える", value=True)
        submitted = st.form_submit_button("ひらく", type="primary", width="stretch")
    if submitted:
        if hmac.compare_digest(entered.encode(), password.encode()):
            st.session_state.update(authed=True, remember=remember, ignore_saved=False)
            st.rerun()
        st.error("パスワードが違います")
    st.caption(f"バージョン {APP_VERSION}")
    st.stop()
