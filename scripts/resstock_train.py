"""ResStock 냉난방 부하 모델 학습 (상세 모드 + 간편 모드).

실행 (저장소 루트에서):
    python scripts/resstock_train.py                       # 기본: 전체의 80%로 점수를 내고, 배포용은 전체로 다시 학습
    python scripts/resstock_train.py --experiment          # 재학습 실험: 아래 설명 참고
    python scripts/resstock_train.py --experiment --logs data/retrain_logs.csv.gz

입력 : data/resstock_sample_v2.csv.gz  (또는 같은 이름의 .csv)
출력 : models/resstock_detail.joblib, models/resstock_simple.joblib, docs/resstock_metrics.json

설계 메모
- 맞히는 값: 연간 난방·냉방 부하(MBtu). 면적이 클수록 총량이 커지므로 '면적(ft²)당 부하'를 학습하고 면적을 곱해 되돌립니다.
- 점수: R²(1에 가까울수록 좋음, 목표 0.85), MAE(MBtu), 정확도 = 100 x (1 - 오차 합 / 실제값 합).

--experiment (재학습 전/후 비교용)
- 데이터를 train / pool / holdout 으로 나눕니다(resstock_prep.experiment_split, seed 고정, 방식은 SPLIT_SCHEME).
- 모델은 train 만으로 학습합니다(재학습 전 = v1). 점수는 holdout 으로만 냅니다. 배포용 모델도 이 모델 그대로입니다.
- 서비스 로그에서 모은 '정답 있는 요청'(--logs 파일, 또는 data/retrain_logs.csv.gz)이 있으면 train 에 더해 학습합니다(재학습 후 = v2).
- 로그의 정답은 pool 건물에서만 나와야 합니다(send_test_requests.py 가 pool 만 보냄). holdout 건물이 섞이지 않았는지는 retrain_report.py 가 검사합니다.
"""
import argparse
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
from resstock_prep import FT2_PER_PYEONG, MODES, TARGETS, add_derived, build_table, experiment_split  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PARAMS = dict(max_iter=1000, learning_rate=0.05, max_leaf_nodes=63, l2_regularization=1.0,
              early_stopping=True, validation_fraction=0.1, n_iter_no_change=30, random_state=42)
SIZE_BINS = [(0, 10, "10평 미만"), (10, 20, "10평대"), (20, 30, "20평대"), (30, 40, "30평대"), (40, 60, "40~59평"), (60, 1000, "60평 이상")]
NAMES = {TARGETS[0]: "heating", TARGETS[1]: "cooling"}
DEFAULT_LOGS = ROOT / "data" / "retrain_logs.csv.gz"


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


def load_log_rows(path, mode):
    """logs_to_training.py 가 만든 CSV -> (입력표 X, 정답표 y). 이 모드의 입력이 모두 있고 정답(난방·냉방)이 둘 다 있는 행만 씁니다."""
    spec = MODES[mode]
    cols = spec["numeric"] + spec["categorical"]
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])   # 'None'(설비 없음)을 결측으로 오해하지 않도록
    need_actual = ["actual_heating", "actual_cooling"]
    if any(c not in df.columns for c in cols + need_actual):
        return None, None, {"rows_in_file": int(len(df)), "used": 0}
    d = df.drop_duplicates("request_id") if "request_id" in df.columns else df
    d = d.dropna(subset=cols + need_actual)
    for c in spec["numeric"] + need_actual:
        d = d[pd.to_numeric(d[c], errors="coerce").notna()]
    d = d.reset_index(drop=True)
    X = d[cols].copy()
    for c in spec["numeric"]:
        X[c] = pd.to_numeric(X[c])
    if spec["derived"]:
        X = add_derived(X)
    y = pd.DataFrame({TARGETS[0]: pd.to_numeric(d["actual_heating"]), TARGETS[1]: pd.to_numeric(d["actual_cooling"])})
    ok = (y >= 0).all(axis=1) & (X["area_pyeong"] > 0)            # 음수 정답, 0 이하 면적은 제외
    return X[ok].reset_index(drop=True), y[ok].reset_index(drop=True), {"rows_in_file": int(len(df)), "used": int(ok.sum())}


