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
