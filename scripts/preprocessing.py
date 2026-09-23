"""
Energy Efficiency 데이터셋 전처리 스크립트
데이터: UCI Energy Efficiency (ENB2012_data.csv)
설명: docs/dataset_description.md 참고
"""

import pandas as pd
from sklearn.model_selection import train_test_split

# 1. 데이터 로드 & 구조 확인
df = pd.read_csv("ENB2012_data.csv")
df = df.dropna(how='all').reset_index(drop=True)  # 완전히 빈 행 제거
print(f"[1] 행: {df.shape[0]}, 열: {df.shape[1]}, 결측치: {df.isnull().sum().sum()}개")

# 2. 컬럼명 정리
df = df.rename(columns={
    'X1': 'relative_compactness', 'X2': 'surface_area', 'X3': 'wall_area',
    'X4': 'roof_area', 'X5': 'height', 'X6': 'orientation',
    'X7': 'glazing_area', 'X8': 'glazing_dist',
    'Y1': 'heating_load', 'Y2': 'cooling_load'
})
print(f"[2] 컬럼명 정리 완료: {df.columns.tolist()}")

# 3. 파생변수 추가 (보조용, 학습에는 미사용)
PYEONG = 3.3058
df['floor_area_pyeong'] = (df['roof_area'] / PYEONG).round(2)
print("[3] floor_area_pyeong 파생변수 추가 완료")

# 4. 범주형 변수 처리 결정
# orientation, glazing_dist는 범주형이지만 RandomForest 사용 -> 인코딩 없이 그대로 사용
print("[4] orientation, glazing_dist -> 인코딩 없이 정수값 그대로 사용 (RandomForest 채택)")

# 5. 입력(X)/출력(y) 분리
FEATURE_COLUMNS = [
    'relative_compactness', 'surface_area', 'wall_area', 'roof_area',
    'height', 'orientation', 'glazing_area', 'glazing_dist'
]
X = df[FEATURE_COLUMNS]
y = df[['heating_load', 'cooling_load']]
print(f"[5] X shape: {X.shape}, y shape: {y.shape}")

# 6. 학습/테스트 분리 (랜덤 셔플 필수: 동일 건물 조합 반복 구조)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"[6] X_train: {X_train.shape}, X_test: {X_test.shape}")

# 7. 스케일링
# RandomForest는 스케일에 영향받지 않으므로 생략
print("[7] 스케일링 생략 (RandomForest 채택 - 스케일 무관)")

# 전처리 완료 데이터 저장
df.to_csv("ENB2012_preprocessed.csv", index=False, encoding="utf-8-sig")
print("\n전처리 완료. 저장 파일: ENB2012_preprocessed.csv")
