# ResStock 모델 — 입력 특성(Feature) 설명

모델이 연간 난방·냉방 부하를 예측하려면 어떤 값을 넣어야 하는지 정리한 문서입니다.
허용 값과 범위는 학습된 모델 파일(`models/resstock_detail.joblib`)에서 직접 뽑았습니다.

> 이 모델은 **미국 주택 시뮬레이션 데이터**로 학습했습니다. 그래서 지역은 미국 주(state), 온도는 °F, 벽·창 면적은 ft²로 받습니다. 한국 집에 적용할 때의 환산은 6장을 보세요.

## 1. 한눈에 보기

| 모드 | 입력 수 | 점수(R², 난방 / 냉방) | 용도 |
|---|---|---|---|
| **상세** | 27개 | 0.94 / 0.92 | 목표(0.85) 달성. 정확한 예측이 필요할 때 |
| 간편 | 9개 | 0.73 / 0.74 | 목표 미달. 대략적인 참고용 |

**평수만으로는 예측할 수 없습니다.** 같은 평수여도 지역과 설비에 따라 부하가 크게 달라서, 평수 하나만 쓴 모델은 R²가 0.2 수준이었습니다. 지역, 냉난방 설비, 설정온도, 외풍(기밀도)이 점수에 특히 크게 영향을 줍니다(7장).

## 2. 간편 모드 입력 (9개)

| 입력 | 뜻 | 형식·허용 값 |
|---|---|---|
| `area_pyeong` | 냉난방이 되는 실내 바닥면적 (평) | 숫자, **7.7 ~ 157평** (밖이면 거절) |
| `stories` | 층수 | 숫자, 1 ~ 21 |
| `state` | 지역(주) | 3-1 참고 |
| `climate_zone` | 기후 구역 | 3-1 참고 |
| `building_type` | 건물 유형 | 3-2 참고 |
| `vintage` | 건축 연대 | 3-2 참고 |
| `cooling_type` | 냉방 설비 | 3-3 참고 |
| `heating_type` | 난방 설비 | 3-3 참고 |
| `heating_fuel` | 난방 연료 | 3-3 참고 |

## 3. 상세 모드 입력 (27개)

아래 표 전체가 상세 모드의 27개이고, 이 중 9개(2장)는 간편 모드에도 쓰입니다. 표의 "흔한 값"은 학습 데이터의 중앙값 또는 최빈값이며, 모를 때 참고만 하세요(그 값으로 대체했을 때의 정확도는 측정하지 않았습니다).

### 3-1. 위치

| 입력 | 뜻 | 허용 값 / 범위 | 흔한 값 |
|---|---|---|---|
| `state` | 주 (2글자 약어) | AL AR AZ CA CO CT DC DE FL GA IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY (49개) | CA |
| `climate_zone` | 기후 구역(ASHRAE/IECC). 숫자 1(가장 더움)~7(가장 추움), 문자 A 습윤 / B 건조 / C 해양성 | 1A 2A 2B 3A 3B 3C 4A 4B 4C 5A 5B 6A 6B 7A 7B | 5A |

### 3-2. 건물 기본 정보

| 입력 | 뜻 | 허용 값 / 범위 | 흔한 값 |
|---|---|---|---|
| `area_pyeong` | 냉난방이 되는 실내 바닥면적 (평) | 7.7 ~ 157 | 34.5 |
| `stories` | 층수 | 1 ~ 21 | 2 |
| `bedrooms` | 침실 수 | 1 ~ 5 | 3 |
| `occupants` | 거주 인원 (0은 데이터에 있는 값, 빈 집으로 추정) | 0 ~ 10 | 2 |
| `building_type` | 건물 유형 | `Single-Family Detached` 단독주택 / `Single-Family Attached` 연립(벽을 맞댄 단독) / `Multi-Family with 2 - 4 Units` 2~4가구 공동주택 / `Multi-Family with 5+ Units` 5가구 이상 공동주택(아파트에 가까움) / `Mobile Home` 이동식 주택 | Single-Family Detached |
| `vintage` | 건축 연대 | `<1940` `1940s` `1950s` `1960s` `1970s` `1980s` `1990s` `2000s` `2010s` | 1970s |

### 3-3. 냉난방 설비 — 점수에 크게 영향

| 입력 | 뜻 | 허용 값 | 흔한 값 |
|---|---|---|---|
| `cooling_type` | 냉방 설비. **`None`이면 냉방 부하가 0에 가깝게 나옴** | `Central AC` 중앙 냉방 / `Room AC` 방별(창문형) 에어컨 / `Heat Pump` 히트펌프 / `None` 없음 | Central AC |
| `heating_type` | 난방 설비 방식 | `Ducted Heating` 덕트식 / `Non-Ducted Heating` 덕트 없는 방식(보일러·라디에이터·전기 패널 등) / `Ducted Heat Pump` 덕트식 히트펌프 / `None` 없음 | Ducted Heating |
| `heating_fuel` | 난방 연료 | `Natural Gas` `Electricity` `Fuel Oil` `Propane` `Other Fuel` `None` | Natural Gas |

