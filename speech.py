"""英語の音声（🔊 再生ボタンと、一時停止・停止・くり返し・速度の操作）。

2つの方式を設定で切り替えられる。
  ブラウザ … ブラウザの読み上げ機能（Web Speech API / speechSynthesis）。無料・キー不要・通信なしで速い
  gTTS     … サーバーで Google翻訳の音声（mp3）を作って <audio> で鳴らす。無料・キー不要

iPhoneのSafariは「指でタップした処理の中」でしか音を出させないため、再生ボタンは Streamlit のボタンではなく
HTMLのボタンにして、ページに1つだけ入れた JavaScript（install()）がタップを受けて直接鳴らす。
再生ボタンの入れ物には、読む英文（gTTSなら音声データも）を data- 属性で持たせる。
速度・くり返し回数・くり返しの間は、install() がページに1つだけ入れる設定の入れ物から JavaScript が読む
（再生中に速度を変えても、すぐに反映する）。

一時停止について：iPhoneの読み上げ（speechSynthesis）は pause()/resume() がうまく動かないことがあるので、
ブラウザ方式では一時停止で読み上げを止め、再開で「止めた文の頭から」読み直す。
gTTS方式は音声ファイルなので、止めたところからそのまま再開でき、速度も再生中にすぐ変わる。
"""
import base64
import hashlib
import html
import io
import json

import streamlit as st

import storage
from textutil import split_sentences

ENGINES = {"browser": "ブラウザの読み上げ（おすすめ・速い）", "gtts": "gTTS（Google翻訳の音声・一時停止が確実）"}
SPEED_MIN, SPEED_MAX = 0.5, 1.5
QUICK_SPEEDS = [0.7, 1.0, 1.2]  # ワンタップで切り替える、よく使う速さ
REPEATS = {1: "1回", 3: "3回", 5: "5回", 0: "∞ 止めるまで"}  # 0 は止めるまでくり返す
ACCENTS = {"en-US": "🇺🇸 アメリカ", "en-GB": "🇬🇧 イギリス"}
GTTS_TLD = {"en-US": "com", "en-GB": "co.uk"}  # gTTS はドメインでアクセントが変わる
DEFAULTS = {"音声方式": "browser", "音声速度": "1.0", "アクセント": "en-US", "くり返し": "1", "くり返しの間": "1.0"}


# ---------- 設定 ----------

def load_settings() -> None:
    """保存してある音声の設定を session_state["voice"] に読み込む（起動時に1回）"""
    if "voice" not in st.session_state:
        saved = storage.load_settings()
        st.session_state["voice"] = {k: saved.get(k) or v for k, v in DEFAULTS.items()}


def setting(name: str) -> str:
    return st.session_state["voice"][name]


def _number(name: str, low: float, high: float) -> float:
    try:
        value = float(setting(name))
    except ValueError:
        value = float(DEFAULTS[name])
    return round(min(high, max(low, value)), 1)


def speed() -> float:
    return _number("音声速度", SPEED_MIN, SPEED_MAX)


def repeat() -> int:
    value = setting("くり返し")
    return int(value) if value.isdigit() and int(value) in REPEATS else 1


def gap() -> float:
    return _number("くり返しの間", 0.0, 3.0)


def _store(name: str, value) -> None:
    if isinstance(value, float):
        value = round(value, 1)  # スライダーの値は 0.7000000000000001 のようになることがある
    st.session_state["voice"][name] = str(value)
    storage.save_settings({**storage.load_settings(), **st.session_state["voice"]})


def _save(name: str, widget_key: str) -> None:
    _store(name, st.session_state[widget_key])


def _save_quick(widget_key: str) -> None:
    if st.session_state[widget_key] is not None:  # 選んである速さをもう一度押したとき（選択が外れる）は何もしない
        _store("音声速度", st.session_state[widget_key])


