"""写真から英文を読み取る（OCR）。

写真を選ぶ・縮小・白黒化・傾きの補正は、すべて iPhone のブラウザの中（下の JavaScript）で行う。
読み取りは2つの方式を切り替えられる。
  browser … ブラウザの中で Tesseract.js（WebAssembly）が読む。写真も文字もサーバーに送らない
  server  … 前処理した小さな白黒画像だけをサーバーに送り、Tesseract（pytesseract）が読む
どちらも写真はどこにも保存しない（読み取った文字だけを使う）。

server 方式は Tesseract 本体が必要。Streamlit Cloud では packages.txt の tesseract-ocr で入る。
"""
import base64
import io
import re

import streamlit as st

ENGINES = {"browser": "📱 この端末で読む（Tesseract.js）", "server": "☁️ サーバーで読む（Tesseract）"}
TESSERACT_JS = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js"
MAX_SIDE = 1800  # 読み取る前に、長い辺をこのピクセル数まで縮小する

# ---------- 読み取り結果を文字にする ----------

MIN_CONFIDENCE = 50  # これより自信の低い語は、写真のふち・影・模様を文字と見間違えたものとみなして除く


def _keep_word(text: str, confidence: float) -> bool:
    if confidence >= MIN_CONFIDENCE:
        return True
    # 少しぼやけただけの普通の単語（小文字3文字以上）は残す
    return confidence >= 30 and re.fullmatch(r"[a-z]{3,}[.,;:!?]?", text) is not None


def assemble(paragraphs: list[list[list[tuple[str, float]]]]) -> str:
    """段落 → 行 → (語, 自信度0〜100) の読み取り結果から、見間違いらしい語・行を除いて文字にする"""
    out = []
    for paragraph in paragraphs:
        lines = []
        for line in paragraph:
            words = [(t.strip(), c) for t, c in line if t.strip()]
            kept = [t for t, c in words if _keep_word(t, c)]
            mean = sum(c for _, c in words) / len(words) if words else 0
            # 残った英字が2文字以下の行、全体に自信の低い行はごみとみなす
            if len(re.findall(r"[A-Za-z]", "".join(kept))) <= 2 or mean < MIN_CONFIDENCE:
                continue
            lines.append(" ".join(kept))
        if lines:
            out.append("\n".join(lines))
    return "\n\n".join(out)


# ---------- 文に区切る ----------

# 後ろのピリオドで文が終わらない略語（小文字で比べる）
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "no", "vs", "etc", "inc", "ltd", "co", "corp",
    "dept", "approx", "est", "fig", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "a.m", "p.m", "e.g", "i.e", "u.s", "u.k",
}


def clean_text(text: str) -> str:
    """読み取った文字を整える（行末のハイフンでの単語の分割をつなぐ・記号のゆれを直す）"""
    text = text.replace("\r\n", "\n").replace("­", "")
    text = re.sub(r"[‘’]", "'", re.sub(r"[“”]", '"', text))
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # 行末のハイフンで分かれた単語をつなぐ
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_sentences(text: str) -> list[str]:
    """英文を文ごとに区切る。空行は段落の区切り、1つの改行は文の途中の改行とみなしてつなぐ"""
    sentences = []
    for paragraph in re.split(r"\n\s*\n", clean_text(text)):
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
        start = 0
        # 「. ! ?」（後ろに閉じかっこ・引用符があってもよい）＋空白＋大文字・数字・引用符・かっこ のところで区切る
        for m in re.finditer(r"[.!?]+[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])", paragraph):
            last_word = re.search(r"([A-Za-z.]+)[.!?]+[\"')\]]*\s+$", paragraph[start : m.end()])
            if last_word and last_word.group(1).lower().strip(".") in _ABBREVIATIONS:
                continue
            if last_word and re.fullmatch(r"[A-Z]", last_word.group(1)):  # 「J. Smith」のような名前の頭文字
                continue
            sentences.append(paragraph[start : m.end()].strip())
            start = m.end()
        sentences.append(paragraph[start:].strip())
    # 英字が2文字未満のもの（ページ番号・記号だけの行など）は除く
    return [s for s in sentences if len(re.findall(r"[A-Za-z]", s)) >= 2]


# ---------- サーバーで読む ----------

def server_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def read_on_server(data_url: str) -> list[list[list[tuple[str, float]]]]:
    """ブラウザで前処理した画像（data URL）を Tesseract で読み、段落 → 行 → (語, 自信度) で返す。
    画像はメモリの中だけで使い、保存しない"""
    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))
    d = pytesseract.image_to_data(image, lang="eng", config="--psm 3", output_type=pytesseract.Output.DICT)
    paragraphs: dict[tuple, dict[tuple, list]] = {}
    for i, word in enumerate(d["text"]):
        if word.strip() and float(d["conf"][i]) >= 0:
            para = (d["block_num"][i], d["par_num"][i])
            paragraphs.setdefault(para, {}).setdefault((*para, d["line_num"][i]), []).append((word, float(d["conf"][i])))
    return [list(lines.values()) for lines in paragraphs.values()]