### 3-4. 설정온도 (°F)

| 입력 | 뜻 | 범위 | 흔한 값 |
|---|---|---|---|
| `heating_setpoint_f` | 난방 설정온도 | 55 ~ 80 | 70 (약 21°C) |
| `cooling_setpoint_f` | 냉방 설정온도 | 60 ~ 80 | 72 (약 22°C) |

### 3-5. 단열·기밀·창

| 입력 | 뜻 | 허용 값 / 범위 | 흔한 값 |
|---|---|---|---|
| `infiltration_ach50` | 기밀도. 숫자가 **클수록 외풍이 심함**(빈틈이 많음). 50Pa 가압 시 시간당 공기 교환 횟수 | 1 ~ 50 | 15 |
| `wall_r` | 외벽 단열 R값(숫자가 클수록 단열 좋음, 0 = 단열 없음) | 0 ~ 19 | 7 |
| `ceiling_r` | 천장 단열 R값 | 0 ~ 49 | 19 |
| `roof_r` | 지붕 단열 R값 | 0 ~ 49 | 0 |
| `floor_r` | 바닥 단열 R값 | 0 ~ 30 | 0 |
| `wall_type` | 외벽 구조 | `Wood Stud` 목조 / `Brick, 12-in, 3-wythe` 벽돌 / `CMU, 6-in Hollow` 콘크리트 블록 | Wood Stud |
| `windows` | 창 종류 (아래 표 참고) | 10종 | Double, Low-E, Non-metal, Air, M-Gain |

`windows` 허용 값 10가지:

| 값 | 뜻 |
|---|---|
| `Single, Clear, Non-metal` | 홑창, 투명, 비금속 프레임 |
| `Single, Clear, Metal` | 홑창, 투명, 금속 프레임 |
| `Single, Clear, Non-metal, Exterior Clear Storm` | 위 홑창 + 바깥 덧창 |
| `Single, Clear, Metal, Exterior Clear Storm` | 금속 홑창 + 바깥 덧창 |
| `Double, Clear, Non-metal, Air` | 복층창, 투명, 비금속 프레임 |
| `Double, Clear, Metal, Air` | 복층창, 투명, 금속 프레임 |
| `Double, Clear, Non-metal, Air, Exterior Clear Storm` | 복층창 + 바깥 덧창 |
| `Double, Clear, Metal, Air, Exterior Clear Storm` | 금속 복층창 + 바깥 덧창 |
| `Double, Low-E, Non-metal, Air, M-Gain` | 복층 저방사(Low-E) 코팅, 햇빛 투과 중간 |
| `Triple, Low-E, Non-metal, Air, L-Gain` | 삼중 저방사 코팅, 햇빛 투과 낮음 |

### 3-6. 외피 면적 (ft²)

| 입력 | 뜻 | 범위 | 흔한 값 |
|---|---|---|---|
| `wall_area_ft2` | 지상 외벽 면적 | 107 ~ 5,113 | 1,341 |
| `window_area_ft2` | 창 면적 | 6.4 ~ 1,292 | 138 |
| `roof_area_ft2` | 지붕 면적(공동주택 중간층 세대 등은 0인 경우가 있음) | 0 ~ 7,212 | 1,218 |
| `door_area_ft2` | 문 면적 | 0 ~ 20 | 20 |

### 3-7. 구조

| 입력 | 뜻 | 허용 값 | 흔한 값 |
|---|---|---|---|
| `foundation` | 기초(건물 밑) 형태 | `Slab` 슬래브(바닥이 땅에 닿음) / `Heated Basement` 난방되는 지하 / `Unheated Basement` 난방 안 되는 지하 / `Vented Crawlspace` 환기되는 낮은 바닥 공간 / `Unvented Crawlspace` 환기 안 되는 낮은 바닥 공간 / `Ambient` 건물 밑이 외기에 열린 구조 | Slab |
| `attic` | 다락 | `None` 없음 / `Vented Attic` 환기되는 다락 / `Finished Attic or Cathedral Ceilings` 마감된 다락·경사 천장 | Vented Attic |
| `garage` | 차고 | `None` / `1 Car` / `2 Car` / `3 Car` | None |

## 4. 모델 안에서 계산되는 값 (직접 넣지 않음)

| 값 | 계산 |
|---|---|
| `wall_per_floor` | 외벽 면적 ÷ 바닥면적(평 × 35.58) |
| `roof_per_floor` | 지붕 면적 ÷ 바닥면적 |
| `window_ratio` | 창 면적 ÷ 외벽 면적 |

## 5. 출력

| 항목 | 뜻 |
|---|---|
| `heating_mbtu_per_year` / `cooling_mbtu_per_year` | 연간 난방·냉방 **부하**(MBtu = 백만 Btu) |
| `heating_kwh_per_year` / `cooling_kwh_per_year` | 같은 값을 kWh로 환산 (1 MBtu = 293.07 kWh) |
| `warnings` | 숫자 입력이 학습 범위를 벗어났을 때의 안내(있을 때만) |

