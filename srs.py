"""復習の予定（簡易な間隔反復）と、ホーム画面の数字の計算"""
import datetime as dt

import pandas as pd

# 「言えた」が続いたときの間隔（日）。段階1で1日後、段階2で3日後…段階5以降は30日ごと
INTERVALS = [1, 3, 7, 14, 30]
GRADES = ["言えた", "あやしい", "言えなかった"]


def next_schedule(stage: int, grade: str, today: dt.date) -> tuple[int, dt.date]:
    """評価から (新しい段階, 次回復習日) を決める"""
    if grade == "言えた":
        stage = min(stage + 1, len(INTERVALS))
        return stage, today + dt.timedelta(days=INTERVALS[stage - 1])
    if grade == "あやしい":
        return stage, today + dt.timedelta(days=1)
    return 0, today  # 言えなかった：今日中にもう一度


def due(expressions: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """今日までに復習する予定の表現（予定日の古い順）"""
    if expressions.empty:
        return expressions
    mask = expressions["次回復習日"].map(lambda d: d is None or pd.isna(d) or d <= today)
    return expressions[mask].sort_values("次回復習日", na_position="first")


def streak(logs: pd.DataFrame, today: dt.date) -> int:
    """連続学習日数。今日まだ復習していなくても、昨日まで続いていれば途切れていない扱いにする"""
    days = set(logs["日付"].dropna())
    day = today if today in days else today - dt.timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= dt.timedelta(days=1)
    return count


def reviewed_today(logs: pd.DataFrame, today: dt.date) -> int:
    """今日復習した表現の数（同じ表現を何度やっても1つと数える）"""
    return logs.loc[logs["日付"] == today, "表現ID"].nunique()
