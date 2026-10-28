# 로그 설계: 재학습·강화학습에 필요한 기록과 CloudWatch → S3 내보내기

## 1. 무엇을 남기나

`api/lambda_function.py`는 요청마다 **JSON 한 줄**을 표준 출력으로 남깁니다. Lambda에서는 이 출력이 자동으로 CloudWatch Logs(`/aws/lambda/<함수 이름>`)에 쌓입니다. 별도 설정이나 추가 패키지는 필요 없습니다.

| event | 언제 | 주요 필드 |
|---|---|---|
| `predict` | 예측 성공(200) | `request_id`, `ts`, `mode`, **`inputs`**(모델 입력 전체), **`prediction`**(난방·냉방 MBtu), `validation_r2`, `model_version`, `warnings`, `latency_ms` |
| `predict_error` | 입력 오류(400)·서버 오류(500) | `request_id`, `status`, `error`(분류 코드), `error_message`, `input_keys`, `mode` |
| `feedback` | 실제값을 알게 되어 보낸 정답 | `feedback.request_id`(어느 예측의 정답인지), `actual_heating_mbtu`, `actual_cooling_mbtu` |

사용법 조회(GET)는 학습에 필요 없어 기록하지 않습니다. 이름·주소·IP 같은 개인정보는 받지도 남기지도 않습니다(주택 조건만 기록).

예측 응답에도 `request_id`가 들어갑니다. 나중에 실제 에너지 사용량이나 정밀 시뮬레이션 값을 알게 되면 같은 `request_id`로 정답을 보냅니다.

```json
POST {"feedback": {"request_id": "27d3f5...", "actual_heating_mbtu": 4.23, "actual_cooling_mbtu": 41.48}}
```

## 2. 왜 이 필드들이 재학습·강화학습에 필요한가

- **재학습(지도학습)**: 학습표는 `inputs`(X)와 `feedback`의 실제값(y)입니다. `request_id`로 두 로그를 이어 붙이면 라벨 있는 새 학습 데이터가 되고, `scripts/logs_to_training.py`가 이 변환을 합니다.
- **드리프트 감시**: `inputs` 분포(주·평수·설비)가 학습 데이터와 달라지는지, `warnings`(학습 범위 밖 값)가 늘어나는지 봅니다. `model_version`·`validation_r2`로 어느 모델이 낸 예측인지 구분합니다.
- **강화학습식 해석**: 상태(state) = `inputs`, 행동(action) = `prediction`, 보상(reward) = 정답이 들어온 뒤의 `-|예측-실제|/실제`입니다. 변환 스크립트가 `reward_heating`, `reward_cooling` 열을 만듭니다.
  - 주의: 이 서비스는 예측 값을 내는 회귀 모델이라, 엄밀한 의미의 강화학습(행동이 다음 상태를 바꾸는 순차 결정)은 아닙니다. 위 기록은 **보상이 붙은 (상태, 행동) 로그**라서 나중에 정책을 학습하거나 오프라인 평가를 하는 재료로 쓸 수 있다는 뜻입니다.
- **품질 관리**: `predict_error`의 `error` 분류(누락·허용되지 않는 값·범위 밖·모델 로드 실패)와 `latency_ms`로 어떤 입력이 자주 틀리는지, 느린지 확인합니다.

`docs/sample_logs.jsonl`이 실제 형식의 예시입니다. **피드백 값은 형식을 보이기 위해 예측에 ±20% 오차를 임의로 준 가짜 값**이며 실제 정답이 아닙니다.

## 3. 로컬에서 확인

```
python api/test_local.py          # 16/16 (로그 형식·request_id 연결 검사 3건 포함)
python scripts/logs_to_training.py docs/sample_logs.jsonl out.csv
```

## 4. AWS: 로그 확인 → S3로 내보내기 (CloudShell 또는 콘솔)

전제: Lambda 함수가 배포되어 있고 요청을 몇 번 보낸 상태. 아래 `<...>`는 본인 값으로 바꿉니다. 리전은 예시로 `ap-northeast-2`입니다.

