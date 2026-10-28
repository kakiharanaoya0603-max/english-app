"""英語の音声（🔊 再生ボタン）。

2つの方式を設定で切り替えられる。
  ブラウザ … ブラウザの読み上げ機能（Web Speech API / speechSynthesis）。無料・キー不要・通信なしで速い
  gTTS     … サーバーで Google翻訳の音声（mp3）を作って <audio> で鳴らす。無料・キー不要

iPhoneのSafariは「指でタップした処理の中」でしか音を出させないため、再生ボタンは Streamlit のボタンではなく
HTMLのボタンにして、ページに1つだけ入れた JavaScript（install()）がタップを受けて直接鳴らす。
ボタンには、読む英文・速度・アクセント（gTTSなら音声データ）を data- 属性で持たせる。
"""
import base64
import html
import io
import json

import streamlit as st

import storage

ENGINES = {"browser": "ブラウザの読み上げ（おすすめ・速い）", "gtts": "gTTS（Google翻訳の音声）"}
SPEEDS = {0.7: "ゆっくり", 1.0: "普通", 1.2: "速め"}
ACCENTS = {"en-US": "🇺🇸 アメリカ", "en-GB": "🇬🇧 イギリス"}
GTTS_TLD = {"en-US": "com", "en-GB": "co.uk"}  # gTTS はドメインでアクセントが変わる
DEFAULTS = {"音声方式": "browser", "音声速度": "1.0", "アクセント": "en-US"}


# ---------- 設定 ----------

def load_settings() -> None:
    """保存してある音声の設定を session_state["voice"] に読み込む（起動時に1回）"""
    if "voice" not in st.session_state:
        saved = storage.load_settings()
        st.session_state["voice"] = {k: saved.get(k) or v for k, v in DEFAULTS.items()}


def setting(name: str) -> str:
    return st.session_state["voice"][name]


def _save(name: str, widget_key: str) -> None:
    value = st.session_state[widget_key]
    st.session_state["voice"][name] = str(value)
    storage.save_settings({**storage.load_settings(), **st.session_state["voice"]})


def controls(key: str, engine: bool = False) -> None:
    """速度・アクセント（engine=True なら方式も）の切り替えボタン。変えるとスプレッドシートに保存する"""
    col1, col2 = st.columns(2)
    speed_key, accent_key = f"{key}_speed", f"{key}_accent"
    # 画面を切り替えるとボタンの状態は消えるので、毎回保存してある設定から作り直す
    st.session_state[speed_key] = float(setting("音声速度"))
    st.session_state[accent_key] = setting("アクセント")
    col1.segmented_control(
        "速度", list(SPEEDS), format_func=SPEEDS.get, key=speed_key, required=True,
        on_change=_save, args=("音声速度", speed_key), width="stretch",
    )
    col2.segmented_control(
        "アクセント", list(ACCENTS), format_func=ACCENTS.get, key=accent_key, required=True,
        on_change=_save, args=("アクセント", accent_key), width="stretch",
    )
    if engine:
        engine_key = f"{key}_engine"
        st.session_state[engine_key] = setting("音声方式")
        st.radio(
            "音声の方式", list(ENGINES), format_func=ENGINES.get, key=engine_key,
            on_change=_save, args=("音声方式", engine_key),
        )


# ---------- gTTS ----------

@st.cache_data(max_entries=1000, show_spinner=False)
def _gtts_data_url(text: str, lang: str) -> str | None:
    """gTTS で mp3 を作り、<audio> でそのまま鳴らせる data URL にする。失敗したら None"""
    try:
        from gtts import gTTS

        buf = io.BytesIO()
        gTTS(text, lang="en", tld=GTTS_TLD[lang]).write_to_fp(buf)
        return "data:audio/mpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # 通信エラーや回数制限のとき（このときはブラウザの読み上げで鳴らす）
        return None


# ---------- 再生ボタン ----------