def build_artifact(mode, X, y, tr, te, logs=None, experiment=False):
    """한 모드의 모델을 학습해 (artifact, metrics) 를 돌려줍니다.
    experiment=False: 이전과 같은 동작(80% 점수 + 전체 재학습). experiment=True: tr(+logs)로만 학습하고 te 로 점수."""
    spec = MODES[mode]
    num, cat = spec["numeric"], spec["categorical"]
    feats = num + spec["derived"] + cat
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    Xe = X[feats].copy()
    Xe[cat] = enc.fit_transform(Xe[cat])           # 범주 목록은 데이터 전체 기준(정답은 쓰지 않음) -> API가 허용하는 값이 모델 버전과 무관
    mask = [c in cat for c in feats]
    ft2 = X["area_pyeong"].values * FT2_PER_PYEONG

    n_logs = 0
    if experiment and logs is not None and len(logs[0]):
        Xl, yl = logs
        Xle = Xl[feats].copy()
        Xle[cat] = enc.transform(Xle[cat])
        ft2_l = Xl["area_pyeong"].values * FT2_PER_PYEONG
        Xtr = pd.concat([Xe.iloc[tr], Xle], ignore_index=True)
        ytr = pd.concat([y.iloc[tr], yl], ignore_index=True)
        ft2_tr = np.concatenate([ft2[tr], ft2_l])
        n_logs = int(len(Xl))
        models = fit(Xtr, ytr, ft2_tr, mask, np.arange(len(Xtr)))
        y_for_base = ytr
    else:
        models = fit(Xe, y, ft2, mask, tr)
        y_for_base = y.iloc[tr]
    pred = predict(models, Xe.iloc[te], ft2[te])

    pyeong, btype = X["area_pyeong"].values[te], X["building_type"].values[te]
    metrics = {"n_train": int(len(tr)) + n_logs, "n_test": int(len(te)), "inputs": len(num) + len(cat), "overall": {}, "by_size": [], "by_building_type": {}}
    for t in TARGETS:
        base = float(y_for_base[t].values.mean())   # 단순 기준: 학습 평균값만 답하기
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

    if not experiment:
        models = fit(Xe, y, ft2, mask, np.arange(len(Xe)))      # 배포용: 전체 데이터로 다시 학습
    ranges = {c: [float(X[c].min()), float(X[c].max())] for c in num}
    tag = "full" if not experiment else ("v2" if n_logs else "v1")
    artifact = dict(mode=mode, features=feats, inputs=num + cat, numeric=num, categorical=cat, derived=spec["derived"],
                    encoder=enc, categories={c: [str(v) for v in cats_] for c, cats_ in zip(cat, enc.categories_)},
                    models=models, ranges=ranges, metrics=metrics, sklearn_version=sklearn.__version__,
                    version_tag=tag, train_rows=metrics["n_train"], log_rows=n_logs,
                    note="학습은 면적당 부하(MBtu/ft²) 기준, 예측은 면적을 곱해 연간 MBtu로 반환")
    return artifact, metrics


def run_mode(mode, X, y, experiment=False, logs_path=None):
    if not experiment:
        tr, te = train_test_split(np.arange(len(X)), test_size=0.2, random_state=42)
        return build_artifact(mode, X, y, tr, te)
    sp = experiment_split(X)
    logs = None
    if logs_path:
        Xl, yl, info = load_log_rows(logs_path, mode)
        if Xl is not None and len(Xl):
            logs = (Xl, yl)
        print(f"  [{mode}] 로그 파일 {info['rows_in_file']}행 중 학습에 쓴 행: {info['used']}")
    return build_artifact(mode, X, y, sp["train"], sp["holdout"], logs=logs, experiment=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", action="store_true", help="재학습 실험 모드(train 만 학습, holdout 으로 점수)")
    ap.add_argument("--logs", default=None, help="정답 있는 로그 CSV (기본: data/retrain_logs.csv.gz 가 있으면 사용). --experiment 에서만 의미가 있음")
    args = ap.parse_args()

    data = find_data()
    print("데이터:", data)
    X, y = build_table(pd.read_csv(data, low_memory=False))
    print(f"학습표: {X.shape[0]}행 (6000 ft² 초과 제외), 면적 {X['area_pyeong'].min():.1f}~{X['area_pyeong'].max():.1f}평\n")
    logs_path = None
    if args.experiment:
        logs_path = Path(args.logs) if args.logs else (DEFAULT_LOGS if DEFAULT_LOGS.exists() else None)
        sp = experiment_split(X)
        print(f"실험 모드: train {len(sp['train'])} / pool {len(sp['pool'])} / holdout {len(sp['holdout'])}  | 로그 파일: {logs_path or '없음 (재학습 전 모델 v1)'}\n")
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    all_metrics = {}
    for mode in ["detail", "simple"]:
        artifact, m = run_mode(mode, X, y, args.experiment, logs_path)
        joblib.dump(artifact, ROOT / "models" / f"resstock_{mode}.joblib", compress=3)
        all_metrics[mode] = m
        print(f"===== {mode} 모드 (입력 {m['inputs']}개, 학습 {m['n_train']} / 검증 {m['n_test']}) 모델 태그: {artifact['version_tag']} =====")
        for k in ["heating", "cooling"]:
            o = m["overall"][k]
            print(f"  {k:<8} R²={o['r2']:.3f}  MAE={o['mae']:.2f} MBtu (단순기준 {o['baseline_mae']:.2f})  정확도={o['accuracy']:.1f}%")
        print("  평 구간별 R² (난방 / 냉방):")
        for r in m["by_size"]:
            print(f"    {r['size']:<8} n={r['n']:<5} {r['heating']['r2']:.3f} / {r['cooling']['r2']:.3f}")
        print()
    all_metrics["sklearn_version"] = sklearn.__version__
    all_metrics["version_tag"] = artifact["version_tag"]
    all_metrics["experiment"] = bool(args.experiment)
    (ROOT / "docs" / "resstock_metrics.json").write_text(json.dumps(all_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print("저장 완료: models/resstock_{detail,simple}.joblib, docs/resstock_metrics.json")


if __name__ == "__main__":
    main()
