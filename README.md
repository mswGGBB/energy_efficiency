# 🏠 건물의 냉난방 부담 예상 (8팀)

## 한 줄 정의

NREL ResStock 미국 주택 시뮬레이션 데이터(약 4.4만 건)로 건물의 연간 난방·냉방 에너지를 예측해, 20평대 소형 주택을 새로 짓거나 고쳐 쓸지 고민하는 30대 맞벌이 예비 집주인(민수 씨)이 단열·창·냉난방 설비 조건을 바꿔 가며 냉난방 부담을 미리 비교해 보도록 돕는 서비스입니다.

> **현재 상태 (2026-11-11)**: API·화면을 Docker Compose 컨테이너 2개로 묶어 **AWS EC2에서 운영** 중이며, `main`에 머지하면 **GitHub Actions가 자동 배포**합니다. 서비스 로그 1,600건으로 **재학습(v1 → v2)·재배포**까지 한 바퀴 돌렸고, 전후 비교 결과는 "유의한 개선 없음"입니다([`docs/retrain_report.md`](docs/retrain_report.md), PR #28). 이전 단계에서 AWS Lambda 함수 URL, CloudWatch 로그, S3 내보내기도 확인했습니다.
> **주의**: 학습 데이터는 미국 주택 시뮬레이션이라, 한국 집의 실제 값이 아니라 **참고용 추정치**입니다.

## 📌 프로젝트 소개

"이 정도 평수·조건이면 냉난방에 에너지가 얼마나 들까?"에 답하기 위해 만들었습니다. 머신러닝 모델이 건물 조건과 설비를 학습해, 입력한 조건의 연간 난방·냉방 부하를 알려 줍니다.

## 🎯 사용자와 사용 상황

**대표 사용자(페르소나): 민수 씨, 33세, 맞벌이 부부, 예비 집주인**
- 상황: 20평대 소형 주택을 새로 짓거나 오래된 집을 고쳐 쓸지 고민 중이고, 시공사 견적을 받기 전에 대략적인 냉난방 부담을 알고 싶음
- 하는 일: 평수·층수·지역·냉난방 설비(간편 9개 입력)로 먼저 감을 잡고, 단열·창·기밀 같은 조건(상세 27개 입력)을 바꿔 가며 어느 조건이 에너지를 줄이는지 비교
- 얻는 것: 연간 난방·냉방 에너지(MBtu, kWh) 예측값과 경고(학습 범위 밖 값, 간편 모드는 참고용)

**이 서비스가 주는 값은 참고용입니다.** 한국 주택이 아니라 미국 주택 시뮬레이션으로 학습했고, 실제 설계·견적을 대신하지 않습니다.

## ✨ 주요 기능

| 기능 | 설명 |
|---|---|
| 간편 모드 | 입력 9개(평수, 층수, 주, 기후 구역, 건물 유형, 건축 연대, 냉방·난방 설비, 난방 연료)로 빠르게 예측 |
| 상세 모드 | 간편 입력 + 설정온도, 기밀도, 단열 R값, 창·벽·지붕 면적 등 총 27개를 넣어 더 정확하게 예측 |
| 경고 안내 | 학습 범위를 벗어난 값은 경고를 함께 반환하고, 평수가 학습 범위(7.7~157평) 밖이면 요청을 거절 |
| 오류 응답 | 누락·잘못된 값은 `400`, 모델 문제는 `500` JSON으로 응답 (서버가 죽지 않음) |
| 모델 표시 | 결과 아래에 사용한 모델 버전(`v1`/`v2`), 검증 R², 요청번호를 표시 |
| 피드백 | 예측의 `request_id`로 실제값을 보내면 재학습 데이터로 쌓임 |

## 🔎 입력 / 출력

**입력**: 간편 9개 / 상세 27개 (항목별 설명과 허용값은 [`docs/resstock_features.md`](docs/resstock_features.md))

**출력**
- 연간 난방 부하 `heating_mbtu_per_year`, `heating_kwh_per_year`
- 연간 냉방 부하 `cooling_mbtu_per_year`, `cooling_kwh_per_year`
- 사용한 모드, 경고(`warnings`), 모델 검증 점수(`validation_r2`), 모델 버전(`model_tag`), 요청번호(`request_id`)

1평 = 35.58 ft², 1 MBtu = 293.071 kWh로 환산합니다.

## 📊 데이터셋

- 출처: NREL **ResStock** "Annual Baseline Results with Component Loads" (미국 주택 약 55만 가구 시뮬레이션, CC-BY)
- 이 중 8%를 무작위 추출해 **43,762행**(6,000 ft² 이하, 7.7~157평) 사용
- 맞히는 값(타깃): 연간 난방·냉방 부하(MBtu). 면적당 부하를 학습한 뒤 면적을 곱해 되돌림
- 이전에 시도한 UCI Energy Efficiency(768행)는 지붕 면적 값이 4종류뿐이라 20평대 작은 집 예측이 어려워 교체함
- 결과 컬럼(`report_simulation_output.*`)은 입력에서 제외해 정답 누출을 막음

## ⚠️ 데이터/서비스 한계

- **미국 주택·기후 기준 시뮬레이션**이라 한국 주택의 실제 값과 다를 수 있습니다.
- 간편 모드는 정확도가 낮습니다(R² 약 0.74). 상세 모드를 권장합니다.
- 5세대 이상 공동주택 난방(R² 0.844)과 2~4세대 냉방(R² 0.829)은 0.85에 못 미칩니다.
- 상세 모드의 기밀도(ACH50) 같은 값은 일반 사용자가 알기 어렵습니다.
- 1회 요청 단위 예측이며, 시계열 예측은 지원하지 않습니다.

## 🧠 모델

- 알고리즘: `HistGradientBoostingRegressor` (난방·냉방 각각 1개), 범주형은 `OrdinalEncoder`
- 평가: 전체의 20%를 학습에 쓰지 않고 따로 떼어 점수 산출(`random_state=42`). 배포용 모델은 전체 데이터로 재학습

| 모드 | 입력 수 | 난방 R² | 냉방 R² | 난방 MAE | 냉방 MAE |
|---|---|---|---|---|---|
| 상세 | 27 | 0.941 | 0.918 | 7.59 MBtu | 4.22 MBtu |
| 간편 | 9 | 0.734 | 0.737 | 16.05 MBtu | 7.70 MBtu |

- 단순 기준(항상 평균만 답하기)의 MAE는 난방 35.80, 냉방 17.42 MBtu
- 정확도 `100×(1−오차합/실제합)`: 상세 82.9% / 82.3%, 간편 63.8% / 67.8%
- 상세 모드 평 구간별 R²(난방/냉방): 10평대 0.892/0.871, **20평대 0.905/0.895**, 30평대 0.920/0.903, 60평 이상 0.933/0.909
- API 경로 검증: 학습에 쓰지 않은 데이터 1,500건을 `lambda_handler`에 JSON으로 넣었을 때 상세 R² 0.939(난방)/0.911(냉방), 간편 R² 0.751/0.713. 모델 직접 계산과의 차이는 0.005 MBtu 이하
- 자세한 결과: [`docs/resstock_results.md`](docs/resstock_results.md), [`docs/resstock_metrics.json`](docs/resstock_metrics.json)

### 현재 EC2에 배포된 모델 (재학습 실험용, 태그 `v2`)

재학습 효과를 공정하게 재려고 EC2 이미지는 전체 데이터가 아니라 아래 분할로 학습합니다(`scripts/resstock_prep.py`의 `experiment_split`, seed 고정). 위 표는 전체 데이터 기준이고, 아래는 평가용(holdout) 6,564채 기준입니다.

| 묶음 | 건물 수 | 역할 |
|---|---|---|
| train | 26,258 | v1이 학습 |
| pool | 10,940 | 서비스에 새로 들어오는 건물. 테스트 요청·피드백은 여기서만 |
| holdout | 6,564 | 평가 전용. v1·v2 모두 학습하지 않음 |

| 모델 | 학습 건수 | 상세 R² (난방/냉방) | 간편 R² (난방/냉방) |
|---|---|---|---|
| v1 (재학습 전) | 26,258 | 0.9371 / 0.9167 | 0.7361 / 0.7372 |
| v2 (로그 1,600건 추가, 현재 배포) | 27,858 | 0.9365 / 0.9180 | 0.7388 / 0.7387 |

R² 변화의 95% 구간이 모두 0을 포함해 **유의한 개선은 없었습니다.** 로그 건물이 학습 데이터와 분포가 거의 같고, 모델이 이미 충분히 학습된 상태였기 때문으로 판단합니다(정답을 전부 안다고 가정한 상한도 R² 약 +0.002). 자세한 내용: [`docs/retrain_report.md`](docs/retrain_report.md)

## 🔌 API

`api/lambda_function.py`의 `lambda_handler`가 AWS Lambda 함수 URL과 로컬 서버(`api/server.py`)에서 같은 코드로 동작합니다.

- `GET` : 사용법(필수 입력, 허용값, 숫자 범위)
- `POST`: JSON 본문으로 예측

### 요청 예시 (간편 모드)

```json
{
  "mode": "simple",
  "area_pyeong": 24, "stories": 1, "state": "TX", "climate_zone": "2A",
  "building_type": "Single-Family Detached", "vintage": "1990s",
  "cooling_type": "Central AC", "heating_type": "Ducted Heating", "heating_fuel": "Natural Gas"
}
```

`mode`를 생략하면 상세 전용 입력이 하나라도 있을 때 `detail`, 아니면 `simple`로 처리합니다.

### 응답 예시

```json
{
  "mode": "simple",
  "heating_mbtu_per_year": 4.95,
  "cooling_mbtu_per_year": 36.42,
  "heating_kwh_per_year": 1449,
  "cooling_kwh_per_year": 10675,
  "validation_r2": {"heating": 0.734, "cooling": 0.737},
  "note": "간편 모드는 입력이 적어 참고용입니다(검증 R² 약 0.73). 정확한 값은 detail 모드를 사용하세요.",
  "request_id": "27d3f534bb0442cfbdaa79ef336400c4"
}
```

(수치는 예시이며, 환경에 따라 소수점 이하가 다를 수 있습니다.)

### 응답 코드

| 코드 | 상황 |
|---|---|
| 200 | 정상 예측 |
| 400 | 입력 없음, JSON 형식 오류, 입력 누락, 허용되지 않는 값, 평수가 학습 범위 밖, 숫자가 아님, 잘못된 `mode` |
| 500 | 모델을 불러오지 못함 등 서버 문제 (`{"error": "...", "detail": "..."}`) |

### 로컬 테스트 (저장소 루트에서)

```bash
python -m pip install -r api/requirements.txt
python scripts/resstock_train.py     # 처음 한 번: 모델 학습 (models/*.joblib 생성)
python api/test_local.py             # API 11건 + 피드백 오류 2건 + 로그 형식 3건 = 16건, 16/16 통과 확인
```

> `models/*.joblib`은 학습할 때 쓴 scikit-learn 버전에서만 열립니다. 로드 오류(500)가 나면 `python scripts/resstock_train.py`를 다시 실행하세요.

## 🧾 로그 (재학습·강화학습용)

요청마다 JSON 한 줄(`predict` / `predict_error` / `feedback`)을 남기고, Lambda에서는 CloudWatch Logs에 자동으로 쌓입니다. 예측 응답의 `request_id`로 나중에 실제값을 보내면(`{"feedback": {"request_id": ..., "actual_heating_mbtu": ..., "actual_cooling_mbtu": ...}}`) 입력·예측·정답이 이어져 재학습 데이터가 됩니다. 필드 설명, S3 내보내기 절차, 정리 방법은 [`docs/logging.md`](docs/logging.md), 형식 예시는 `docs/sample_logs.jsonl`, 변환은 `scripts/logs_to_training.py`.

## 🔁 재학습 절차 (로그 → 재학습 → 재배포)

```bash
# 1) 테스트 로그 쌓기: pool 건물을 예측 요청하고 실제값(ResStock 시뮬레이션 값)을 피드백 (팀원마다 다른 --part)
python scripts/send_test_requests.py --url http://<EC2 주소>/predict --part 1/4 --n 400
# 2) EC2에서 로그 내보내기 (재배포하면 컨테이너 로그가 사라지므로 먼저!)
docker compose logs --no-color api > ~/logs_v1.txt
# 3) 로그 → 학습표 (request_id로 예측과 피드백을 이음, 중복 제거)
python scripts/logs_to_training.py logs_v1.txt data/retrain_logs.csv.gz
# 4) 전/후 비교 보고서 (무결성 검사, v1 vs v2, 95% 구간, 학습곡선)
python scripts/retrain_report.py --logs data/retrain_logs.csv.gz
# 5) data/retrain_logs.csv.gz 를 PR로 머지 → 자동 배포 시 Docker 빌드에서 v2로 학습
# 6) 배포된 서비스 점수 재기 (배포 전 before / 배포 후 after, 같은 holdout 600채)
python scripts/eval_service.py --url http://<EC2 주소>/predict --label after
```

- 피드백 정답은 실사용자 측정값이 아니라 **정답을 아는 팀원이 보낸 ResStock 시뮬레이션 값**입니다. 예측값을 정답으로 복사하지 않습니다.
- `logs_v1.txt` 같은 원본 로그는 저장소에 올리지 않습니다.

## 🚀 EC2 자동 배포 (GitHub Actions)

- `main`에 `api/**`, `web/**`, `scripts/**`, `data/**`, `docker-compose.yml` 변경이 머지되면 `.github/workflows/deploy.yml`이 실행됩니다(수동 실행도 가능).
- 순서: Secrets 확인 → SSH 접속 → `scripts/deploy_ec2.sh`(최신 코드 받기, `docker compose up --build -d`, 상태 확인) → 외부에서 `/health` 확인
- 필요한 Secrets(조장 관리): `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`. **EC2를 껐다 켜면 공인 IP가 바뀌므로 `EC2_HOST`를 새 주소로 고쳐야 합니다.** (첫 배포 실패 원인이 이것이었음)
- 80번 포트를 다른 컨테이너가 쓰고 있으면 배포가 실패하므로, 기존 컨테이너를 정리한 뒤 다시 실행합니다.

## 🐳 컨테이너로 실행 (Docker Compose)

API와 화면을 컨테이너 2개로 묶어 한 번에 실행합니다. 같은 구성을 EC2에도 그대로 씁니다.

```bash
docker compose up --build        # 처음에는 모델 학습 때문에 수 분 걸립니다
```

- 화면: `http://localhost` (80 포트가 사용 중이면 `WEB_PORT=8080`으로 지정해 실행, 윈도우 PowerShell은 `$env:WEB_PORT=8080; docker compose up --build`)
- 상태 확인: `http://localhost/health` (사용법 JSON이 나오면 정상)
- 화면의 `/predict` 요청은 nginx가 API 컨테이너(`api:8000`)로 넘겨 줍니다. API 포트는 내 컴퓨터(127.0.0.1)에만 열려 있습니다.
- 구성: `api/Dockerfile.server`(API, gunicorn), `web/Dockerfile` + `web/nginx.conf`(화면), `docker-compose.yml`
- Lambda용 이미지는 기존 `api/Dockerfile` 그대로입니다.

## 🖥️ 입력 화면 (로컬)

`web/index.html` + `web/app.js`: 간편/상세 탭, 입력 폼, 결과(kWh, MBtu), 경고 표시, 입력 검사(범위·빈 칸).

```bash
python -m pip install flask flask-cors
python api/server.py                 # http://127.0.0.1:8000  (lambda_function 을 그대로 호출)
cd web && python -m http.server 5500 # 브라우저에서 http://127.0.0.1:5500/index.html
```

AWS 배포 후에는 `web/app.js` 맨 위의 `API_URL`을 Lambda 함수 URL로 바꾸고, 함수 URL의 CORS를 허용해야 합니다.

## 🛠️ 기술 스택

- 데이터 처리·학습: Python, pandas, scikit-learn, joblib
- API: AWS Lambda 호환 핸들러(`lambda_handler`), 로컬은 Flask
- 화면: HTML, JavaScript (fetch)
- 배포·운영: Docker Compose(api + nginx web), AWS EC2, GitHub Actions(SSH 자동 배포)
- 이전 단계: AWS Lambda(컨테이너 이미지) + 함수 URL, ECR, CloudWatch Logs, S3 내보내기

## 📁 폴더 구조

```
energy_efficiency/
├── scripts/
│   ├── extract_resstock_v2.py   # 원본 CSV에서 60개 컬럼, 8% 추출
│   ├── resstock_prep.py         # 학습표 만들기 (단위 변환, 파생 변수)
│   ├── resstock_train.py        # 학습·평가·모델 저장
│   ├── resstock_predict.py      # 입력 검증 + 예측
│   ├── logs_to_training.py      # 내보낸 로그 -> 재학습용 표
│   ├── retrain_common.py        # 재학습 실험 공통 도구
│   ├── send_test_requests.py    # 테스트 요청 + 피드백 보내기
│   ├── retrain_report.py        # 재학습 전/후 비교 보고서
│   ├── eval_service.py          # 배포된 서비스 점수 재기
│   └── deploy_ec2.sh            # EC2 배포 스크립트 (Actions가 실행)
├── data/resstock_sample_v2.csv.gz   # 추출한 샘플 (학습에 사용)
├── data/retrain_logs.csv.gz     # 서비스 로그에서 만든 재학습 데이터 1,600행
├── .github/workflows/deploy.yml # EC2 자동 배포
├── models/                      # resstock_{detail,simple}.joblib
├── docs/                        # 결과·입력 항목 설명, 지표 JSON
├── api/
│   ├── lambda_function.py       # Lambda 핸들러
│   ├── server.py                # 로컬 테스트용 Flask 서버
│   ├── test_local.py            # 로컬 테스트 16건
│   ├── Dockerfile               # Lambda 용 컨테이너 이미지 (빌드 중 재학습)
│   ├── Dockerfile.server        # 웹 서버용 API 이미지 (EC2/ECS/compose)
│   ├── requirements-server.txt  # 웹 서버용 추가 패키지
│   └── requirements.txt
├── web/                         # 입력 화면 (index.html, app.js, nginx.conf, Dockerfile)
├── docker-compose.yml           # api + web 컨테이너 묶음
├── members/                     # 팀원별 소개
├── .dockerignore
└── README.md
```

초기 UCI 실험 파일(`preprocessing.py`, `model.py`, `ENB2012_*` 등)이 남아 있다면 참고용 기록이며, 현재 서비스는 위 구조를 사용합니다.

## 🗺️ 진행 상황

- [x] 데이터 선정·전처리 (UCI → ResStock로 교체)
- [x] 모델 학습·검증 (상세 R² 0.94/0.92)
- [x] API 구현, 로컬 테스트 16/16, 검증 데이터 1,500건 확인
- [x] 요청 로그(JSON)와 피드백 기록 구현 (로컬 확인)
- [x] 입력 화면 (로컬에서 동작 확인)
- [x] AWS 배포: CloudShell 빌드 → ECR → Lambda 함수 URL
- [x] 배포 후 정상·오류 요청 확인과 증거 캡처
- [x] CloudWatch에 로그가 쌓이는지 확인, 로그 스트림 하나를 S3로 내보내기
- [x] Docker Compose 컨테이너화, EC2 배포
- [x] GitHub Actions로 EC2 자동 배포
- [x] 서비스 로그 1,600건으로 재학습(v2)·자동 재배포, 전후 비교 (유의한 개선 없음)
- [ ] 실습 후 자원 정리 (Lambda, ECR, 로그 그룹, S3)
- [ ] 피드백에 출처·확정 시각 기록, 학습 데이터와 다른 분포(예: 한랭 기후)의 로그로 재학습 재시도
- [ ] 간편 모드 정확도 개선, 공동주택 오차 개선

## 👥 팀 구성

| 이름 | 역할 |
|---|---|
| (팀원 이름) | (역할) |