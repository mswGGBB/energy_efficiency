import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# 1. 전처리된 데이터 로드
df = pd.read_csv("ENB2012_preprocessed.csv")

# 2. 입력 특성(X) 및 타깃(y) 설정
FEATURE_COLUMNS = [
    'relative_compactness', 'surface_area', 'wall_area', 'roof_area',
    'height', 'orientation', 'glazing_area', 'glazing_dist'
]
X = df[FEATURE_COLUMNS]
y = df[['heating_load', 'cooling_load']]

# 3. 데이터 분할 (80% 학습, 20% 검증)
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# 4. 모델 정의 및 학습
model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

# 5. 검증 데이터 예측
y_pred = model.predict(X_val)

# 6. 평가 지표 출력
for i, col in enumerate(y.columns):
    mae = mean_absolute_error(y_val.iloc[:, i], y_pred[:, i])
    rmse = np.sqrt(mean_squared_error(y_val.iloc[:, i], y_pred[:, i]))
    r2 = r2_score(y_val.iloc[:, i], y_pred[:, i])
    print(f"[{col}] MAE: {mae:.4f} | RMSE: {rmse:.4f} | R²: {r2:.4f}")

# 7. 학습된 모델 저장
joblib.dump(model, "building_energy_rf_model.pkl")

# ====== 샘플링해서 예측 정확도 확인 ======
np.random.seed(42)
sample_idx = np.random.choice(len(X_val), size=10, replace=False)

result = pd.DataFrame({
    '실제_난방부하': y_val['heating_load'].values[sample_idx],
    '예측_난방부하': y_pred[sample_idx, 0].round(2),
    '난방_오차율(%)': (abs(y_val['heating_load'].values[sample_idx] - y_pred[sample_idx, 0]) / y_val['heating_load'].values[sample_idx] * 100).round(2),
    '실제_냉방부하': y_val['cooling_load'].values[sample_idx],
    '예측_냉방부하': y_pred[sample_idx, 1].round(2),
    '냉방_오차율(%)': (abs(y_val['cooling_load'].values[sample_idx] - y_pred[sample_idx, 1]) / y_val['cooling_load'].values[sample_idx] * 100).round(2),
})
print(result.to_string(index=False))
print(f"\n평균 오차율 - 난방: {result['난방_오차율(%)'].mean():.2f}%, 냉방: {result['냉방_오차율(%)'].mean():.2f}%")
