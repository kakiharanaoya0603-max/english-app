"""検索用の文字の処理（表現帳の検索・辞書の検索・辞書データの作成で共通に使う）"""
import re
import unicodedata

import pykakasi

_kakasi = pykakasi.kakasi()


def normalize(text: str) -> str:
    """検索用に、全角/半角・大文字/小文字・カタカナ/ひらがな・記号やスペースの違いをなくす"""
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)
    return re.sub(r"[\s\[\]<>()・/／,，、。;；《》『』〈〉…'\"!?！？.\-]", "", text)


def reading(text: str) -> str:
    """漢字をひらがなの読みにする（例：調達する → ちょうたつする）"""
    return normalize("".join(part["hira"] for part in _kakasi.convert(str(text))))


def normalize_en(text: str) -> str:
    """英語の比較用（大文字小文字・前後や連続のスペースの違いをなくす）"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text)).lower()).strip()


def is_english(text: str) -> bool:
    """英字・数字・記号だけなら英語の検索とみなす"""
    return bool(re.fullmatch(r"[\x20-\x7e]+", unicodedata.normalize("NFKC", text).strip()))


# ---------- 英文を文に区切る（写真の読み取り・音声の再生で使う） ----------

# 後ろのピリオドで文が終わらない略語（小文字で比べる）
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "no", "vs", "etc", "inc", "ltd", "co", "corp",
    "dept", "approx", "est", "fig", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "a.m", "p.m", "e.g", "i.e", "u.s", "u.k",
}


def clean_text(text: str) -> str:
    """読み取った文字を整える（行末のハイフンでの単語の分割をつなぐ・記号のゆれを直す）"""
    text = text.replace("\r\n", "\n").replace("\u00ad", "")
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
