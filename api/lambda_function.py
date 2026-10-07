"""
AWS Lambda 핸들러 (v2)
건물 구조 입력 -> 난방/냉방 부하 예측

두 가지 입력 모드 지원:
1. 정밀 모드: 8개 항목(relative_compactness ~ glazing_dist)을 전부 입력
2. 간편 모드: pyeong(평수) 하나만 입력하면 나머지는 기본값(데이터셋 중앙값)으로 자동 채움
"""

import json
import joblib
import pandas as pd

# 모델 로드를 try/except로 감싸서, 실패해도 Lambda 자체가 죽지 않고
# 요청이 들어왔을 때 정상적인 에러 응답(500)을 줄 수 있도록 함
MODEL = None
MODEL_LOAD_ERROR = None
try:
    MODEL = joblib.load("model.pkl")
except Exception as e:
    MODEL_LOAD_ERROR = f"{type(e).__name__}: {e}"

FEATURE_COLUMNS = [
    'relative_compactness', 'surface_area', 'wall_area', 'roof_area',
    'height', 'orientation', 'glazing_area', 'glazing_dist'
]

# 데이터셋 중앙값 기반 기본값 (roof_area 제외 -> 평수로부터 계산되므로)
DEFAULTS = {
    'relative_compactness': 0.75,
    'surface_area': 673.75,
    'wall_area': 318.50,
    'height': 5.25,
    'orientation': 3,
    'glazing_area': 0.25,
    'glazing_dist': 3,
}

PYEONG_TO_M2 = 3.3058


def lambda_handler(event, context):
    # 모델이 애초에 로드되지 않았으면, 요청을 더 처리하지 않고
    # 바로 "모델 준비 실패"임을 알리는 정상적인 JSON 에러로 응답
    if MODEL is None:
        return _response(500, {
            "error": "모델을 불러올 수 없습니다. 서버 설정을 확인해주세요.",
            "detail": MODEL_LOAD_ERROR
        })

    try:
        if "body" in event:
            body = event["body"]
            payload = json.loads(body) if isinstance(body, str) else body
        else:
            payload = event

        # ---- 모드 판별 ----
        if "pyeong" in payload and not all(c in payload for c in FEATURE_COLUMNS):
            # 간편 모드: 평수만 입력
            mode = "simple"
            try:
                pyeong = float(payload["pyeong"])
            except (TypeError, ValueError):
                return _response(400, {"error": "pyeong 값이 올바르지 않습니다."})

            if pyeong <= 0:
                return _response(400, {"error": "pyeong 값은 0보다 커야 합니다."})

            roof_area = round(pyeong * PYEONG_TO_M2, 2)
            input_values = {**DEFAULTS, "roof_area": roof_area}

        else:
            # 정밀 모드: 8개 항목 전부 입력
            mode = "precise"
            missing = [c for c in FEATURE_COLUMNS if c not in payload]
            if missing:
                return _response(400, {
                    "error": f"누락된 입력값: {missing}",
                    "required_fields": FEATURE_COLUMNS,
                    "or_use_simple_mode": {"pyeong": "숫자 (평수)"}
                })
            input_values = {c: payload[c] for c in FEATURE_COLUMNS}

        # ---- 예측 ----
        input_df = pd.DataFrame([[input_values[c] for c in FEATURE_COLUMNS]],
                                 columns=FEATURE_COLUMNS)
        pred = MODEL.predict(input_df)[0]

        result = {
            "mode": mode,
            "heating_load": round(float(pred[0]), 2),
            "cooling_load": round(float(pred[1]), 2),
        }
        if mode == "simple":
            result["note"] = "평수 외 조건은 표준값(중앙값)으로 가정한 참고용 예측입니다."
            result["assumed_roof_area_m2"] = input_values["roof_area"]

        return _response(200, result)

    except Exception as e:
        return _response(500, {"error": str(e)})


def _response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body_dict, ensure_ascii=False)
    }