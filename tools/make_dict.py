"""EJDict-hand（パブリックドメインの英和辞書）から ejdict.tsv.gz を作る。

1. https://github.com/kujirahand/EJDict をダウンロードして展開する
2. python tools/make_dict.py <展開したフォルダ>
   （例：python tools/make_dict.py C:/Users/.../EJDict-master）

列：英語、意味、読み（意味をひらがなにしたもの。漢字の訳をひらがなで検索するため）、
    訳語・訳語読み（意味を1語ずつに分けたもの。完全に一致する訳を上位に出すため）、基本（よく使う2000語なら1）
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from textutil import normalize, reading  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "ejdict.tsv.gz"


def split_terms(meaning: str) -> list[str]:
    """意味を1つずつの訳語に分ける（例：'…を捨てる,断念する / 奔放さ' → ['捨てる', '断念する', '奔放さ']）"""
    meaning = re.sub(r"《[^》]*》|〈[^〉]*〉|\([^)]*\)|（[^）]*）|\{[^}]*\}", "", meaning)
    terms = re.split(r"[/;,，、]", meaning)
    # 「…を」「…に」のような目的語の印を取る
    return [t for t in (re.sub(r"^\s*…*[をにがのへとで]?\s*", "", t).strip() for t in terms) if t]


def main(src_dir: Path) -> None:
    rows = []
    for path in sorted((src_dir / "src").glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                word, meaning = line.split("\t", 1)
                rows.append((word.strip(), meaning.strip()))
    df = pd.DataFrame(rows, columns=["英語", "意味"]).drop_duplicates()
    basic = set((src_dir / "frequency" / "2000.txt").read_text(encoding="utf-8").split())
    df["読み"] = df["意味"].map(reading)
    terms = df["意味"].map(split_terms)
    df["訳語"] = terms.map(lambda ts: "\n" + "\n".join(normalize(t) for t in ts) + "\n")
    df["訳語読み"] = terms.map(lambda ts: "\n" + "\n".join(reading(t) for t in ts) + "\n")
    df["基本"] = df["英語"].isin(basic).astype(int)
    df.to_csv(OUT, sep="\t", index=False, compression="gzip")
    print(f"{len(df)}語を {OUT.name} に書き出しました")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
