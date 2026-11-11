"""재학습 전/후 비교와 로그 데이터 분석 보고서를 만듭니다 (PR 본문에 붙일 표).

사용 (저장소 루트에서):
    python scripts/retrain_report.py --logs data/retrain_logs.csv.gz

하는 일
 1) 로그 분석: 몇 건인지, 어떤 건물인지, 재학습 전 모델(v1)이 서비스에서 낸 예측의 오차
 2) 무결성 검사: 로그 건물이 holdout(평가 전용)에 섞이지 않았는지, 같은 건물이 중복되지 않았는지
 3) v1(train 60%)과 v2(train 60% + 로그)를 같은 holdout 15%로 비교 + 부트스트랩 신뢰구간
 4) 로그 양에 따른 변화(0% / 25% / 50% / 100%) 와, 참고용 '정답을 전부 안다면'(pool 전체) 상한
결과: docs/retrain_report.md, docs/retrain_report.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resstock_prep import FT2_PER_PYEONG, MODES, TARGETS  # noqa: E402
from resstock_train import NAMES, build_artifact, load_log_rows  # noqa: E402
from retrain_common import ROOT, load_xy  # noqa: E402


def holdout_predictions(art, X, te):
    """저장된 artifact 로 holdout 행을 예측(면적당 부하 x 면적)."""
    Xe = X.iloc[te][art["features"]].copy()
    Xe[art["categorical"]] = art["encoder"].transform(Xe[art["categorical"]])
    ft2 = X["area_pyeong"].values[te] * FT2_PER_PYEONG
    return {t: np.clip(art["models"][t].predict(Xe), 0, None) * ft2 for t in TARGETS}


def r2(a, p):
    return float(1 - ((a - p) ** 2).sum() / ((a - a.mean()) ** 2).sum())


def bootstrap_delta(a, p1, p2, n=400, seed=0):
    """같은 holdout 행을 다시 뽑아(부트스트랩) v2 - v1 의 R², MAE 변화에 대한 95% 구간."""
    rng = np.random.RandomState(seed)
    d_r2, d_mae = [], []
    for _ in range(n):
        s = rng.randint(0, len(a), len(a))
        d_r2.append(r2(a[s], p2[s]) - r2(a[s], p1[s]))
        d_mae.append(np.abs(a[s] - p2[s]).mean() - np.abs(a[s] - p1[s]).mean())
    return [float(np.percentile(d_r2, 2.5)), float(np.percentile(d_r2, 97.5))], [float(np.percentile(d_mae, 2.5)), float(np.percentile(d_mae, 97.5))]


def key_frame(df, cols):
    """건물 한 채를 가리는 열쇠(입력값 문자열). 로그 건물이 holdout/pool 에 있는지 대조할 때 씁니다."""
    return df[cols].astype(str).agg("|".join, axis=1) if len(df) else pd.Series([], dtype=str)


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=str(ROOT / "data" / "retrain_logs.csv.gz"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "retrain_report"))
    args = ap.parse_args()

    X, y, sp = load_xy()
    tr, te, pool = sp["train"], sp["holdout"], sp["pool"]
    rep = {"n_total": len(X), "n_train": len(tr), "n_pool": len(pool), "n_holdout": len(te)}
    lines = ["# 재학습 전/후 비교 보고서", "",
             "※ 이 표는 `scripts/retrain_report.py` 가 만든 것입니다. 로그의 정답은 실제 사용자가 아니라 ResStock 데이터의 시뮬레이션 값이며, "
             "요청은 정답을 아는 테스터(팀원 스크립트)가 보냈습니다.", "",
             f"## 0. 데이터 분할 (방식: {sp['scheme']}, seed 고정)", "",
             md_table(["이름", "건물 수", "역할"], [["train", len(tr), "재학습 전 모델(v1)이 학습"], ["pool", len(pool), "서비스에 새로 들어올 건물. 테스트 요청·정답은 여기서만 나옴"],
                                                 ["holdout", len(te), "평가 전용. v1·v2 모두 학습하지 않음"]]), ""]

    # ---- 로그 읽기 ----
    logs_path = Path(args.logs)
    if not logs_path.exists():
        sys.exit(f"로그 파일이 없습니다: {logs_path}  (logs_to_training.py 로 먼저 만드세요)")
    raw = pd.read_csv(logs_path, keep_default_na=False, na_values=[""])
    d = raw.drop_duplicates("request_id") if "request_id" in raw.columns else raw
    Xl, yl, info = {}, {}, {}
    for mode in ("detail", "simple"):
        Xl[mode], yl[mode], info[mode] = load_log_rows(logs_path, mode)

    # ---- 1) 로그 분석 ----
    lines += ["## 1. 재학습에 쓴 로그 데이터 분석", ""]
    n_detail = int((raw.get("mode") == "detail").sum()) if "mode" in raw.columns else 0
    lines += [f"- 로그 파일 {len(raw)}행 → 중복 제거 {len(d)}행 → 학습에 쓸 수 있는 행: 상세 {info['detail']['used']} / 간편 {info['simple']['used']}",
              f"- 요청 모드: {raw['mode'].value_counts().to_dict() if 'mode' in raw.columns else '?'}  / 응답한 모델 태그: {raw['model_tag'].fillna('(없음)').value_counts().to_dict() if 'model_tag' in raw.columns else '?'}", ""]
    for mode in ("detail", "simple"):
        if info[mode]["used"] < len(d):
            lines.append(f"- ⚠️ {mode}: 중복 제거 {len(d)}행 중 {len(d) - info[mode]['used']}행은 입력 누락·형식 오류·음수 정답으로 학습에서 제외됨")
    rep["logs"] = {"rows_file": int(len(raw)), "rows_unique": int(len(d)), "usable_detail": info["detail"]["used"], "usable_simple": info["simple"]["used"]}
    Xd = Xl["detail"]
    if Xd is not None and len(Xd):
        # 서비스(v1)가 낸 예측의 오차
        errs = []
        for k, name in (("heating", "난방"), ("cooling", "냉방")):
            a, p = d[f"actual_{k}"].astype(float).values, d[f"pred_{k}"].astype(float).values
            errs.append([name, f"{np.abs(a - p).mean():.2f}", f"{(p - a).mean():+.2f}", f"{r2(a, p):.3f}" if len(a) > 2 else "-"])
        lines += ["**서비스가 낸 예측 vs 피드백으로 받은 정답** (재학습 전 모델이 이 건물들을 처음 본 결과)", "",
                  md_table(["대상", "MAE (MBtu)", "평균 편향 (예측-실제)", "R²"], errs), ""]
        lines += [f"- 분할 방식: {sp['scheme']} / 따로 보는 구간: {sp['focus_label']}", f"- 로그 중 30평 미만 소형 주택 비율: {(Xd['area_pyeong'] < 30).mean() * 100:.1f}% (train {(X['area_pyeong'].iloc[tr] < 30).mean() * 100:.1f}%), 한랭 기후 비율: {Xd['climate_zone'].isin(['6A', '6B', '7A', '7B']).mean() * 100:.1f}% (train {X['climate_zone'].iloc[tr].isin(['6A', '6B', '7A', '7B']).mean() * 100:.1f}%)", ""]
        lines += ["**로그 건물 vs 학습(train) 건물 구성 비교** (로그가 학습 데이터와 다르게 생겼을수록 새 정보가 많음)", ""]
        cmp_rows = []
        for b in X["building_type"].value_counts().index:
            cmp_rows.append([b, f"{(X['building_type'].iloc[tr] == b).mean() * 100:.1f}%", f"{(Xd['building_type'] == b).mean() * 100:.1f}%"])
        cmp_rows.append(["평균 면적(평)", f"{X['area_pyeong'].iloc[tr].mean():.1f}", f"{Xd['area_pyeong'].mean():.1f}"])
        cmp_rows.append(["평균 난방 부하(MBtu)", f"{y[TARGETS[0]].iloc[tr].mean():.1f}", f"{yl['detail'][TARGETS[0]].mean():.1f}"])
        cmp_rows.append(["평균 냉방 부하(MBtu)", f"{y[TARGETS[1]].iloc[tr].mean():.1f}", f"{yl['detail'][TARGETS[1]].mean():.1f}"])
        lines += [md_table(["항목", "train", "로그"], cmp_rows), ""]

    # ---- 2) 무결성 검사 ----
    dcols = MODES["detail"]["numeric"] + MODES["detail"]["categorical"]
    fmt = X[dcols].copy()
    for c in MODES["detail"]["numeric"]:
        fmt[c] = fmt[c].astype(float).round(4)
    keys_all = key_frame(fmt, dcols)
    leak = dup = in_pool = in_train = 0
    if Xd is not None and len(Xd):
        lf = Xd[dcols].copy()
        for c in MODES["detail"]["numeric"]:
            lf[c] = lf[c].astype(float).round(4)
        lk = key_frame(lf, dcols)
        leak = int(lk.isin(set(keys_all.iloc[te])).sum())
        in_train = int(lk.isin(set(keys_all.iloc[tr])).sum())
        in_pool = int(lk.isin(set(keys_all.iloc[pool])).sum())
        dup = int(lk.duplicated().sum())
    lines += ["## 2. 무결성 검사", "",
              md_table(["검사", "결과", "기대값"], [["로그 건물이 holdout(평가용)과 같은 경우", leak, "0 (0이 아니면 평가가 오염됨)"],
                                           ["로그 건물이 train 과 같은 경우", in_train, "0에 가까움 (비슷한 건물이 우연히 같을 수는 있음)"],
                                           ["로그 건물이 pool 에 있는 경우", f"{in_pool} / {len(Xd) if Xd is not None else 0}", "대부분"],
                                           ["로그 안에서 같은 건물이 중복된 경우", dup, "0 (중복이면 같은 건물을 두 번 학습)"]]), ""]
    rep["integrity"] = {"holdout_overlap": leak, "train_overlap": in_train, "in_pool": in_pool, "duplicates": dup}

    # ---- 3) v1 vs v2 ----
    lines += ["## 3. 재학습 전(v1) vs 후(v2) — 같은 평가용(holdout) 건물로 비교", ""]
    rows3, rows_small, rep["compare"] = [], [], {}
    small = np.isin(te, sp["focus_holdout"])           # 보고서에서 따로 보는 구간 (SPLIT_SCHEME 의 focus)
    curve_rows = []
    for mode in ("detail", "simple"):
        logs = (Xl[mode], yl[mode]) if Xl[mode] is not None and len(Xl[mode]) else None
        a1, m1 = build_artifact(mode, X, y, tr, te, logs=None, experiment=True)
        if logs is None:
            lines.append(f"- {mode}: 쓸 수 있는 로그가 없어 v2 를 만들지 못했습니다.")
            continue
        a2, m2 = build_artifact(mode, X, y, tr, te, logs=logs, experiment=True)
        p1, p2 = holdout_predictions(a1, X, te), holdout_predictions(a2, X, te)
        rep["compare"][mode] = {"n_log_rows": a2["log_rows"], "v1": m1["overall"], "v2": m2["overall"]}
        for t in TARGETS:
            k, a = NAMES[t], y[t].values[te]
            ci_r2, ci_mae = bootstrap_delta(a, p1[t], p2[t])
            o1, o2 = m1["overall"][k], m2["overall"][k]
            rows3.append([mode, "난방" if k == "heating" else "냉방", f"{m1['n_train']} → {m2['n_train']}", f"{o1['r2']:.4f}", f"{o2['r2']:.4f}",
                          f"{o2['r2'] - o1['r2']:+.4f} ({ci_r2[0]:+.4f} ~ {ci_r2[1]:+.4f})", f"{o1['mae']:.3f}", f"{o2['mae']:.3f}",
                          f"{o2['mae'] - o1['mae']:+.3f} ({ci_mae[0]:+.3f} ~ {ci_mae[1]:+.3f})", f"{o1['accuracy']:.2f}", f"{o2['accuracy']:.2f}"])
            rep["compare"][mode][f"delta_{k}"] = {"r2": o2["r2"] - o1["r2"], "r2_ci95": ci_r2, "mae": o2["mae"] - o1["mae"], "mae_ci95": ci_mae}
            sa = a[small]
            ci_r2s, ci_maes = bootstrap_delta(sa, p1[t][small], p2[t][small])
            r1s, r2s = r2(sa, p1[t][small]), r2(sa, p2[t][small])
            m1s, m2s = np.abs(sa - p1[t][small]).mean(), np.abs(sa - p2[t][small]).mean()
            rows_small.append([mode, "난방" if k == "heating" else "냉방", int(small.sum()), f"{r1s:.4f}", f"{r2s:.4f}", f"{r2s - r1s:+.4f} ({ci_r2s[0]:+.4f} ~ {ci_r2s[1]:+.4f})",
                               f"{m1s:.3f}", f"{m2s:.3f}", f"{m2s - m1s:+.3f} ({ci_maes[0]:+.3f} ~ {ci_maes[1]:+.3f})"])
            rep["compare"][mode][f"small_{k}"] = {"n": int(small.sum()), "r2_v1": r1s, "r2_v2": r2s, "r2_ci95": ci_r2s, "mae_v1": float(m1s), "mae_v2": float(m2s), "mae_ci95": ci_maes}
        # 로그 양 변화
        rng = np.random.RandomState(1)
        for frac in (0.25, 0.5):
            sub = rng.permutation(len(logs[0]))[:int(len(logs[0]) * frac)]
            _, m = build_artifact(mode, X, y, tr, te, logs=(logs[0].iloc[sub].reset_index(drop=True), logs[1].iloc[sub].reset_index(drop=True)), experiment=True)
            curve_rows.append([mode, f"로그 {frac * 100:.0f}% ({len(sub)}건)", f"{m['overall']['heating']['r2']:.4f}", f"{m['overall']['cooling']['r2']:.4f}",
                               f"{m['overall']['heating']['mae']:.3f}", f"{m['overall']['cooling']['mae']:.3f}"])
        curve_rows.insert(len(curve_rows) - 2, [mode, "로그 0건 (v1)", f"{m1['overall']['heating']['r2']:.4f}", f"{m1['overall']['cooling']['r2']:.4f}",
                                                f"{m1['overall']['heating']['mae']:.3f}", f"{m1['overall']['cooling']['mae']:.3f}"])
        curve_rows.append([mode, f"로그 100% ({len(logs[0])}건 = v2)", f"{m2['overall']['heating']['r2']:.4f}", f"{m2['overall']['cooling']['r2']:.4f}",
                           f"{m2['overall']['heating']['mae']:.3f}", f"{m2['overall']['cooling']['mae']:.3f}"])
        _, mp = build_artifact(mode, X, y, tr, te, logs=(X.iloc[pool].reset_index(drop=True), y.iloc[pool].reset_index(drop=True)), experiment=True)
        curve_rows.append([mode, f"(가정) pool 전체 {len(pool)}건의 정답을 안다면", f"{mp['overall']['heating']['r2']:.4f}", f"{mp['overall']['cooling']['r2']:.4f}",
                           f"{mp['overall']['heating']['mae']:.3f}", f"{mp['overall']['cooling']['mae']:.3f}"])
    if rows3:
        lines += [md_table(["모드", "대상", "학습 건수", "R² v1", "R² v2", "R² 변화 (95% 구간)", "MAE v1", "MAE v2", "MAE 변화 (95% 구간)", "정확도% v1", "정확도% v2"], rows3), "",
                  "- 95% 구간은 같은 평가용 건물을 다시 뽑아(부트스트랩) 계산한 변화량의 범위입니다. **구간이 0을 포함하면 개선이라고 단정할 수 없습니다.**",
                  "- R²·MAE·정확도의 정의는 `scripts/resstock_train.py` 머리말과 같습니다. MAE는 낮을수록 좋습니다.", ""]
    if rows_small:
        lines += [f"### 따로 보는 구간: {sp['focus_label']} (holdout 중 해당 건물)", "",
                  md_table(["모드", "대상", "건물 수", "R² v1", "R² v2", "R² 변화 (95% 구간)", "MAE v1", "MAE v2", "MAE 변화 (95% 구간)"], rows_small), ""]
    if curve_rows:
        lines += ["## 4. 로그 양에 따른 변화 (평가용 holdout 기준)", "",
                  md_table(["모드", "학습에 더한 로그", "R² 난방", "R² 냉방", "MAE 난방", "MAE 냉방"], curve_rows), "",
                  "- 로그가 늘수록 점수가 어떻게 변하는지 보여 주는 표입니다. 마지막 줄 '(가정)'은 실제 로그가 아니라 정답을 전부 안다고 가정한 참고용 상한입니다.", ""]

    Path(args.out + ".md").write_text("\n".join(lines), encoding="utf-8")
    Path(args.out + ".json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n저장: {args.out}.md / .json")


if __name__ == "__main__":
    main()