def controls(key: str, engine: bool = False, playback: bool = True) -> None:
    """速度・アクセント（playback=True ならくり返し、engine=True なら方式も）の操作。変えるとスプレッドシートに保存する"""
    speed_key, quick_key, accent_key = f"{key}_speed", f"{key}_quick", f"{key}_accent"
    # 画面を切り替えるとボタンの状態は消えるので、毎回保存してある設定から作り直す
    st.session_state[speed_key] = speed()
    st.session_state[quick_key] = speed() if speed() in QUICK_SPEEDS else None
    st.session_state[accent_key] = setting("アクセント")
    st.slider(
        "速度", SPEED_MIN, SPEED_MAX, step=0.1, format="%.1f倍", key=speed_key,
        on_change=_save, args=("音声速度", speed_key),
    )
    st.segmented_control(
        "よく使う速さ", QUICK_SPEEDS, format_func=lambda v: f"{v}倍", key=quick_key, label_visibility="collapsed",
        on_change=_save_quick, args=(quick_key,), width="stretch",
    )
    st.segmented_control(
        "アクセント", list(ACCENTS), format_func=ACCENTS.get, key=accent_key, required=True,
        on_change=_save, args=("アクセント", accent_key), width="stretch",
    )
    if playback:
        repeat_key, gap_key = f"{key}_repeat", f"{key}_gap"
        st.session_state[repeat_key] = repeat()
        st.session_state[gap_key] = gap()
        st.segmented_control(
            "くり返し", list(REPEATS), format_func=REPEATS.get, key=repeat_key, required=True,
            on_change=_save, args=("くり返し", repeat_key), width="stretch",
        )
        st.slider(
            "くり返しの間（シャドーイング用）", 0.0, 3.0, step=0.5, format="%.1f秒", key=gap_key,
            on_change=_save, args=("くり返しの間", gap_key),
            help="1回読むごとに、この秒数だけ間をあけます。単語→例文のときは単語と例文の間にもあきます",
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

def buttons(items: list[tuple[str, str]], chain: bool = True) -> None:
    """🔊 再生ボタンを横に並べる。items は (ボタンの文字, 読む英文)。英文が空のものは出さない。
    chain=True で2つ以上あるときは「単語→例文」のように続けて読むボタンも付ける。
    再生を始めると、その下に一時停止・停止のボタンと、いま読んでいるところが出る"""
    items = [(label, text.strip()) for label, text in items if text and text.strip()]
    if not items:
        return
    lang = setting("アクセント")
    use_gtts = setting("音声方式") == "gtts"
    data, failed = [], False
    for label, text in items:
        # ブラウザ方式は、一時停止のあと文の頭から読み直せるように文ごとに分けて読む
        item = {"label": label, "parts": split_sentences(text) or [text]}
        if use_gtts:
            with st.spinner("音声を準備しています…"):
                src = _gtts_data_url(text, lang)
            if src:
                item["src"] = src
            else:
                failed = True
        data.append(item)

    plays = [([i], label) for i, (label, _) in enumerate(items)]
    if chain and len(items) >= 2:
        plays.append((list(range(len(items))), "→".join(label for label, _ in items)))
    parts = [
        f'<button type="button" class="spk-btn" data-play="{json.dumps(idx)}" data-label="{html.escape(label, quote=True)}">'
        f"🔊 {html.escape(label)}</button>"
        for idx, label in plays
    ]
    # 画面が描き直されても同じ再生ボタンの入れ物だと分かるように、内容から名前（id）を作る
    box_id = hashlib.md5(json.dumps([items, lang, use_gtts], ensure_ascii=False).encode()).hexdigest()[:12]
    message = "gTTSの音声を作れなかったので、ブラウザの読み上げで鳴らします" if failed else ""
    st.html(
        f'<div class="spk" data-id="{box_id}" data-lang="{lang}" data-items="{html.escape(json.dumps(data), quote=True)}">'
        f'<div class="spk-row">{"".join(parts)}</div>'
        '<div class="spk-ctl" hidden><button type="button" class="spk-pause">⏸ 一時停止</button>'
        '<button type="button" class="spk-stop">⏹ 停止</button></div>'
        f'<div class="spk-status"></div><div class="spk-msg">{message}</div></div>'
    )


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

  // ---------- 再生（くり返し・一時停止・停止） ----------

  // 速度・くり返し回数・間（install() が入れる設定の入れ物から読む。変えるとすぐ反映される）
  function settings() {
    const el = document.querySelector(".spk-settings");
    const d = el ? el.dataset : {};
    return { rate: parseFloat(d.rate || "1"), repeat: parseInt(d.repeat || "1", 10), gap: parseFloat(d.gap || "0") };
  }

  // いまの再生。state は idle（止まっている）／playing（読んでいる）／gap（くり返しの間）／paused（一時停止中）
  // token は、止めたり読み直したりした「前の読み上げ」の終わりの知らせを無視するための番号
  const P = { state: "idle", box: "", play: "", lang: "en-US", items: [], idx: 0, part: 0, rep: 0, timer: null, token: 0, fromGap: false, rate: null };
  const audio = new Audio();  // iPhoneは、タップで一度鳴らした audio 要素なら、そのあとも続けて鳴らせるので1つを使い回す
  audio.preservesPitch = true;

  function message(el, text) {
    const box = el && el.closest(".spk");
    const msg = box && box.querySelector(".spk-msg");
    if (msg) msg.textContent = text;
  }
  function activeBox() { return document.querySelector('.spk[data-id="' + P.box + '"]'); }

  function statusText() {
    const s = settings(), it = P.items[P.idx];
    const head = P.state === "paused" ? "⏸ 一時停止中" : P.state === "gap" ? "… 間をあけています" : "▶ 再生中";
    let where = P.items.length > 1 ? P.items.map((x, i) => i === P.idx ? "【" + x.label + "】" : x.label).join(" → ") : it.label;
    if (!it.src && it.parts.length > 1) where += "（" + (P.part + 1) + "/" + it.parts.length + "文目）";
    const times = s.repeat === 0 ? "　" + (P.rep + 1) + "回目（止めるまでくり返し）" : s.repeat > 1 ? "　" + (P.rep + 1) + "/" + s.repeat + "回目" : "";
    return head + "：" + where + times;
  }

  // ボタンの文字（再生中／一時停止中）と、いま読んでいるところの表示を、いまの再生に合わせる
  function syncUI() {
    document.querySelectorAll(".spk").forEach(box => {
      const active = P.state !== "idle" && box.dataset.id === P.box;
      box.querySelectorAll(".spk-btn").forEach(btn => {
        const on = active && btn.dataset.play === P.play;
        const text = on ? (P.state === "paused" ? "⏸ 一時停止中：" : "▶ 再生中：") + btn.dataset.label : "🔊 " + btn.dataset.label;
        if (btn.textContent !== text) btn.textContent = text;  // 同じなら書き換えない（MutationObserver が止まらなくなるため）
        btn.classList.toggle("spk-on", on);
      });
      const ctl = box.querySelector(".spk-ctl");
      if (ctl && ctl.hidden === active) ctl.hidden = !active;
      const pause = box.querySelector(".spk-pause");
      const pauseText = P.state === "paused" ? "▶ 再開" : "⏸ 一時停止";
      if (pause && pause.textContent !== pauseText) pause.textContent = pauseText;
      const status = box.querySelector(".spk-status");
      const statusNow = active ? statusText() : "";
      if (status && status.textContent !== statusNow) status.textContent = statusNow;
    });
  }

  function speakPart(token) {
    if (!hasTTS) { message(activeBox(), "このブラウザは読み上げに対応していません。設定で gTTS に切り替えてください"); stop(); return; }
    const it = P.items[P.idx];
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(it.parts[P.part]);
    u.lang = P.lang;
    u.rate = P.rate;
    const v = pickVoice(P.lang);
    if (v) u.voice = v;
    u.onend = () => {
      if (token !== P.token) return;
      if (++P.part < it.parts.length) { speakPart(token); syncUI(); }
      else advance();
    };
    u.onerror = e => {
      if (token !== P.token || e.error === "interrupted" || e.error === "canceled") return;
      message(activeBox(), "再生できませんでした（" + e.error + "）。設定で gTTS に切り替えてください");
      stop();
    };
    speechSynthesis.speak(u);
    if (speechSynthesis.paused) speechSynthesis.resume();  // iPhoneで一時停止のまま止まることがあるため
  }

  // いまの項目を読む。fromStart=false は gTTS の一時停止からの再開（止めたところから続ける）
  function playItem(fromStart) {
    const it = P.items[P.idx];
    const token = ++P.token;
    P.state = "playing";
    P.rate = settings().rate;
    if (it.src) {
      if (hasTTS) speechSynthesis.cancel();
      if (fromStart) audio.src = it.src;
      audio.defaultPlaybackRate = P.rate;
      audio.playbackRate = P.rate;
      audio.onended = () => { if (token === P.token) advance(); };
      audio.play().catch(e => {
        if (token !== P.token) return;
        message(activeBox(), "再生できませんでした（" + e.name + "）");
        stop();
      });
    } else {
      speakPart(token);  // ブラウザ方式は、いまの文（P.part）の頭から読む
    }
    syncUI();
  }

  // 次の項目へ。最後まで読んだら回数を数え、決めた回数になったら止める。間があれば待つ
  function advance() {
    const s = settings();
    P.part = 0;
    if (++P.idx >= P.items.length) {
      P.idx = 0;
      if (++P.rep >= s.repeat && s.repeat > 0) { stop(); return; }
    }
    if (s.gap > 0) {
      P.state = "gap";
      P.timer = setTimeout(() => { P.timer = null; playItem(true); }, s.gap * 1000);
      syncUI();
    } else {
      playItem(true);
    }
  }

  function start(box, btn) {
    stop();
    const all = JSON.parse(box.dataset.items);
    Object.assign(P, {
      items: JSON.parse(btn.dataset.play).map(i => all[i]), lang: box.dataset.lang || "en-US",
      box: box.dataset.id, play: btn.dataset.play, idx: 0, part: 0, rep: 0,
    });
    message(box, "");
    playItem(true);  // タップの処理の中で鳴らし始める（iPhoneの決まり）
  }

  function pause() {
    if (P.state === "playing") {
      P.token++;
      if (P.items[P.idx].src) audio.pause();
      else speechSynthesis.cancel();  // iPhoneは pause() が効かないことがあるので止める（再開は文の頭から）
      P.fromGap = false;
    } else if (P.state === "gap") {
      clearTimeout(P.timer);
      P.timer = null;
      P.fromGap = true;
    } else return;
    P.state = "paused";
    syncUI();
  }

  function resume() {
    if (P.state !== "paused") return;
    playItem(P.fromGap || !P.items[P.idx].src);
  }

  function stop() {
    P.token++;
    if (P.timer) { clearTimeout(P.timer); P.timer = null; }
    if (hasTTS) speechSynthesis.cancel();
    audio.pause();
    P.state = "idle";
    syncUI();
  }

  // 速度が変わったら、いま読んでいるものにもすぐ反映する
  function applyRate() {
    const rate = settings().rate;
    if (P.state !== "playing" || rate === P.rate) return;
    if (P.items[P.idx].src) { P.rate = rate; audio.defaultPlaybackRate = rate; audio.playbackRate = rate; }
    else playItem(true);  // 読み上げは途中で速さを変えられないので、いまの文の頭から新しい速さで読み直す
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest && e.target.closest(".spk-btn, .spk-pause, .spk-stop");
    if (!btn) return;
    e.preventDefault();
    const box = btn.closest(".spk");
    const mine = P.state !== "idle" && box.dataset.id === P.box;
    if (btn.classList.contains("spk-stop")) stop();
    else if (btn.classList.contains("spk-pause") || (mine && btn.dataset.play === P.play)) {
      P.state === "paused" ? resume() : pause();  // 再生中のボタンをもう一度押しても一時停止・再開になる
    } else start(box, btn);
  });

  // 再生中のボタンが画面から消えたら（ほかの画面へ移ったら）止める。描き直しで一瞬消えるだけのときは止めない
  let goneTimer = null;
  function watchPlayer() {
    applyRate();
    syncUI();
    if (P.state === "idle" || activeBox()) { clearTimeout(goneTimer); goneTimer = null; return; }
    if (!goneTimer) goneTimer = setTimeout(() => { goneTimer = null; if (P.state !== "idle" && !activeBox()) stop(); }, 1500);
  }

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
    watchPlayer();
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-rate"] });

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
    """再生・声の選択・候補一覧を閉じる処理の JavaScript と、再生の設定（速度・くり返し・間）をページに入れる。
    app.py で毎回呼ぶ（load_settings() のあとで）"""
    with st.container(key="speech_js"):  # 見た目には何も出さない（app.py のCSSで隠す）
        st.html(_SCRIPT, unsafe_allow_javascript=True)
        st.html(f'<div class="spk-settings" data-rate="{speed()}" data-repeat="{repeat()}" data-gap="{gap()}">再生の設定</div>')
