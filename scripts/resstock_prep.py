"""ResStock 샘플(resstock_sample_v2.csv) 전처리와 입력 사양.

- 학습(resstock_train.py)과 예측(resstock_predict.py)이 같은 규칙을 쓰도록 한 파일에 모았습니다.
- 단위: 면적은 '평'(1평 = 35.58 ft²), 부하는 연간 MBtu(백만 Btu). 1 MBtu = 293.07 kWh.
"""
import numpy as np
import pandas as pd

FT2_PER_PYEONG = 35.58
MBTU_TO_KWH = 293.071
TARGETS = ["load_heating_delivered_m_btu", "load_cooling_delivered_m_btu"]

# ---- 입력 사양 (사용자가 넣는 값) ----
# 상세 모드: R² 0.85 목표
DETAIL_NUMERIC = ["area_pyeong", "stories", "bedrooms", "occupants", "heating_setpoint_f", "cooling_setpoint_f",
                  "infiltration_ach50", "wall_r", "ceiling_r", "roof_r", "floor_r",
                  "wall_area_ft2", "window_area_ft2", "roof_area_ft2", "door_area_ft2"]
DETAIL_CATEGORICAL = ["state", "climate_zone", "building_type", "vintage", "cooling_type", "heating_type",
                      "heating_fuel", "windows", "wall_type", "foundation", "attic", "garage"]
# 간편 모드: 참고용 (입력 9개)
SIMPLE_NUMERIC = ["area_pyeong", "stories"]
SIMPLE_CATEGORICAL = ["state", "climate_zone", "building_type", "vintage", "cooling_type", "heating_type", "heating_fuel"]
# 입력에서 계산해 만드는 값
DERIVED = ["wall_per_floor", "roof_per_floor", "window_ratio"]

MODES = {
    "detail": dict(numeric=DETAIL_NUMERIC, categorical=DETAIL_CATEGORICAL, derived=DERIVED),
    "simple": dict(numeric=SIMPLE_NUMERIC, categorical=SIMPLE_CATEGORICAL, derived=[]),
}


def _num(s, pattern):
    return pd.to_numeric(s.astype("string").str.extract(pattern)[0], errors="coerce")


def add_derived(X):
    """벽·지붕·창 면적을 바닥면적 대비 비율로 바꾼 값 (입력 면적에서 계산)."""
    ft2 = X["area_pyeong"] * FT2_PER_PYEONG
    X["wall_per_floor"] = X["wall_area_ft2"] / ft2
    X["roof_per_floor"] = X["roof_area_ft2"] / ft2
    X["window_ratio"] = X["window_area_ft2"] / X["wall_area_ft2"]
    return X


def build_table(df, max_ft2=6000):
    """원본 샘플 -> (입력표 X, 타깃 y). 6000 ft²(약 169평) 초과 대저택은 제외."""
    d = df[df["floor_area_conditioned_ft_2"] <= max_ft2].reset_index(drop=True)
    X = pd.DataFrame(index=d.index)
    # 면적·구조 (ft² -> 평)
    X["area_pyeong"] = d["floor_area_conditioned_ft_2"] / FT2_PER_PYEONG
    X["stories"] = d["geometry_stories"]
    X["bedrooms"] = d["bedrooms"]
    # occupants: '2' / '2.0' / '10+' 가 섞여 있어 숫자로 통일
    X["occupants"] = pd.to_numeric(d["occupants"].astype("string").str.replace("+", "", regex=False), errors="coerce")
    # '72F' -> 72, '15 ACH50' -> 15
    X["heating_setpoint_f"] = _num(d["heating_setpoint"], r"(\d+)")
    X["cooling_setpoint_f"] = _num(d["cooling_setpoint"], r"(\d+)")
    X["infiltration_ach50"] = _num(d["infiltration"], r"(\d+)")
    # 단열: 'R-11' -> 11, 'Uninsulated' 또는 해당 구조 없음(빈칸) -> 0
    for col, name in [("insulation_wall", "wall"), ("insulation_ceiling", "ceiling"),
                      ("insulation_roof", "roof"), ("insulation_floor", "floor")]:
        X[f"{name}_r"] = _num(d[col], r"R-(\d+)").fillna(0)
    X["wall_area_ft2"] = d["wall_area_above_grade_exterior_ft_2"]
    X["window_area_ft2"] = d["window_area_ft_2"]
    X["roof_area_ft2"] = d["roof_area_ft_2"]
    X["door_area_ft2"] = d["door_area_ft_2"]
    # 범주형. 빈칸은 '해당 설비/구조 없음'이므로 "None"으로 채움
    X["state"] = d["state"]
    X["climate_zone"] = d["ashrae_iecc_climate_zone_2004"]
    X["building_type"] = d["geometry_building_type_recs"]
    X["vintage"] = d["vintage"]
    X["cooling_type"] = d["hvac_cooling_type"].fillna("None")
    X["heating_type"] = d["hvac_heating_type"].fillna("None")
    X["heating_fuel"] = d["heating_fuel"].fillna("None")
    X["windows"] = d["windows"]
    X["wall_type"] = d["insulation_wall"].str.replace(r",?\s*(R-\d+|Uninsulated)$", "", regex=True)
    X["foundation"] = d["geometry_foundation_type"]
    X["attic"] = d["geometry_attic_type"].fillna("None")
    X["garage"] = d["geometry_garage"].fillna("None")
    X = add_derived(X)
    return X, d[TARGETS].copy()


