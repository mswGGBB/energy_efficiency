"""재학습 실험용 공통 도구: 데이터 불러오기, 건물 한 채를 API 입력으로 바꾸기, API 호출.

send_test_requests.py(팀원 테스트 로그 쌓기), eval_service.py(배포된 서비스 점수 재기), retrain_report.py 가 같이 씁니다.
표준 라이브러리 + pandas 만 필요합니다.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resstock_prep import MODES, TARGETS, build_table, experiment_split  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_xy():
    for p in [ROOT / "data" / "resstock_sample_v2.csv.gz", ROOT / "data" / "resstock_sample_v2.csv"]:
        if p.exists():
            X, y = build_table(pd.read_csv(p, low_memory=False))
            return X, y, experiment_split(X)
    sys.exit("data/resstock_sample_v2.csv.gz 를 찾지 못했습니다. 저장소 루트에서 실행하세요.")


def row_inputs(X, i, mode="detail"):
    """X 의 i 번째 건물 -> API 가 받는 JSON 입력(mode 포함)."""
    spec = MODES[mode]
    out = {"mode": mode}
    for c in spec["numeric"]:
        out[c] = float(X[c].iloc[i])
    for c in spec["categorical"]:
        out[c] = str(X[c].iloc[i])
    return out


def post(url, payload, timeout=30, retries=2):
    """JSON POST. (HTTP 상태, 응답 dict) 를 돌려줍니다. 연결 오류는 몇 번 다시 시도합니다."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    last = None
    for k in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, {"error": str(e)}
        except Exception as e:                      # 연결 실패·시간 초과
            last = e
            time.sleep(1 + k)
    return 0, {"error": f"{type(last).__name__}: {last}"}


def actuals(y, i):
    return float(y[TARGETS[0]].iloc[i]), float(y[TARGETS[1]].iloc[i])
