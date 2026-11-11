"""서비스 로그(CloudWatch 내보내기, `docker compose logs`, 텍스트·.gz)를 재학습용 표로 바꿉니다.

사용:
    python scripts/logs_to_training.py <로그 파일 또는 폴더> [<로그 2> ...] [출력.csv 또는 출력.csv.gz]

 - predict 로그(입력·예측)와 feedback 로그(실제값)를 request_id 로 이어 붙입니다.
 - 실제값이 있는 행만 라벨 있는 학습 데이터가 됩니다. 나머지는 개수만 보고합니다.
 - 같은 request_id 가 여러 번 나오면(내보내기 겹침 등) 한 번만 씁니다. 피드백이 여러 번이면 마지막 값을 씁니다.
 - 출력 컬럼: 입력 항목들 + actual/pred(난방·냉방) + reward(= -오차비율, 강화학습의 보상 후보) + model_tag, source
 - 출력 파일 이름이 .gz 로 끝나면 압축해서 저장합니다. 재학습에는 data/retrain_logs.csv.gz 로 저장하세요.
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
                i = line.find("{")          # 앞의 시각·컨테이너 이름 같은 접두어는 건너뜀
                if i < 0:
                    continue
                try:
                    rec = json.loads(line[i:])
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and "event" in rec and "request_id" in rec:
                    rec["_source"] = f.name
                    yield rec


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    out = args.pop() if len(args) > 1 and args[-1].lower().endswith((".csv", ".csv.gz")) else None
    recs = [r for a in args for r in read_records(Path(a))]

    preds, fbs, dup_pred = {}, {}, 0
    for r in recs:
        if r["event"] == "predict":
            dup_pred += r["request_id"] in preds
            preds.setdefault(r["request_id"], r)
        elif r["event"] == "feedback":
            fbs[r["feedback"]["request_id"]] = r["feedback"]       # 마지막 값이 이김
    errors = sum(r["event"] == "predict_error" for r in recs)

    rows = []
    for rid, fb in fbs.items():
        p = preds.get(rid)
        if p is None:
            continue
        row = dict(p["inputs"], mode=p["mode"], request_id=rid, ts=p["ts"], model_tag=p.get("model_tag"), source=p["_source"])
        for k, name in (("heating", "heating_mbtu"), ("cooling", "cooling_mbtu")):
            row[f"pred_{k}"] = p["prediction"][name]
            a = fb.get(f"actual_{k}_mbtu")
            row[f"actual_{k}"] = a
            row[f"reward_{k}"] = None if a is None else -abs(p["prediction"][name] - a) / max(abs(a), 1e-9)
        rows.append(row)
    df = pd.DataFrame(rows)

    print(f"예측 {len(preds)}건 / 피드백 {len(fbs)}건 / 오류 요청 {errors}건 (중복 예측 기록 {dup_pred}건 무시)")
    print(f"-> 예측과 피드백이 이어진, 라벨 있는 학습 행 {len(df)}건")
    unmatched = len(set(fbs) - set(preds))
    if unmatched:
        print(f"   (짝이 되는 예측 로그가 없는 피드백 {unmatched}건은 제외: 로그 범위가 모자라면 더 넓게 내보내세요)")
    if len(df):
        print("   모드별:", df["mode"].value_counts().to_dict(), "| 모델 태그별:", df["model_tag"].fillna("(없음)").value_counts().to_dict())
        for k in ("heating", "cooling"):
            e = (df[f"pred_{k}"] - df[f"actual_{k}"]).astype(float)
            print(f"   {k}: 서비스가 낸 예측의 MAE {e.abs().mean():.2f} MBtu, 평균 편향 {e.mean():+.2f} (예측 - 실제)")
    if out:
        df.to_csv(out, index=False, encoding="utf-8-sig" if not out.lower().endswith(".gz") else "utf-8")
        print("저장:", out)
    elif len(df):
        print(df.head().to_string())


if __name__ == "__main__":
    main()