### 4-1. CloudWatch에서 로그가 남는지 확인
콘솔: CloudWatch → 로그 그룹 → `/aws/lambda/<함수 이름>` → 로그 스트림(날짜별) 열기 → 위 JSON 줄이 보이면 성공.

또는 CloudShell:
```
aws logs tail /aws/lambda/<함수 이름> --since 30m
```
로그 그룹이 없으면 함수를 한 번도 호출하지 않았거나, 실행 역할에 로그 쓰기 권한(`AWSLambdaBasicExecutionRole`)이 없는 것입니다.

### 4-2. S3 버킷 만들기 (같은 리전)
```
aws s3 mb s3://<버킷 이름> --region ap-northeast-2
```
(SSE-KMS 암호화 버킷은 내보내기 대상이 될 수 없습니다. 기본 암호화(SSE-S3)로 두세요.)

### 4-3. 버킷 정책에 CloudWatch Logs 허용 추가
콘솔: S3 → 버킷 → 권한 → 버킷 정책에 아래를 붙여넣고 `<버킷>`, `<계정ID>`를 바꿉니다.
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "logs.ap-northeast-2.amazonaws.com"},
     "Action": "s3:GetBucketAcl", "Resource": "arn:aws:s3:::<버킷>",
     "Condition": {"StringEquals": {"aws:SourceAccount": "<계정ID>"}}},
    {"Effect": "Allow", "Principal": {"Service": "logs.ap-northeast-2.amazonaws.com"},
     "Action": "s3:PutObject", "Resource": "arn:aws:s3:::<버킷>/energy-logs/*",
     "Condition": {"StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control", "aws:SourceAccount": "<계정ID>"}}}
  ]
}
```

### 4-4. 로그 스트림 하나 내보내기
콘솔: CloudWatch → 로그 그룹 선택 → 작업 → **Amazon S3로 데이터 내보내기** → 기간, **스트림 접두사**(내보낼 로그 스트림 이름 앞부분, 예: `2026/10/28/`), 버킷, 접두사 `energy-logs` 입력.

CloudShell:
```
aws logs create-export-task \
  --log-group-name /aws/lambda/<함수 이름> \
  --log-stream-name-prefix "2026/10/28/" \
  --from <시작 epoch 밀리초> --to <끝 epoch 밀리초> \
  --destination <버킷 이름> --destination-prefix energy-logs
aws logs describe-export-tasks          # status 가 COMPLETED 인지 확인
aws s3 ls s3://<버킷 이름>/energy-logs/ --recursive
```
`--from/--to`는 `date -d "2026-10-28 00:00" +%s000`처럼 만듭니다. 로그가 많지 않아도 내보내기는 보통 몇 분 안에 끝나지만, 길어질 수 있으니 `describe-export-tasks`로 확인하세요.

### 4-5. 내보낸 로그로 재학습용 표 만들기
```
aws s3 cp s3://<버킷 이름>/energy-logs/ ./exported --recursive
python scripts/logs_to_training.py ./exported training_from_logs.csv
```

### 권한이 막혔을 때
학교 계정은 IAM·버킷 정책 수정이 막혀 있을 수 있습니다. `create-export-task`나 버킷 정책 단계에서 `AccessDenied`가 나오면 그 화면을 캡처하고 담당자에게 권한을 요청하세요. 대안으로 Logs Insights 쿼리 결과를 CSV로 내려받아 S3 콘솔에서 직접 올릴 수 있지만, 이것은 "내보내기 작업"이 아니라 수동 업로드이므로 제출 때 그렇게 표시해야 합니다.

## 5. 실습 후 정리
- 내보낸 S3 객체와 버킷 삭제, Lambda 함수·ECR 저장소 삭제
- CloudWatch 로그 그룹 `/aws/lambda/<함수 이름>` 삭제 (남겨 두면 저장 비용)