**부하는 전기·가스 요금이 아닙니다.** 집이 실내를 유지하려고 공급해야 하는 열량이고, 실제 에너지 사용량은 설비 효율에 따라 달라집니다.

입력 예시와 결과(상세 모드 24평, 텍사스 단독주택):

```json
{
  "area_pyeong": 24, "stories": 1, "bedrooms": 3, "occupants": 3,
  "state": "TX", "climate_zone": "2A", "building_type": "Single-Family Detached", "vintage": "1990s",
  "cooling_type": "Central AC", "heating_type": "Ducted Heating", "heating_fuel": "Natural Gas",
  "heating_setpoint_f": 70, "cooling_setpoint_f": 75, "infiltration_ach50": 15,
  "wall_r": 11, "ceiling_r": 30, "roof_r": 0, "floor_r": 0,
  "wall_area_ft2": 1100, "window_area_ft2": 120, "roof_area_ft2": 860, "door_area_ft2": 20,
  "windows": "Double, Clear, Non-metal, Air", "wall_type": "Wood Stud",
  "foundation": "Slab", "attic": "Vented Attic", "garage": "None"
}
```

결과: 난방 약 4.5 MBtu(1,308 kWh), 냉방 약 37.4 MBtu(10,973 kWh). 같은 입력에서 `cooling_type`만 `None`으로 바꾸면 냉방이 약 1.5 MBtu로 줄어듭니다. (수치는 학습 환경에 따라 소폭 달라질 수 있음)

간편 모드는 위에서 `stories`, `state`, `climate_zone`, `building_type`, `vintage`, `cooling_type`, `heating_type`, `heating_fuel`, `area_pyeong` 9개만 보내면 됩니다.

## 6. 한국 단위로 바꾸는 법

| 한국에서 아는 값 | 모델 입력 |
|---|---|
| 평 | `area_pyeong`에 그대로 |
| ㎡ (면적) | × 10.764 = ft² (`wall_area_ft2` 등) |
| °C (설정온도) | × 1.8 + 32 = °F (22°C → 약 72°F) |
| 지역 | 한국 지역은 입력할 수 없고, 비슷한 기후의 미국 주·기후 구역을 골라야 함 |

## 7. 어떤 특성이 중요한가

검증 데이터에서 한 특성의 값을 무작위로 섞었을 때 R²가 얼마나 떨어지는지 측정했습니다(클수록 중요).

| 순위 | 특성 | 난방 | 냉방 | 의미 |
|---|---|---|---|---|
| 1 | `state` | 0.34 | 0.23 | 지역이 가장 큼 |
| 2 | `climate_zone` | 0.18 | 0.29 | 기후 |
| 3 | `cooling_type` | 0.00 | **0.44** | 에어컨 유무가 냉방을 좌우 |
| 4 | `area_pyeong` | 0.00* | 0.37 | 아래 설명 참고 |
| 5 | `infiltration_ach50` | **0.32** | 0.00 | 외풍이 난방을 좌우 |
| 6 | `cooling_setpoint_f` | 0.00 | 0.31 | 냉방 설정온도 |
| 7 | `heating_setpoint_f` | 0.19 | 0.01 | 난방 설정온도 |
| 8 | `wall_per_floor` (계산값) | 0.07 | 0.10 | 바닥 대비 외벽 비율 |
| 9 | `ceiling_r` | 0.07 | 0.05 | 천장 단열 |
| 10 | `heating_fuel` | 0.11 | 0.00 | 난방 연료 |

\* 평수는 모델 안에서 "면적당 부하 × 면적"으로 곱해져 반영되기 때문에, 이 방식(입력값 섞기)으로는 중요도가 낮게 나옵니다. 실제로는 부하 총량에 직접 비례하는 필수 입력입니다.

주의: 서로 비슷한 정보를 가진 특성(예: 주와 기후 구역)은 중요도를 나눠 가져서 각각 작게 나올 수 있습니다.

**중요도가 0에 가까운 특성**은 `bedrooms`, `door_area_ft2`, `attic`, `garage`, `window_area_ft2`, `roof_area_ft2`, `floor_r`, `wall_type`, `stories`입니다. 입력을 줄이는 후보지만, 다른 특성이 대신해주고 있을 수 있어서 **빼고 다시 학습해 점수를 확인하기 전에는 줄여도 된다고 말할 수 없습니다.**

## 8. 입력 검사 규칙

- 필수 입력이 하나라도 빠지면 오류와 함께 누락된 이름을 알려줍니다.
- 범주형 값은 위 표의 허용 값만 받고, 다르면 가능한 값 목록을 알려줍니다.
- `area_pyeong`이 7.7~157평 밖이면 거절합니다 (학습하지 않은 크기).
- 그 외 숫자가 학습 범위를 벗어나면 예측은 하되 `warnings`로 알려줍니다.
