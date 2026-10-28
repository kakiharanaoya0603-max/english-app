# 英語表現帳（TOEIC 900点に向けた表現の登録・検索・脳内英作文の復習）

Streamlit Community Cloud ＋ Googleスプレッドシート保存。iPhoneのSafariで使う前提。設計は [DESIGN.md](DESIGN.md)。

## パソコンで動かす

```
pip install -r requirements.txt
python -m streamlit run app.py
```

`.streamlit/secrets.toml`（GitHubには入れない）があればスプレッドシートに、なければ `data/` フォルダに保存します。

## 写真から英文を読み取る（📒 表現帳 → 📷 写真）

文字の読み取り（OCR）は無料の Tesseract を使います（APIキー不要）。初期設定はブラウザの中で動く Tesseract.js で、パソコンでも `streamlit run` するだけで試せます。
「サーバーで読む」方式をパソコンで試すときは Tesseract 本体のインストールが必要です（Streamlit Cloud では `packages.txt` で自動で入ります）。

## 辞書データ

`ejdict.tsv.gz` は [EJDict-hand](https://github.com/kujirahand/EJDict)（kujirahand さん作成、パブリックドメイン／CC0）から
`tools/make_dict.py` で作ったものです（検索用のひらがなの読みを付けています）。
