"""AWS Lambda 핸들러 — ResStock 냉난방 부하 예측 API

요청 (POST, JSON)
  - 간편 모드: area_pyeong, stories, state, climate_zone, building_type, vintage, cooling_type, heating_type, heating_fuel
  - 상세 모드: 위 9개 + 18개 (docs/resstock_features.md 참고)
  - "mode": "simple" | "detail" 로 지정 가능. 없으면 상세 전용 입력이 하나라도 있으면 detail, 아니면 simple
  - GET 으로 열면 사용법(필수 입력 목록)을 돌려줌

응답: 200 예측 / 400 잘못된 입력 / 500 서버(모델) 문제. 모델을 못 불러와도 함수가 죽지 않고 500 JSON 으로 답함.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 저장소 안(../scripts)과 Docker 이미지 안(./scripts) 양쪽에서 동작
for _cand in (HERE / "scripts", HERE.parent / "scripts"):
    if _cand.exists():
        sys.path.insert(0, str(_cand))
        break

ARTIFACTS = {}
LOAD_ERROR = None
try:
    from resstock_prep import MODES
    from resstock_predict import InputError, load_artifact, predict

    for _mode in ("simple", "detail"):
        ARTIFACTS[_mode] = load_artifact(_mode)
except Exception as e:  # 모델·라이브러리 문제여도 import 단계에서 죽지 않게
    LOAD_ERROR = f"{type(e).__name__}: {e}"

    class InputError(ValueError):  # noqa: N818  (import 실패 시 대체)
        pass


def _inputs_of(mode):
    return MODES[mode]["numeric"] + MODES[mode]["categorical"]


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _method(event):
    return (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod") or "POST").upper()


def lambda_handler(event, context):
    # 모델 준비 실패: 함수는 살아 있고 500 JSON 으로 알림
    if LOAD_ERROR is not None or not ARTIFACTS:
        return _response(500, {"error": "모델을 불러올 수 없습니다. 서버 설정을 확인해주세요.", "detail": LOAD_ERROR})

    try:
        if _method(event) == "GET":
            return _response(200, {
                "service": "ResStock 연간 난방·냉방 부하 예측",
                "usage": "POST JSON. mode 는 simple 또는 detail",
                "required_inputs": {m: _inputs_of(m) for m in ("simple", "detail")},
                "allowed_values": {c: ARTIFACTS["detail"]["categories"][c] for c in ARTIFACTS["detail"]["categorical"]},
                "numeric_ranges": ARTIFACTS["detail"]["ranges"],
                "docs": "docs/resstock_features.md",
            })

        body = event.get("body", event) if isinstance(event, dict) else event
        if isinstance(body, str):
            try:
                body = json.loads(body) if body.strip() else {}
            except json.JSONDecodeError:
                return _response(400, {"error": "요청 본문이 올바른 JSON이 아닙니다."})
        if not isinstance(body, dict) or not body:
            return _response(400, {"error": "입력값이 없습니다.", "required_inputs": {m: _inputs_of(m) for m in ("simple", "detail")}})

        mode = body.get("mode")
        if mode is None:
            detail_only = set(_inputs_of("detail")) - set(_inputs_of("simple"))
            mode = "detail" if detail_only & set(body) else "simple"
        if mode not in ARTIFACTS:
            return _response(400, {"error": f"mode는 'simple' 또는 'detail'이어야 합니다: {mode!r}"})

        try:
            result = predict(ARTIFACTS[mode], body)
        except InputError as e:
            return _response(400, {"error": str(e), "mode": mode, "required_inputs": _inputs_of(mode)})

        m = ARTIFACTS[mode]["metrics"]["overall"]
        result["validation_r2"] = {"heating": round(m["heating"]["r2"], 3), "cooling": round(m["cooling"]["r2"], 3)}
        if mode == "simple":
            result["note"] = "간편 모드는 입력이 적어 참고용입니다(검증 R² 약 0.73). 정확한 값은 detail 모드를 사용하세요."
        return _response(200, result)

    except Exception as e:  # 예상 못 한 오류
        return _response(500, {"error": f"{type(e).__name__}: {e}"})
