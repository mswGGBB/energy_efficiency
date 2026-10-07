"""ResStock 냉난방 부하 모델 학습 (상세 모드 + 간편 모드).

실행 (저장소 루트에서):
    python scripts/resstock_train.py

입력 : data/resstock_sample_v2.csv.gz  (또는 같은 이름의 .csv)
출력 : models/resstock_detail.joblib, models/resstock_simple.joblib, docs/resstock_metrics.json

설계 메모
- 맞히는 값: 연간 난방·냉방 부하(MBtu). 면적이 클수록 총량이 커지므로 '면적(ft²)당 부하'를 학습하고 면적을 곱해 되돌립니다.
- 평가: 전체의 20%를 학습에 쓰지 않고 따로 떼어 점수를 냅니다(random_state=42). 점수를 낸 뒤, 배포용 모델은 전체로 다시 학습합니다.
- 점수: R²(1에 가까울수록 좋음, 목표 0.85), MAE(MBtu), 정확도 = 100 x (1 - 오차 합 / 실제값 합).
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resstock_prep import FT2_PER_PYEONG, MODES, TARGETS, build_table  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PARAMS = dict(max_iter=1000, learning_rate=0.05, max_leaf_nodes=63, l2_regularization=1.0,
              early_stopping=True, validation_fraction=0.1, n_iter_no_change=30, random_state=42)
SIZE_BINS = [(0, 10, "10평 미만"), (10, 20, "10평대"), (20, 30, "20평대"), (30, 40, "30평대"), (40, 60, "40~59평"), (60, 1000, "60평 이상")]
NAMES = {TARGETS[0]: "heating", TARGETS[1]: "cooling"}


def find_data():
    for p in [ROOT / "data" / "resstock_sample_v2.csv.gz", ROOT / "data" / "resstock_sample_v2.csv",
              HERE / "resstock_sample_v2.csv", Path.cwd() / "resstock_sample_v2.csv"]:
        if p.exists():
            return p
    sys.exit("resstock_sample_v2.csv(.gz)를 찾지 못했습니다. data/ 폴더에 넣어주세요.")


def accuracy(actual, pred):
    return float(100 * (1 - np.abs(actual - pred).sum() / np.abs(actual).sum()))


def score(actual, pred, base=None):
    out = dict(r2=float(r2_score(actual, pred)), mae=float(mean_absolute_error(actual, pred)), accuracy=accuracy(actual, pred))
    if base is not None:
        out["baseline_mae"] = float(mean_absolute_error(actual, np.full_like(actual, base)))
    return out


def fit(Xe, y, ft2, mask, idx):
    models = {}
    for t in TARGETS:
        m = HistGradientBoostingRegressor(categorical_features=mask if any(mask) else None, **PARAMS)
        m.fit(Xe.iloc[idx], (y[t].values / ft2)[idx])      # 면적당 부하를 학습
        models[t] = m
    return models


def predict(models, Xe, ft2):
    return {t: np.clip(m.predict(Xe), 0, None) * ft2 for t, m in models.items()}   # 면적을 곱해 총량으로


def run_mode(mode, X, y):
    spec = MODES[mode]
    num, cat = spec["numeric"], spec["categorical"]
    feats = num + spec["derived"] + cat
    ft2 = X["area_pyeong"].values * FT2_PER_PYEONG

    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    Xe = X[feats].copy()
    Xe[cat] = enc.fit_transform(Xe[cat])
    mask = [c in cat for c in feats]

    tr, te = train_test_split(np.arange(len(Xe)), test_size=0.2, random_state=42)
    pred = predict(fit(Xe, y, ft2, mask, tr), Xe.iloc[te], ft2[te])

    pyeong, btype = X["area_pyeong"].values[te], X["building_type"].values[te]
    metrics = {"n_train": int(len(tr)), "n_test": int(len(te)), "inputs": len(num) + len(cat), "overall": {}, "by_size": [], "by_building_type": {}}
    for t in TARGETS:
        base = float(y[t].values[tr].mean())   # 단순 기준: 학습 평균값만 답하기
        metrics["overall"][NAMES[t]] = score(y[t].values[te], pred[t], base)
    for lo, hi, label in SIZE_BINS:
        s = (pyeong >= lo) & (pyeong < hi)
        row = {"size": label, "n": int(s.sum())}
        for t in TARGETS:
            row[NAMES[t]] = score(y[t].values[te][s], pred[t][s])
        metrics["by_size"].append(row)
    for b in pd.Series(btype).value_counts().index:
        s = btype == b
        metrics["by_building_type"][b] = {"n": int(s.sum()), **{NAMES[t]: float(r2_score(y[t].values[te][s], pred[t][s])) for t in TARGETS}}

    # 배포용: 전체 데이터로 다시 학습
    final = fit(Xe, y, ft2, mask, np.arange(len(Xe)))
    ranges = {c: [float(X[c].min()), float(X[c].max())] for c in num}
    artifact = dict(mode=mode, features=feats, inputs=num + cat, numeric=num, categorical=cat, derived=spec["derived"],
                    encoder=enc, categories={c: [str(v) for v in cats_] for c, cats_ in zip(cat, enc.categories_)},
                    models=final, ranges=ranges, metrics=metrics, sklearn_version=sklearn.__version__,
                    note="학습은 면적당 부하(MBtu/ft²) 기준, 예측은 면적을 곱해 연간 MBtu로 반환")
    return artifact, metrics


def main():
    data = find_data()
    print("데이터:", data)
    X, y = build_table(pd.read_csv(data, low_memory=False))
    print(f"학습표: {X.shape[0]}행 (6000 ft² 초과 제외), 면적 {X['area_pyeong'].min():.1f}~{X['area_pyeong'].max():.1f}평\n")
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    all_metrics = {}
    for mode in ["detail", "simple"]:
        artifact, m = run_mode(mode, X, y)
        joblib.dump(artifact, ROOT / "models" / f"resstock_{mode}.joblib", compress=3)
        all_metrics[mode] = m
        print(f"===== {mode} 모드 (입력 {m['inputs']}개, 학습 {m['n_train']} / 검증 {m['n_test']}) =====")
        for k in ["heating", "cooling"]:
            o = m["overall"][k]
            print(f"  {k:<8} R²={o['r2']:.3f}  MAE={o['mae']:.2f} MBtu (단순기준 {o['baseline_mae']:.2f})  정확도={o['accuracy']:.1f}%")
        print("  평 구간별 R² (난방 / 냉방):")
        for r in m["by_size"]:
            print(f"    {r['size']:<8} n={r['n']:<5} {r['heating']['r2']:.3f} / {r['cooling']['r2']:.3f}")
        print()
    all_metrics["sklearn_version"] = sklearn.__version__
    (ROOT / "docs" / "resstock_metrics.json").write_text(json.dumps(all_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print("저장 완료: models/resstock_{detail,simple}.joblib, docs/resstock_metrics.json")


if __name__ == "__main__":
    main()