# ---------- 写真を選ぶ・前処理する・（端末で）読む部品 ----------

_HTML = """
<div class="ocr">
  <label class="ocr-pick">📷 写真を撮る・選ぶ<input type="file" accept="image/*" hidden></label>
  <div class="ocr-tools" hidden>
    <button type="button" data-rotate="-90">↺ 左に回す</button>
    <button type="button" data-rotate="90">↻ 右に回す</button>
    <button type="button" data-again>🔎 もう一度読む</button>
  </div>
  <div class="ocr-status"></div>
  <div class="ocr-bar" hidden><div></div></div>
  <canvas class="ocr-preview" hidden></canvas>
</div>
"""

_CSS = """
.ocr { font-family: inherit; color: var(--st-text-color); }
.ocr-pick {
  display: flex; align-items: center; justify-content: center; min-height: 52px; border-radius: 10px;
  font-size: 1.05rem; font-weight: 600; cursor: pointer; color: #fff; background: var(--st-primary-color);
  -webkit-tap-highlight-color: transparent;
}
.ocr-tools { display: flex; gap: 6px; margin-top: 8px; }
.ocr-tools[hidden], .ocr-bar[hidden], .ocr-preview[hidden] { display: none; }
.ocr-tools button {
  flex: 1; min-height: 44px; border-radius: 8px; font-size: .9rem; color: inherit; background: transparent;
  border: 1px solid rgba(128,128,128,.45); touch-action: manipulation; white-space: nowrap; padding: 0 4px;
}
.ocr-tools button:disabled { opacity: .45; }
.ocr-status { font-size: .9rem; margin-top: 8px; min-height: 1.2em; }
.ocr-status.err { color: #d33; }
.ocr-bar { height: 6px; border-radius: 3px; background: rgba(128,128,128,.25); margin-top: 6px; overflow: hidden; }
.ocr-bar div { height: 100%; width: 0; background: var(--st-primary-color); transition: width .2s; }
.ocr-preview { width: 100%; max-height: 220px; object-fit: contain; margin-top: 8px; border: 1px solid rgba(128,128,128,.3); border-radius: 6px; }
"""

