import pandas as pd

PATH = "results_up00_update.csv"   # 내려받은 파일 이름
FRAC = 0.08                             # 행의 8%만 무작위로 (약 4만 행)

P = "build_existing_model."
R = "report_simulation_output."
U = "upgrade_costs."

cols = [
    "building_id", "completed_status",
    # 맞힐 값(타깃): 연간 난방/냉방 부하 (MBtu)
    R + "load_heating_delivered_m_btu", R + "load_cooling_delivered_m_btu",
    # 면적·형태 (ft², 입력으로 쓸 값)
    U + "floor_area_conditioned_ft_2", U + "wall_area_above_grade_exterior_ft_2",
    U + "window_area_ft_2", U + "roof_area_ft_2",
    P + "geometry_floor_area", P + "geometry_building_type_recs", P + "geometry_stories",
    P + "geometry_foundation_type", P + "geometry_attic_type",
    # 단열·창·기밀
    P + "vintage", P + "insulation_wall", P + "insulation_ceiling", P + "insulation_roof",
    P + "insulation_floor", P + "windows", P + "infiltration", P + "orientation",
    # 기후·위치
    P + "ashrae_iecc_climate_zone_2004", P + "state",
    P + "weather_file_latitude", P + "weather_file_longitude",
    # 사용 조건
    P + "heating_setpoint", P + "cooling_setpoint", P + "occupants", P + "bedrooms",
    P + "sample_weight",
    # ---- v2 추가: 설비 유무·구성 (부하가 0이 되는 원인 확인용) ----
    P + "hvac_cooling_type", P + "hvac_heating_type", P + "heating_fuel",
    P + "hvac_cooling_partial_space_conditioning", P + "hvac_has_ducts", P + "ducts",
    # 설정온도 야간/부재 조정(offset)
    P + "heating_setpoint_has_offset", P + "heating_setpoint_offset_magnitude",
    P + "cooling_setpoint_has_offset", P + "cooling_setpoint_offset_magnitude",
    # 내부 발열·사용량
    P + "usage_level", P + "plug_loads", P + "lighting", P + "ceiling_fan",
    # 외피·환기 상세
    P + "window_areas", P + "neighbors", P + "overhangs", P + "interior_shading", P + "eaves",
    P + "doors", P + "insulation_slab", P + "insulation_foundation_wall", P + "insulation_rim_joist",
    P + "geometry_garage", P + "geometry_wall_type", P + "roof_material", P + "radiant_barrier",
    P + "natural_ventilation", P + "mechanical_ventilation",
    U + "door_area_ft_2",
]

parts, total = [], 0
for chunk in pd.read_csv(PATH, usecols=cols, chunksize=50_000, dtype={P + "occupants": str}):   # 나눠서 읽기(메모리 절약)
    total += len(chunk)
    chunk = chunk[chunk["completed_status"] == "Success"]
    parts.append(chunk.sample(frac=FRAC, random_state=42))
    print("읽은 행:", total, flush=True)

df = pd.concat(parts, ignore_index=True)
df.columns = [c.split(".")[-1] for c in df.columns]   # 접두어 제거
df.to_csv("resstock_sample_v2.csv", index=False, encoding="utf-8-sig")

print("\n저장 완료: resstock_sample_v2.csv", df.shape)
ft2 = df["floor_area_conditioned_ft_2"]
print("\n[면적 요약, ft²]"); print(ft2.describe().round(1))
pyeong = ft2 / 35.58
bins = pd.cut(pyeong, [0, 10, 20, 30, 40, 60, 1000], right=False)
print("\n[평 구간별 행 수]"); print(bins.value_counts().sort_index())
print("\n[비어 있는 값 개수]"); print(df.isna().sum()[df.isna().sum() > 0])
print("\n[타깃 요약]"); print(df[["load_heating_delivered_m_btu", "load_cooling_delivered_m_btu"]].describe().round(2))
