"""AWS 없이 로컬에서 API(lambda_handler)를 호출해 정상·오류 응답을 확인합니다.

실행 (저장소 루트에서):  python api/test_local.py
먼저 python scripts/resstock_train.py 로 models/ 를 만들어 두어야 합니다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lambda_function import lambda_handler  # noqa: E402

SIMPLE = dict(area_pyeong=24, stories=1, state="TX", climate_zone="2A", building_type="Single-Family Detached",
              vintage="1990s", cooling_type="Central AC", heating_type="Ducted Heating", heating_fuel="Natural Gas")
DETAIL = dict(SIMPLE, bedrooms=3, occupants=3, heating_setpoint_f=70, cooling_setpoint_f=75, infiltration_ach50=15,
              wall_r=11, ceiling_r=30, roof_r=0, floor_r=0, wall_area_ft2=1100, window_area_ft2=120, roof_area_ft2=860,
              door_area_ft2=20, windows="Double, Clear, Non-metal, Air", wall_type="Wood Stud",
              foundation="Slab", attic="Vented Attic", garage="None")

CASES = [
    ("정상: 간편 모드", {"body": json.dumps(SIMPLE)}, 200),
    ("정상: 상세 모드", {"body": json.dumps(DETAIL)}, 200),
    ("정상: 에어컨 없음 (냉방이 크게 줄어야 함)", {"body": json.dumps(dict(DETAIL, cooling_type="None"))}, 200),
    ("오류: 입력 없음", {"body": "{}"}, 400),
    ("오류: JSON 형식이 아님", {"body": "{area_pyeong: 24"}, 400),
    ("오류: 입력 일부 누락", {"body": json.dumps({"area_pyeong": 24})}, 400),
    ("오류: 허용되지 않는 값 (state)", {"body": json.dumps(dict(SIMPLE, state="ZZ"))}, 400),
    ("오류: 평수가 학습 범위 밖 (3평)", {"body": json.dumps(dict(SIMPLE, area_pyeong=3))}, 400),
    ("오류: 평수가 숫자가 아님", {"body": json.dumps(dict(SIMPLE, area_pyeong="스물네평"))}, 400),
    ("오류: mode 값이 잘못됨", {"body": json.dumps(dict(SIMPLE, mode="fast"))}, 400),
    ("사용법 조회 (GET)", {"requestContext": {"http": {"method": "GET"}}}, 200),
]

ok = 0
for name, event, expect in CASES:
    res = lambda_handler(event, None)
    body = json.loads(res["body"])
    passed = res["statusCode"] == expect
    ok += passed
    brief = {k: body[k] for k in ("mode", "heating_mbtu_per_year", "cooling_mbtu_per_year", "error") if k in body}
    if name.startswith("사용법"):
        brief = {"required_inputs": {k: len(v) for k, v in body["required_inputs"].items()}}
    print(f"[{'통과' if passed else '실패'}] {name}: 상태 {res['statusCode']} (기대 {expect}) {json.dumps(brief, ensure_ascii=False)[:150]}")
print(f"\n{ok}/{len(CASES)} 통과")