_JS = """
const TESSERACT_JS = "%(tesseract_js)s";
const MAX_SIDE = %(max_side)d;

// ---------- 画像の前処理 ----------

async function loadImage(file) {
  // 写真の向き（EXIF）を反映して読み込む
  if (window.createImageBitmap) {
    try { return await createImageBitmap(file, { imageOrientation: "from-image" }); } catch (e) {}
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally { URL.revokeObjectURL(url); }
}

// 長い辺を MAX_SIDE までに縮小し、90°単位で回して、グレーの画素（0〜255）にする
function toGray(img, quarterTurns) {
  const w0 = img.width, h0 = img.height;
  const scale = Math.min(1, MAX_SIDE / Math.max(w0, h0));
  const sw = Math.round(w0 * scale), sh = Math.round(h0 * scale);
  const swap = quarterTurns %% 2 !== 0;
  const c = document.createElement("canvas");
  c.width = swap ? sh : sw; c.height = swap ? sw : sh;
  const ctx = c.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.translate(c.width / 2, c.height / 2);
  ctx.rotate(quarterTurns * Math.PI / 2);
  ctx.drawImage(img, -sw / 2, -sh / 2, sw, sh);
  const rgba = ctx.getImageData(0, 0, c.width, c.height).data;
  const gray = new Uint8ClampedArray(c.width * c.height);
  for (let i = 0, j = 0; j < gray.length; i += 4, j++)
    gray[j] = (rgba[i] * 299 + rgba[i + 1] * 587 + rgba[i + 2] * 114) / 1000;
  return { w: c.width, h: c.height, gray };
}

// 明るさの幅を広げる（薄い文字をはっきりさせる）。暗い方1%%・明るい方1%%を端とみなす
function stretch(g) {
  const hist = new Uint32Array(256);
  for (const v of g.gray) hist[v]++;
  const cut = g.gray.length * 0.01;
  let lo = 0, hi = 255, n = 0;
  for (; lo < 255; lo++) { n += hist[lo]; if (n > cut) break; }
  for (n = 0; hi > 0; hi--) { n += hist[hi]; if (n > cut) break; }
  if (hi - lo < 10) return;
  const k = 255 / (hi - lo);
  for (let i = 0; i < g.gray.length; i++) g.gray[i] = (g.gray[i] - lo) * k;
}

// 白黒にする（まわりの明るさと比べる方式なので、影や明るさのムラがあっても文字が残りやすい）
function binarize(g) {
  const { w, h, gray } = g;
  const integral = new Float64Array((w + 1) * (h + 1));
  for (let y = 0; y < h; y++) {
    let row = 0;
    for (let x = 0; x < w; x++) {
      row += gray[y * w + x];
      integral[(y + 1) * (w + 1) + x + 1] = integral[y * (w + 1) + x + 1] + row;
    }
  }
  const r = Math.max(8, Math.round(Math.max(w, h) / 50));
  const out = new Uint8ClampedArray(w * h);
  for (let y = 0; y < h; y++) {
    const y0 = Math.max(0, y - r), y1 = Math.min(h, y + r + 1);
    for (let x = 0; x < w; x++) {
      const x0 = Math.max(0, x - r), x1 = Math.min(w, x + r + 1);
      const sum = integral[y1 * (w + 1) + x1] - integral[y0 * (w + 1) + x1] - integral[y1 * (w + 1) + x0] + integral[y0 * (w + 1) + x0];
      const mean = sum / ((x1 - x0) * (y1 - y0));
      out[y * w + x] = gray[y * w + x] < mean * 0.85 ? 0 : 255;
    }
  }
  return { w, h, gray: out };
}

// 傾きの角度（度）を調べる。黒い点を少し回して、行ごとの黒い点の数のばらつきが一番大きくなる角度を探す
function skewAngle(bw) {
  const { w, h, gray } = bw;
  const step = Math.max(1, Math.round(Math.max(w, h) / 600));
  const pts = [];
  for (let y = 0; y < h; y += step)
    for (let x = 0; x < w; x += step)
      if (gray[y * w + x] === 0) pts.push(x / step, y / step);
  if (pts.length < 200) return 0;
  const size = Math.ceil(Math.hypot(w, h) / step) * 2 + 2;
  const bins = new Uint32Array(size);
  function score(deg) {
    const a = deg * Math.PI / 180, s = Math.sin(a), c = Math.cos(a);
    bins.fill(0);
    for (let i = 0; i < pts.length; i += 2) bins[Math.round(pts[i + 1] * c - pts[i] * s) + (size >> 1)]++;
    let sum = 0;
    for (const b of bins) sum += b * b;
    return sum;
  }
  let best = 0, bestScore = score(0);
  for (let d = -15; d <= 15; d += 0.5) { const sc = score(d); if (sc > bestScore) { best = d; bestScore = sc; } }
  for (let d = best - 0.4; d <= best + 0.4; d += 0.1) { const sc = score(d); if (sc > bestScore) { best = d; bestScore = sc; } }
  return best;
}

// グレーの画像を角度ぶん回す（はみ出したところは白にする）
function rotateGray(g, deg) {
  const src = document.createElement("canvas");
  drawTo(src, g);
  const dst = document.createElement("canvas");
  dst.width = g.w; dst.height = g.h;
  const ctx = dst.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, g.w, g.h);
  ctx.translate(g.w / 2, g.h / 2);
  ctx.rotate(-deg * Math.PI / 180);
  ctx.drawImage(src, -g.w / 2, -g.h / 2);
  const rgba = ctx.getImageData(0, 0, g.w, g.h).data;
  const gray = new Uint8ClampedArray(g.w * g.h);
  for (let i = 0; i < gray.length; i++) gray[i] = rgba[i * 4];
  return { w: g.w, h: g.h, gray };
}

function drawTo(canvas, g) {
  canvas.width = g.w; canvas.height = g.h;
  const img = new ImageData(g.w, g.h), d = img.data;
  for (let i = 0, j = 0; i < g.gray.length; i++, j += 4) { d[j] = d[j + 1] = d[j + 2] = g.gray[i]; d[j + 3] = 255; }
  canvas.getContext("2d").putImageData(img, 0, 0);
}

function preprocess(img, quarterTurns, useBinarize, canvas) {
  let g = toGray(img, quarterTurns);
  stretch(g);
  const angle = skewAngle(binarize(g));
  if (Math.abs(angle) >= 0.3) g = rotateGray(g, angle);
  drawTo(canvas, useBinarize ? binarize(g) : g);
  return angle;
}

// ---------- Tesseract.js（端末で読む） ----------

function loadScript(src) {
  if (window.Tesseract) return Promise.resolve();
  if (!window.__ocrScript) {
    window.__ocrScript = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src; s.onload = resolve;
      s.onerror = () => { window.__ocrScript = null; reject(new Error("Tesseract.js を読み込めませんでした（通信を確認してください）")); };
      document.head.appendChild(s);
    });
  }
  return window.__ocrScript;
}

// 読み取りの進み具合を知らせる先（部品が作り直されても、いまの部品に知らせる）
let report = () => {};

async function getWorker() {
  if (!window.__ocrWorker) {
    window.__ocrWorker = (async () => {
      await loadScript(TESSERACT_JS);
      const worker = await Tesseract.createWorker("eng", 1, { logger: m => report(m) });
      await worker.setParameters({ preserve_interword_spaces: "1", user_defined_dpi: "300" });
      return worker;
    })();
    window.__ocrWorker.catch(() => { window.__ocrWorker = null; });
  }
  return window.__ocrWorker;
}

// ---------- 部品 ----------

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const root = parentElement.querySelector(".ocr");
  root.__data = data;  // 設定（方式・白黒化）は Python から毎回届くので、最新のものを使う
  if (root.__ready) return;
  root.__ready = true;

  const input = root.querySelector("input[type=file]");
  const tools = root.querySelector(".ocr-tools");
  const status = root.querySelector(".ocr-status");
  const bar = root.querySelector(".ocr-bar");
  const canvas = root.querySelector(".ocr-preview");
  let image = null, turns = 0, busy = false;

  function show(text, isError) { status.textContent = text; status.classList.toggle("err", !!isError); }
  function progress(p) { bar.hidden = p == null; bar.firstElementChild.style.width = Math.round((p || 0) * 100) + "%%"; }
  function setBusy(b) { busy = b; tools.querySelectorAll("button").forEach(btn => btn.disabled = b); }

  async function run() {
    if (!image || busy) return;
    setBusy(true);
    try {
      show("画像を整えています…");
      progress(0);
      await new Promise(r => setTimeout(r, 30));  // 文字を画面に出してから重い処理を始める
      const angle = preprocess(image, turns, root.__data.binarize, canvas);
      canvas.hidden = false;
      const tilt = Math.abs(angle) >= 0.3 ? `（傾き ${angle.toFixed(1)}° を直しました）` : "";

      if (root.__data.engine === "server") {
        show("サーバーで読み取っています…" + tilt);
        const type = root.__data.binarize ? "image/png" : "image/jpeg";
        setTriggerValue("result", { image: canvas.toDataURL(type, 0.9), tilt });
        progress(null);
        return;
      }

      show("読み取りの準備をしています（初めてのときは数MBダウンロードします）…" + tilt);
      report = m => {
        if (m.status === "recognizing text") { show("文字を読み取っています… " + Math.round(m.progress * 100) + "%%" + tilt); progress(m.progress); }
        else if (m.status && m.status.startsWith("loading")) show("読み取りの準備をしています（初めてのときは数MBダウンロードします）… " + Math.round((m.progress || 0) * 100) + "%%");
      };
      const worker = await getWorker();
      const started = performance.now();
      const { data: result } = await worker.recognize(canvas);
      const seconds = ((performance.now() - started) / 1000).toFixed(1);
      progress(null);
      show(`読み取りました（${seconds}秒）` + tilt);
      // 段落 → 行 → [語, 自信度]（見間違いらしい語は Python 側で除く）
      const paragraphs = result.paragraphs.map(p => p.lines.map(l => l.words.map(w => [w.text, w.confidence])));
      setTriggerValue("result", { paragraphs });
    } catch (e) {
      progress(null);
      show("読み取れませんでした：" + (e && e.message ? e.message : e) + "。「読み取りの設定」でサーバーで読む方式も試せます", true);
    } finally {
      setBusy(false);
    }
  }

  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    input.value = "";  // 同じ写真をもう一度選んでも反応するように
    if (!file) return;
    try {
      show("写真を読み込んでいます…");
      image = await loadImage(file);  // 写真はこの画面の中だけで使い、どこにも保存しない
      turns = 0;
      tools.hidden = false;
      run();
    } catch (e) {
      show("この写真を開けませんでした（" + (e && e.message ? e.message : e) + "）", true);
    }
  });
  tools.addEventListener("click", e => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.rotate) turns = (turns + (btn.dataset.rotate === "90" ? 1 : 3)) %% 4;
    run();
  });
}
""" % {"tesseract_js": TESSERACT_JS, "max_side": MAX_SIDE}

_component = st.components.v2.component("photo_ocr", html=_HTML, css=_CSS, js=_JS)


def picker(engine: str, binarize: bool, key: str):
    """写真を選ぶボタン・前処理・（browser 方式なら）読み取りまでを行う部品。
    読み終わると result が {"paragraphs": ...}（browser）か {"image": data URL}（server）になる"""
    return _component(data={"engine": engine, "binarize": binarize}, key=key, on_result_change=lambda: None)