def buttons(items: list[tuple[str, str]]) -> None:
    """🔊 再生ボタンを横に並べる。items は (ボタンの文字, 読む英文)。英文が空のものは出さない"""
    items = [(label, text.strip()) for label, text in items if text and text.strip()]
    if not items:
        return
    lang, rate = setting("アクセント"), setting("音声速度")
    use_gtts = setting("音声方式") == "gtts"
    parts, failed = [], False
    for label, text in items:
        attrs = {"data-text": text, "data-lang": lang, "data-rate": rate}
        if use_gtts:
            with st.spinner("音声を準備しています…"):
                src = _gtts_data_url(text, lang)
            if src:
                attrs["data-src"] = src
            else:
                failed = True
        attr_text = " ".join(f'{k}="{html.escape(v, quote=True)}"' for k, v in attrs.items())
        parts.append(f'<button type="button" class="spk-btn" {attr_text}>🔊 {html.escape(label)}</button>')
    message = "gTTSの音声を作れなかったので、ブラウザの読み上げで鳴らします" if failed else ""
    st.html(f'<div class="spk">{"".join(parts)}<div class="spk-msg">{message}</div></div>')


def voice_picker() -> None:
    """この端末で使える英語の声の一覧と、声の選択欄（設定画面用。選んだ声はこの端末のブラウザに覚える）"""
    rows = "".join(
        f'<div class="voice-row"><span>{label}</span>'
        f'<select class="voice-select" data-lang="{lang}"><option value="">自動で選ぶ</option></select></div>'
        for lang, label in ACCENTS.items()
    )
    st.html(f'<div class="voice-box">{rows}<div class="voice-info"></div></div>')


# ---------- ページに1つだけ入れる JavaScript ----------

# iPhone（Safari）には、普通の声のほかに「Bells」「Zarvox」のような効果音っぽい声が英語として入っているので除く
_NOVELTY = [
    "Albert", "Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos", "Good News", "Jester", "Organ",
    "Superstar", "Trinoids", "Whisper", "Wobble", "Zarvox", "Fred", "Junior", "Ralph", "Kathy", "Grandma",
    "Grandpa", "Eddy", "Flo", "Reed", "Rocko", "Sandy", "Shelley",
]
# 自動で選ぶときに優先する声（先頭ほど優先。iPhone・Mac・Windows・Androidでよくある名前）
_PREFERRED = {
    "en-US": ["Samantha", "Ava", "Allison", "Susan", "Nicky", "Alex", "Google US English",
              "Microsoft Aria", "Microsoft Jenny", "Microsoft Guy", "Microsoft Zira", "Microsoft David"],
    "en-GB": ["Daniel", "Serena", "Kate", "Arthur", "Martha", "Oliver", "Google UK English Female",
              "Google UK English Male", "Microsoft Sonia", "Microsoft Libby", "Microsoft Ryan",
              "Microsoft Hazel", "Microsoft George"],
}

