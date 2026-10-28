# 🏠 건물의 냉난방 부담 예상 (8팀)

집의 평수·층수·지역·냉난방 설비 같은 조건을 입력하면, 1년 동안 필요한 난방·냉방 에너지(MBtu, kWh)를 예측해 주는 서비스입니다.

> **현재 상태**: 모델 학습, API(로컬 테스트 11/11), 입력 화면(로컬) 완료. **AWS 배포는 아직 하지 않았습니다.**
> **주의**: 학습 데이터는 미국 주택 시뮬레이션이라, 한국 집의 실제 값이 아니라 **참고용 추정치**입니다.

## 📌 프로젝트 소개

"이 정도 평수·조건이면 냉난방에 에너지가 얼마나 들까?"에 답하기 위해 만들었습니다. 머신러닝 모델이 건물 조건과 설비를 학습해, 입력한 조건의 연간 난방·냉방 부하를 알려 줍니다.

## 🎯 타겟 사용자

- 집 평수와 기본 설비만 알고 대략적인 냉난방 부담이 궁금한 일반 사용자
- 단열·창·기밀 같은 조건을 바꿔 가며 에너지 효율을 비교해 보려는 사용자

## ✨ 주요 기능

| 기능 | 설명 |
|---|---|
| 간편 모드 | 입력 9개(평수, 층수, 주, 기후 구역, 건물 유형, 건축 연대, 냉방·난방 설비, 난방 연료)로 빠르게 예측 |
| 상세 모드 | 간편 입력 + 설정온도, 기밀도, 단열 R값, 창·벽·지붕 면적 등 총 27개를 넣어 더 정확하게 예측 |
| 경고 안내 | 학습 범위를 벗어난 값은 경고를 함께 반환하고, 평수가 학습 범위(7.7~157평) 밖이면 요청을 거절 |
| 오류 응답 | 누락·잘못된 값은 `400`, 모델 문제는 `500` JSON으로 응답 (서버가 죽지 않음) |

## 🔎 입력 / 출력

**입력**: 간편 9개 / 상세 27개 (항목별 설명과 허용값은 [`docs/resstock_features.md`](docs/resstock_features.md))

**출력**
- 연간 난방 부하 `heating_mbtu_per_year`, `heating_kwh_per_year`
- 연간 냉방 부하 `cooling_mbtu_per_year`, `cooling_kwh_per_year`
- 사용한 모드, 경고(`warnings`), 모델 검증 점수(`validation_r2`)

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
- 배포 예정: AWS Lambda(컨테이너 이미지) + 함수 URL, ECR, CloudShell에서 빌드

## 📁 폴더 구조

```
energy_efficiency/
├── scripts/
│   ├── extract_resstock_v2.py   # 원본 CSV에서 60개 컬럼, 8% 추출
│   ├── resstock_prep.py         # 학습표 만들기 (단위 변환, 파생 변수)
│   ├── resstock_train.py        # 학습·평가·모델 저장
│   ├── resstock_predict.py      # 입력 검증 + 예측
│   └── logs_to_training.py      # 내보낸 로그 -> 재학습용 표
├── data/resstock_sample_v2.csv.gz   # 추출한 샘플 (학습에 사용)
├── models/                      # resstock_{detail,simple}.joblib
├── docs/                        # 결과·입력 항목 설명, 지표 JSON
├── api/
│   ├── lambda_function.py       # Lambda 핸들러
│   ├── server.py                # 로컬 테스트용 Flask 서버
│   ├── test_local.py            # 로컬 테스트 16건
│   ├── Dockerfile               # 배포용 컨테이너 이미지 (빌드 중 재학습)
│   └── requirements.txt
├── web/                         # 입력 화면 (index.html, app.js)
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
- [ ] AWS 배포: CloudShell 빌드 → ECR → Lambda 함수 URL
- [ ] 배포 후 정상·오류 요청 확인과 증거 캡처
- [ ] CloudWatch에 로그가 쌓이는지 확인, 로그 스트림 하나를 S3로 내보내기
- [ ] 실습 후 자원 정리 (Lambda, ECR, 로그 그룹)
- [ ] 간편 모드 정확도 개선, 공동주택 오차 개선
