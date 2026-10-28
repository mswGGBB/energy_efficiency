"""AWS Lambda 핸들러 — ResStock 냉난방 부하 예측 API

요청 (POST, JSON)
  - 간편 모드: area_pyeong, stories, state, climate_zone, building_type, vintage, cooling_type, heating_type, heating_fuel
  - 상세 모드: 위 9개 + 18개 (docs/resstock_features.md 참고)
  - "mode": "simple" | "detail" 로 지정 가능. 없으면 상세 전용 입력이 하나라도 있으면 detail, 아니면 simple
  - GET 으로 열면 사용법(필수 입력 목록)을 돌려줌

로그: 요청마다 JSON 한 줄을 남깁니다(CloudWatch Logs). 재학습·강화학습에 쓸 입력/예측/피드백 기록이며 docs/logging.md 참고.

응답: 200 예측 / 400 잘못된 입력 / 500 서버(모델) 문제. 모델을 못 불러와도 함수가 죽지 않고 500 JSON 으로 답함.
"""
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 저장소 안(../scripts)과 Docker 이미지 안(./scripts) 양쪽에서 동작
for _cand in (HERE / "scripts", HERE.parent / "scripts"):
    if _cand.exists():
        sys.path.insert(0, str(_cand))
        break

LOG = logging.getLogger("energy")
LOG.setLevel(logging.INFO)
if not LOG.handlers:                      # Lambda 는 root 핸들러가 이미 있어 INFO 가 안 보일 수 있으므로 직접 출력
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(_h)
    LOG.propagate = False

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


def _handle(event, info):
    """요청 처리. 로그에 쓸 정보를 info(dict)에 채워 둔다."""
    # 모델 준비 실패: 함수는 살아 있고 500 JSON 으로 알림
    if LOAD_ERROR is not None or not ARTIFACTS:
        info["error"] = "model_load_failed"
        return _response(500, {"error": "모델을 불러올 수 없습니다. 서버 설정을 확인해주세요.", "detail": LOAD_ERROR})

    try:
        if _method(event) == "GET":
            info["event"] = "usage"
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
                info["error"] = "invalid_json"
                return _response(400, {"error": "요청 본문이 올바른 JSON이 아닙니다."})
        if not isinstance(body, dict) or not body:
            info["error"] = "empty_input"
            return _response(400, {"error": "입력값이 없습니다.", "required_inputs": {m: _inputs_of(m) for m in ("simple", "detail")}})

        # 정답 피드백: 예측 뒤에 실제값을 알게 되면 request_id 와 함께 보내 로그로 남김 (재학습용 라벨)
        if "feedback" in body:
            fb = body["feedback"]
            try:
                clean = {"request_id": str(fb["request_id"])}
                for k in ("actual_heating_mbtu", "actual_cooling_mbtu"):
                    if k in fb:
                        v = float(fb[k])
                        if v < 0:
                            raise ValueError(k)
                        clean[k] = v
                if len(clean) == 1:
                    raise ValueError("actual_*")
            except (KeyError, TypeError, ValueError) as e:
                info["error"] = "invalid_feedback"
                return _response(400, {"error": f"feedback 형식 오류: request_id 와 actual_heating_mbtu/actual_cooling_mbtu(0 이상 숫자)가 필요합니다. ({e})"})
            info["event"] = "feedback"
            info["feedback"] = clean
            return _response(200, {"status": "logged", "request_id": clean["request_id"]})

        mode = body.get("mode")
        if mode is None:
            detail_only = set(_inputs_of("detail")) - set(_inputs_of("simple"))
            mode = "detail" if detail_only & set(body) else "simple"
        info["mode"] = mode
        if mode not in ARTIFACTS:
            info["error"] = "invalid_mode"
            return _response(400, {"error": f"mode는 'simple' 또는 'detail'이어야 합니다: {mode!r}"})

        try:
            result = predict(ARTIFACTS[mode], body)
        except InputError as e:
            info["error"] = "invalid_input"
            info["error_message"] = str(e)[:300]
            info["input_keys"] = sorted(body)[:40]
            return _response(400, {"error": str(e), "mode": mode, "required_inputs": _inputs_of(mode)})

        m = ARTIFACTS[mode]["metrics"]["overall"]
        result["validation_r2"] = {"heating": round(m["heating"]["r2"], 3), "cooling": round(m["cooling"]["r2"], 3)}
        if mode == "simple":
            result["note"] = "간편 모드는 입력이 적어 참고용입니다(검증 R² 약 0.73). 정확한 값은 detail 모드를 사용하세요."
        info["event"] = "predict"
        info["inputs"] = {c: body[c] for c in ARTIFACTS[mode]["inputs"]}
        info["prediction"] = {"heating_mbtu": result["heating_mbtu_per_year"], "cooling_mbtu": result["cooling_mbtu_per_year"]}
        info["validation_r2"] = result["validation_r2"]
        info["warnings"] = result.get("warnings", [])
        info["model_version"] = ARTIFACTS[mode].get("sklearn_version", "unknown")
        return _response(200, result)

    except Exception as e:  # 예상 못 한 오류
        info["error"] = "unexpected"
        info["error_message"] = f"{type(e).__name__}: {e}"[:300]
        return _response(500, {"error": f"{type(e).__name__}: {e}"})


def lambda_handler(event, context):
    t0 = time.time()
    request_id = getattr(context, "aws_request_id", None) or uuid.uuid4().hex   # 예측과 나중의 피드백을 잇는 키
    info = {}
    resp = _handle(event, info)

    kind = info.get("event") or ("predict_error" if "error" in info else "request")
    if kind == "predict":                      # 응답에도 request_id 를 넣어 피드백 때 쓰게 함
        body = json.loads(resp["body"])
        body["request_id"] = request_id
        resp["body"] = json.dumps(body, ensure_ascii=False)
    if kind != "usage":                        # 사용법 조회(GET)는 학습에 필요 없어 기록하지 않음
        record = {"event": kind, "request_id": request_id, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "status": resp["statusCode"], "latency_ms": round((time.time() - t0) * 1000, 1)}
        record.update({k: v for k, v in info.items() if k != "event"})
        try:
            LOG.info(json.dumps(record, ensure_ascii=False, default=str))
        except Exception:                      # 로그 실패가 응답을 막으면 안 됨
            pass
    return resp