# ---- 재학습 실험용 데이터 분할 ----
# 같은 데이터 파일이면 누가 돌려도 같은 분할이 나옵니다(seed 고정). 행 번호는 build_table 결과의 행 번호입니다.
#   train   : 재학습 전 모델(v1)이 배우는 건물
#   pool    : 서비스에 '새로 들어올' 건물. v1은 본 적이 없고, 팀원 테스트 요청과 정답(피드백)이 여기서 나옵니다
#   holdout : 평가 전용. v1·v2 어느 쪽도 절대 학습하지 않습니다
#   focus_* : 보고서에서 따로 보는 구간(pool/holdout 중 해당하는 건물)
# SPLIT_SCHEME 은 팀 모두가 같아야 하므로 환경변수가 아니라 이 파일의 상수로 둡니다(바꾸면 로그를 새로 쌓아야 함).
#   "random": 무작위 분할 (train 60 / pool 25 / holdout 15). 구간 = 30평 미만 소형 주택(서비스 주 사용자)
#   "cold"  : 한랭 기후(6A·6B·7A·7B) 건물은 10%만 train, 60% pool, 30% holdout. 나머지 지역은 85% train, 15% holdout.
#             '추운 지역 사용자가 갑자기 늘어난' 상황을 흉내냄. 구간 = 한랭 기후
SPLIT_SCHEME = "random"
COLD_ZONES = ["6A", "6B", "7A", "7B"]
EXPERIMENT_SEED = 42
HOLDOUT_FRAC = 0.15
POOL_FRAC = 0.25
SMALL_PYEONG = 30


def experiment_split(X, scheme=None, seed=EXPERIMENT_SEED):
    scheme = scheme or SPLIT_SCHEME
    n = len(X)
    rng = np.random.RandomState(seed)
    if scheme == "random":
        perm = rng.permutation(n)
        n_h, n_p = int(round(n * HOLDOUT_FRAC)), int(round(n * POOL_FRAC))
        sp = {"holdout": perm[:n_h], "pool": perm[n_h:n_h + n_p], "train": perm[n_h + n_p:]}
        small = (X["area_pyeong"].values < SMALL_PYEONG)
        sp["focus_label"] = f"{SMALL_PYEONG}평 미만 소형 주택"
        in_focus = small
    elif scheme == "cold":
        cold_mask = X["climate_zone"].isin(COLD_ZONES).values
        cold, warm = np.where(cold_mask)[0], np.where(~cold_mask)[0]
        pw, pc = rng.permutation(warm), rng.permutation(cold)
        nh_w, nh_c, np_c = int(round(len(pw) * HOLDOUT_FRAC)), int(round(len(pc) * 0.30)), int(round(len(pc) * 0.60))
        sp = {"holdout": np.concatenate([pw[:nh_w], pc[:nh_c]]), "pool": pc[nh_c:nh_c + np_c],
              "train": np.concatenate([pw[nh_w:], pc[nh_c + np_c:]])}
        sp["focus_label"] = "한랭 기후(6A·6B·7A·7B)"
        in_focus = cold_mask
    else:
        raise ValueError(f"알 수 없는 SPLIT_SCHEME: {scheme}")
    for k in ("holdout", "pool", "train"):
        sp[k] = np.sort(sp[k])
    sp["focus_holdout"] = sp["holdout"][in_focus[sp["holdout"]]]
    sp["focus_pool"] = sp["pool"][in_focus[sp["pool"]]]
    sp["scheme"] = scheme
    return sp
