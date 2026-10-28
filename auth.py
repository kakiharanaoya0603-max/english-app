"""パスワード画面。パスワードは secrets.toml（Streamlit Cloud では Secrets）の app_password に書く。

ログインすると、この端末のブラウザに「合言葉（パスワードから作った値）」をクッキーとして1年間覚えさせ、
次からはパスワードを聞かない。パスワードそのものはクッキーに入れない。パスワードを変えると全端末でログアウトになる。
"""
import hashlib
import hmac

import streamlit as st

COOKIE = "english_app_auth"
MAX_AGE = 60 * 60 * 24 * 365  # 1年


def _password() -> str | None:
    try:
        return st.secrets.get("app_password") or None
    except Exception:  # secrets.toml が無いとき
        return None


def _token(password: str) -> str:
    return hmac.new(password.encode(), b"english-app-login", hashlib.sha256).hexdigest()


def _set_cookie(value: str, max_age: int) -> None:
    # Streamlit Cloud ではアプリが iframe の中で動くので、SameSite=None; Secure にしないと覚えてもらえない
    secure = "; SameSite=None; Secure" if (st.context.url or "").startswith("https") else "; SameSite=Lax"
    with st.container(key="auth_js"):  # 見た目には何も出さない（app.py のCSSで隠す）
        st.html(
            f"<script>document.cookie = '{COOKIE}={value}; max-age={max_age}; path=/{secure}';</script>",
            unsafe_allow_javascript=True,
        )


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
    if st.session_state.pop("logout", False):
        _set_cookie("", 0)
        st.session_state["authed"] = False
        # この画面を開いたときに届いたクッキーは消したあとも残って見えるので、以後は使わない
        st.session_state["ignore_cookie"] = True
    elif st.session_state.get("authed") or (
        not st.session_state.get("ignore_cookie")
        and hmac.compare_digest(st.context.cookies.get(COOKIE, ""), _token(password))
    ):
        st.session_state["authed"] = True
        if st.session_state.pop("remember", False):  # ログインした直後の1回だけクッキーを書く
            _set_cookie(_token(password), MAX_AGE)
        return

    st.markdown("### 🔤 英語表現帳")
    with st.form("login"):
        entered = st.text_input("パスワード", type="password")
        remember = st.checkbox("この端末ではパスワードを覚える", value=True)
        submitted = st.form_submit_button("ひらく", type="primary", width="stretch")
    if submitted:
        if hmac.compare_digest(entered.encode(), password.encode()):
            st.session_state.update(authed=True, remember=remember, ignore_cookie=False)
            st.rerun()
        st.error("パスワードが違います")
    st.stop()
