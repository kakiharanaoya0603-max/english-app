"""英和辞書（EJDict-hand）とマイ表現帳の検索。

EJDict-hand は kujirahand さんが公開しているパブリックドメイン（CC0）の英和辞書。
ejdict.tsv.gz は tools/make_dict.py で作る。
"""
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from textutil import is_english, normalize, normalize_en, reading

DICT_PATH = Path(__file__).parent / "ejdict.tsv.gz"
CREDIT = (
    "英和辞書：[EJDict-hand](https://github.com/kujirahand/EJDict)（kujirahand さん作成・パブリックドメイン／CC0）"
)


@st.cache_data
def load() -> pd.DataFrame:
    df = pd.read_csv(DICT_PATH, sep="\t", dtype=str, keep_default_na=False)
    df["基本"] = df["基本"].astype(int)
    # 「color, colour」のような別つづりも、1つずつ照合できるよう改行で区切って持つ
    df["_見出し"] = "\n" + df["英語"].str.lower().str.replace(r"\s*,\s*", "\n", regex=True) + "\n"
    df["_意味"] = df["意味"].map(normalize)
    df["_長さ"] = df["英語"].str.len()
    return df


def _japanese_words(term: str) -> set[str]:
    """日本語の検索語を、書いたままの形と読み（ひらがな）にする"""
    return {normalize(term), reading(term)} - {""}


def search(query: str) -> pd.DataFrame:
    """辞書を検索して、近いものから順に返す"""
    df = load()
    query = query.strip()
    if not query:
        return df.iloc[0:0]
    if is_english(query):
        q = normalize_en(query)
        esc = re.escape(q)
        exact = df["_見出し"].str.contains(f"\n{esc}\n")
        prefix = df["_見出し"].str.contains(f"\n{esc}")
        word = df["_見出し"].str.contains(rf"\b{esc}")
        hit = word if len(q) < 3 else (word | df["_見出し"].str.contains(esc, regex=False))
        rank = (~exact).astype(int) + (~prefix).astype(int) + (~word).astype(int)
    else:
        hit = pd.Series(True, index=df.index)
        exact = pd.Series(True, index=df.index)
        main = pd.Series(True, index=df.index)  # EJDictでは『』で囲まれた訳が主な意味
        literal = pd.Series(True, index=df.index)
        for term in query.split():
            words = _japanese_words(term)
            pattern = "|".join(map(re.escape, words))
            items = "|".join(f"\n{re.escape(w)}\n" for w in words)
            in_text = df["_意味"].str.contains(pattern)
            hit &= in_text | df["読み"].str.contains(pattern)
            exact &= df["訳語"].str.contains(items) | df["訳語読み"].str.contains(items)
            main &= df["意味"].str.contains(f"『{re.escape(term)}』")
            literal &= in_text
        rank = (~exact).astype(int) * 4 + (~main).astype(int) * 2 + (~literal).astype(int)
    if not hit.any() and len(query.split()) > 1:
        # 「look into」のような熟語が辞書に無いときは、単語ごとの結果を出す
        return pd.concat([search(w) for w in query.split()]).drop_duplicates("英語")
    result = df[hit].assign(_rank=rank[hit])
    # 近い順 → よく使う語 → 短い語
    return result.sort_values(["_rank", "基本", "_長さ"], ascending=[True, False, True])


def search_expressions(expressions: pd.DataFrame, query: str) -> pd.DataFrame:
    """マイ表現帳を検索する。英語なら英語・例文、日本語なら訳・例文訳・メモ・タグを探す"""
    query = query.strip()
    if expressions.empty or not query:
        return expressions.iloc[0:0]
    if is_english(query):
        q = normalize_en(query)
        english = expressions["英語"].map(normalize_en)
        hit = english.str.contains(q, regex=False) | expressions["例文"].map(normalize_en).str.contains(q, regex=False)
        rank = (english != q).astype(int) + (~english.str.startswith(q)).astype(int)
        return expressions[hit].assign(_rank=rank[hit]).sort_values("_rank").drop(columns="_rank")
    texts = expressions[["日本語訳", "例文訳", "メモ", "タグ", "英語"]].astype(str).agg(" ".join, axis=1)
    keys = texts.map(normalize) + "\n" + texts.map(reading)
    hit = pd.Series(True, index=expressions.index)
    for term in query.split():
        hit &= keys.str.contains("|".join(map(re.escape, _japanese_words(term))))
    return expressions[hit]
