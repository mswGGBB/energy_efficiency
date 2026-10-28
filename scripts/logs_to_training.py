"""CloudWatch Logs 에서 내보낸 로그(S3 export, .gz 또는 텍스트)를 재학습용 표로 바꿉니다.

사용:  python scripts/logs_to_training.py <로그 파일 또는 폴더> [출력.csv]
 - predict 로그(입력·예측)와 feedback 로그(실제값)를 request_id 로 이어 붙입니다.
 - 실제값이 있는 행만 라벨 있는 학습 데이터가 됩니다. 나머지는 개수만 보고합니다.
 - 출력 컬럼: 입력 항목들 + actual/pred(난방·냉방) + reward(= -오차비율, 강화학습의 보상 후보)
"""
import gzip
import json
import sys
from pathlib import Path

import pandas as pd


def read_records(path):
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    for f in files:
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                i = line.find("{")          # 앞의 시각/로그 접두어는 건너뜀
                if i < 0:
                    continue
                try:
                    rec = json.loads(line[i:])
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and "event" in rec and "request_id" in rec:
                    yield rec


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    recs = list(read_records(Path(sys.argv[1])))
    preds = {r["request_id"]: r for r in recs if r["event"] == "predict"}
    fbs = {r["feedback"]["request_id"]: r["feedback"] for r in recs if r["event"] == "feedback"}
    errors = sum(r["event"] == "predict_error" for r in recs)
    rows = []
    for rid, fb in fbs.items():
        p = preds.get(rid)
        if p is None:
            continue
        row = dict(p["inputs"], mode=p["mode"], request_id=rid, ts=p["ts"])
        for k, name in (("heating", "heating_mbtu"), ("cooling", "cooling_mbtu")):
            row[f"pred_{k}"] = p["prediction"][name]
            a = fb.get(f"actual_{k}_mbtu")
            row[f"actual_{k}"] = a
            row[f"reward_{k}"] = None if a is None else -abs(p["prediction"][name] - a) / max(abs(a), 1e-9)
        rows.append(row)
    df = pd.DataFrame(rows)
    print(f"예측 {len(preds)}건 / 피드백 {len(fbs)}건 / 오류 요청 {errors}건 -> 라벨 있는 학습 행 {len(df)}건")
    if len(sys.argv) > 2:
        df.to_csv(sys.argv[2], index=False, encoding="utf-8-sig")
        print("저장:", sys.argv[2])
    elif len(df):
        print(df.head().to_string())


if __name__ == "__main__":
    main()
