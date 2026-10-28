"""データの保存・読み込みを担当するファイル。

Googleスプレッドシートの設定（.streamlit/secrets.toml）があればスプレッドシートに、
なければパソコン内の data フォルダの CSV に保存する。
スプレッドシートでは、下の TABLES のシート名ごとにタブが作られる。
"""
import datetime as dt
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

TABLES = {
    # マイ表現帳。段階〜復習回数は復習のたびに自動で書き換わる
    "表現": [
        "ID", "英語", "日本語訳", "例文", "例文訳", "品詞", "出典", "メモ", "タグ",
        "登録日", "段階", "次回復習日", "最終復習日", "復習回数",
    ],
    # 復習した記録（今日の復習数・連続学習日数の計算に使う）
    "復習ログ": ["日時", "表現ID", "向き", "評価"],
    "設定": ["項目", "値"],
}
# 表現のうち、登録・編集画面で入力する項目
INPUT_COLUMNS = ["英語", "日本語訳", "例文", "例文訳", "品詞", "出典", "メモ", "タグ"]
SOURCES = ["Distinction 2000", "Distinction 1", "TOEIC公式", "記事", "その他"]
PARTS_OF_SPEECH = ["", "名詞", "動詞", "形容詞", "副詞", "句動詞", "熟語・フレーズ", "前置詞", "接続詞", "その他"]
TAG_SEP = "／"
LOCAL_DIR = Path(__file__).parent / "data"


def use_gsheets() -> bool:
    """Googleスプレッドシートの設定がされているかどうか"""
    try:
        return "gcp_service_account" in st.secrets and "spreadsheet_url" in st.secrets
    except Exception:  # secrets.toml がまだ無いとき
        return False


# ---------- 共通の読み書き ----------

@st.cache_resource
def _spreadsheet():
    import gspread

    client = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    return client.open_by_url(st.secrets["spreadsheet_url"])


def _worksheet(name: str):
    """シート（タブ）を取得する。まだ無ければ見出し行つきで作る"""
    import gspread

    sh = _spreadsheet()
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=len(TABLES[name]))
        ws.append_row(TABLES[name])
        return ws


def _csv_path(name: str) -> Path:
    return LOCAL_DIR / f"{name}.csv"


@st.cache_data(ttl=300)
def _load_table(name: str) -> pd.DataFrame:
    """表をすべて文字列のまま読み込む（数値や日付への変換は呼び出し側で行う）"""
    columns = TABLES[name]
    if use_gsheets():
        records = _worksheet(name).get_all_records(numericise_ignore=["all"])
        df = pd.DataFrame(records, columns=columns)
    else:
        path = _csv_path(name)
        df = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=columns)
    return df.fillna("").astype(str)


def _to_rows(df: pd.DataFrame, name: str) -> list[list[str]]:
    return df[TABLES[name]].fillna("").astype(str).values.tolist()


def _save_table(name: str, df: pd.DataFrame) -> None:
    """表をまるごと書き直す（削除・編集のとき用）"""
    rows = [TABLES[name]] + _to_rows(df, name)
    if use_gsheets():
        ws = _worksheet(name)
        if len(rows) > ws.row_count:
            ws.resize(rows=len(rows) + 500)
        ws.clear()
        # RAW：「=」で始まるメモなどが数式として扱われないよう、書いたままの文字で保存する
        ws.update(rows, value_input_option="RAW")
    else:
        LOCAL_DIR.mkdir(exist_ok=True)
        df[TABLES[name]].to_csv(_csv_path(name), index=False)
    _load_table.clear()  # 次回は保存先から読み直す


def _append_rows(name: str, df: pd.DataFrame) -> None:
    """表の末尾に行を足す（追加のとき用）"""
    if df.empty:
        return
    if use_gsheets():
        _worksheet(name).append_rows(_to_rows(df, name), value_input_option="RAW")
    else:
        LOCAL_DIR.mkdir(exist_ok=True)
        path = _csv_path(name)
        df[TABLES[name]].to_csv(path, mode="a", header=not path.exists(), index=False)
    _load_table.clear()


def _update_row(name: str, row: dict) -> None:
    """1列目（ID）が一致する1行だけを書き換える（復習のたびに表全体を書き直すと遅いため）"""
    if use_gsheets():
        ws = _worksheet(name)
        cell = ws.find(str(row[TABLES[name][0]]), in_column=1)
        if cell is None:
            return
        values = [str(row.get(c, "")) for c in TABLES[name]]
        ws.update([values], f"A{cell.row}", value_input_option="RAW")
        _load_table.clear()
    else:
        df = _load_table(name).copy()
        key = TABLES[name][0]
        df.loc[df[key] == str(row[key]), list(row)] = [str(v) for v in row.values()]
        _save_table(name, df)


# ---------- 表現 ----------

def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", None), errors="coerce").dt.date


def load_expressions() -> pd.DataFrame:
    """表現を登録した順で返す（日付は date 型、未設定は None）"""
    df = _load_table("表現").copy()
    for col in ["登録日", "次回復習日", "最終復習日"]:
        df[col] = _to_date(df[col])
    for col in ["段階", "復習回数"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df.set_index("ID", drop=False).rename_axis(None)


def new_expression(values: dict, today: dt.date) -> dict:
    """入力された項目から、保存する1行を作る（登録した日から復習の対象になる）"""
    row = {c: str(values.get(c, "") or "").strip() for c in INPUT_COLUMNS}
    row.update({
        "ID": "E" + uuid.uuid4().hex[:10],
        "登録日": today.isoformat(),
        "段階": 0,
        "次回復習日": today.isoformat(),
        "最終復習日": "",
        "復習回数": 0,
    })
    return row


def add_expressions(rows: list[dict]) -> None:
    _append_rows("表現", pd.DataFrame(rows, columns=TABLES["表現"]))


def update_expression(expr_id: str, values: dict) -> None:
    """表現の一部の項目を書き換える（values は {列名: 値}）"""
    current = _load_table("表現")
    match = current[current["ID"] == expr_id]
    if match.empty:
        return
    row = match.iloc[0].to_dict()
    row.update({k: "" if v is None else (v.isoformat() if isinstance(v, dt.date) else v) for k, v in values.items()})
    _update_row("表現", row)


def delete_expression(expr_id: str) -> None:
    df = _load_table("表現")
    _save_table("表現", df[df["ID"] != expr_id])


# ---------- 復習ログ ----------

def load_logs() -> pd.DataFrame:
    df = _load_table("復習ログ").copy()
    df["日時"] = pd.to_datetime(df["日時"], errors="coerce")
    df["日付"] = df["日時"].dt.date
    return df


def add_log(when: dt.datetime, expr_id: str, direction: str, grade: str) -> None:
    row = {"日時": when.strftime("%Y-%m-%d %H:%M:%S"), "表現ID": expr_id, "向き": direction, "評価": grade}
    _append_rows("復習ログ", pd.DataFrame([row]))


# ---------- 設定 ----------

def load_settings() -> dict:
    """設定を {項目: 値} の形で返す（値はすべて文字列）"""
    df = _load_table("設定")
    return dict(zip(df["項目"], df["値"]))


def save_settings(settings: dict) -> None:
    _save_table("設定", pd.DataFrame(list(settings.items()), columns=TABLES["設定"]))
