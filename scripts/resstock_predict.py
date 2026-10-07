"""저장된 모델(models/resstock_*.joblib)로 연간 난방·냉방 부하를 예측합니다.

실행 예 (저장소 루트에서):
    python scripts/resstock_predict.py

API(lambda_function.py)에서도 load_artifact / predict 를 그대로 가져다 쓰면 됩니다.
"""
import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resstock_prep import FT2_PER_PYEONG, MBTU_TO_KWH, TARGETS, add_derived  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_artifact(mode, models_dir=None):
    return joblib.load(Path(models_dir or ROOT / "models") / f"resstock_{mode}.joblib")


class InputError(ValueError):
    """사용자가 잘못된 입력을 보냈을 때(400 응답에 해당)."""


def predict(art, inputs):
    # 1) 필수 입력 확인
    missing = [c for c in art["inputs"] if c not in inputs]
    if missing:
        raise InputError(f"누락된 입력값: {missing}")
    # 2) 범주형은 학습에 쓰인 값만 허용
    for c in art["categorical"]:
        if str(inputs[c]) not in art["categories"][c]:
            raise InputError(f"'{c}'에 허용되지 않는 값: {inputs[c]!r}. 가능한 값: {art['categories'][c]}")
    # 3) 숫자 확인. 면적은 학습 범위 밖이면 거절, 나머지는 경고만
    warnings = []
    for c in art["numeric"]:
        try:
            v = float(inputs[c])
        except (TypeError, ValueError):
            raise InputError(f"'{c}'는 숫자여야 합니다: {inputs[c]!r}")
        lo, hi = art["ranges"][c]
        if c == "area_pyeong" and not lo <= v <= hi:
            raise InputError(f"area_pyeong은 학습 범위({lo:.1f}~{hi:.1f}평) 안이어야 합니다: {v}")
        if v < lo or v > hi:
            warnings.append(f"{c}={v}은(는) 학습 범위({lo:g}~{hi:g}) 밖이라 오차가 클 수 있습니다.")

    row = pd.DataFrame([{c: inputs[c] for c in art["inputs"]}])
    for c in art["numeric"]:
        row[c] = row[c].astype(float)
    if art["derived"]:
        row = add_derived(row)
    X = row[art["features"]].copy()
    X[art["categorical"]] = art["encoder"].transform(X[art["categorical"]].astype(str))

    ft2 = float(row["area_pyeong"].iloc[0]) * FT2_PER_PYEONG
    out = {}
    for t, name in zip(TARGETS, ["heating", "cooling"]):
        mbtu = max(float(art["models"][t].predict(X)[0]), 0.0) * ft2   # 면적당 부하 x 면적
        out[f"{name}_mbtu_per_year"] = round(mbtu, 2)
        out[f"{name}_kwh_per_year"] = round(mbtu * MBTU_TO_KWH)
    out["mode"] = art["mode"]
    if warnings:
        out["warnings"] = warnings
    return out


if __name__ == "__main__":
    detail = load_artifact("detail")
    simple = load_artifact("simple")
    # 예시 1: 20평대 단독주택 (미국 텍사스, 에어컨·가스난방)
    base = dict(area_pyeong=24, stories=1, state="TX", climate_zone="2A", building_type="Single-Family Detached",
                vintage="1990s", cooling_type="Central AC", heating_type="Ducted Heating", heating_fuel="Natural Gas")
    print("간편 모드 (24평):", predict(simple, base))
    full = dict(base, bedrooms=3, occupants=3, heating_setpoint_f=70, cooling_setpoint_f=75, infiltration_ach50=15,
                wall_r=11, ceiling_r=30, roof_r=0, floor_r=0, wall_area_ft2=1100, window_area_ft2=120, roof_area_ft2=860,
                door_area_ft2=20, windows="Double, Clear, Non-metal, Air", wall_type="Wood Stud",
                foundation="Slab", attic="Vented Attic", garage="None")
    print("상세 모드 (24평):", predict(detail, full))
    # 예시 2: 에어컨 없는 같은 집 -> 냉방 부하가 크게 줄어야 정상
    print("상세 모드, 에어컨 없음:", predict(detail, dict(full, cooling_type="None")))
    # 예시 3: 잘못된 입력
    for bad in [dict(full, area_pyeong=3), dict(full, state="ZZ"), {"area_pyeong": 24}]:
        try:
            predict(detail, bad)
        except InputError as e:
            print("오류 응답:", str(e)[:90])