_SCRIPT = """
<script>
(function () {
  if (window.__englishAppSpeech) return;
  window.__englishAppSpeech = true;
  const NOVELTY = new RegExp("^(" + %(novelty)s.join("|") + ")\\\\b");
  const PREFERRED = %(preferred)s;
  const hasTTS = "speechSynthesis" in window;
  let voices = [];

  function store(key, value) {
    try { if (value === undefined) return localStorage.getItem(key) || ""; localStorage.setItem(key, value); }
    catch (e) { return ""; }
  }
  function englishVoices(lang) {
    return voices.filter(v => (v.lang || "").replace("_", "-").startsWith(lang) && !NOVELTY.test(v.name));
  }
  function pickVoice(lang) {
    const list = englishVoices(lang);
    const saved = store("englishAppVoice:" + lang);
    if (saved) { const v = list.find(v => v.name === saved); if (v) return v; }
    for (const name of PREFERRED[lang] || []) { const v = list.find(v => v.name.startsWith(name)); if (v) return v; }
    return list.find(v => v.localService) || list[0] || null;
  }
  function message(btn, text) {
    const box = btn.closest(".spk");
    const msg = box && box.querySelector(".spk-msg");
    if (msg) msg.textContent = text;
  }

  function speakBrowser(btn, text, lang, rate) {
    if (!hasTTS) { message(btn, "このブラウザは読み上げに対応していません。設定で gTTS に切り替えてください"); return; }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = rate;
    const v = pickVoice(lang);
    if (v) u.voice = v;
    u.onerror = e => {
      if (e.error !== "interrupted" && e.error !== "canceled")
        message(btn, "再生できませんでした（" + e.error + "）。設定で gTTS に切り替えてください");
    };
    speechSynthesis.speak(u);
    if (speechSynthesis.paused) speechSynthesis.resume();  // iPhoneで一時停止のまま止まることがあるため
  }

  let audio = null;
  function playAudio(btn, src, rate) {
    if (hasTTS) speechSynthesis.cancel();
    if (audio) audio.pause();
    audio = new Audio(src);
    audio.defaultPlaybackRate = rate;
    audio.playbackRate = rate;
    audio.play().catch(e => message(btn, "再生できませんでした（" + e.name + "）"));
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest && e.target.closest(".spk-btn");
    if (!btn) return;
    e.preventDefault();
    message(btn, "");
    const rate = parseFloat(btn.dataset.rate || "1");
    if (btn.dataset.src) playAudio(btn, btn.dataset.src, rate);
    else speakBrowser(btn, btn.dataset.text, btn.dataset.lang || "en-US", rate);
  });

  // 設定画面の「声の選択」欄に、この端末の英語の声を入れる
  function fillVoicePickers() {
    document.querySelectorAll("select.voice-select").forEach(sel => {
      const lang = sel.dataset.lang;
      const names = englishVoices(lang).map(v => v.name);
      if (sel.dataset.filled === names.join("|")) return;
      sel.dataset.filled = names.join("|");
      sel.length = 1;
      names.forEach(n => sel.add(new Option(n, n)));
      sel.value = store("englishAppVoice:" + lang);
    });
    document.querySelectorAll(".voice-info").forEach(info => {
      let text = "このブラウザは読み上げ（speechSynthesis）に対応していません。gTTSを使ってください。";
      if (hasTTS) {
        const us = pickVoice("en-US"), gb = pickVoice("en-GB");
        text = "この端末の英語の声：" + voices.filter(v => (v.lang || "").startsWith("en")).length + "個"
          + "　／　いま使う声：🇺🇸 " + (us ? us.name : "見つかりません")
          + "　🇬🇧 " + (gb ? gb.name : "見つかりません");
      }
      // 同じ内容なら書き換えない（書き換えると下の MutationObserver がまた反応して止まらなくなる）
      if (info.textContent !== text) info.textContent = text;
    });
  }
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("select.voice-select")) {
      store("englishAppVoice:" + e.target.dataset.lang, e.target.value);
      fillVoicePickers();
    }
  });
  function loadVoices() { voices = hasTTS ? speechSynthesis.getVoices() : []; fillVoicePickers(); }
  if (hasTTS) {
    loadVoices();
    speechSynthesis.addEventListener("voiceschanged", loadVoices);  // 声の一覧はあとから届くことがある
  }
  new MutationObserver(() => {
    if (document.querySelector("select.voice-select, .voice-info")) fillVoicePickers();
  }).observe(document.body, { childList: true, subtree: true });

  // 検索の候補一覧（キーが results_ で始まる入れ物）は、一覧と検索欄の外をタップしたら閉じる。
  // 検索欄（キーが「同じ名前_query」）をタップすると、また開く
  function resultKey(el) {
    const c = [...el.classList].find(c => c.startsWith("st-key-results_"));
    return c ? c.slice("st-key-results_".length) : null;
  }
  document.addEventListener("pointerdown", function (e) {
    document.querySelectorAll('[class*="st-key-results_"]').forEach(box => {
      const key = resultKey(box);
      const input = key && document.querySelector(".st-key-" + key + "_query");
      if (!key || box.contains(e.target)) return;
      box.style.display = input && input.contains(e.target) ? "" : "none";
    });
  }, true);
  document.addEventListener("focusin", function (e) {
    const wrap = e.target.closest && e.target.closest('[class*="_query"]');
    if (!wrap) return;
    const c = [...wrap.classList].find(c => c.startsWith("st-key-") && c.endsWith("_query"));
    if (!c) return;
    const box = document.querySelector(".st-key-results_" + c.slice("st-key-".length, -"_query".length));
    if (box) box.style.display = "";
  });
})();
</script>
""" % {"novelty": json.dumps(_NOVELTY), "preferred": json.dumps(_PREFERRED)}


def install() -> None:
    """再生ボタン・声の選択・候補一覧を閉じる処理の JavaScript をページに入れる（app.py で毎回呼ぶ）"""
    with st.container(key="speech_js"):  # 見た目には何も出さない（app.py のCSSで隠す）
        st.html(_SCRIPT, unsafe_allow_javascript=True)
