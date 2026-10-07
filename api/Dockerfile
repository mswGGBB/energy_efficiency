# 빌드는 저장소 "루트"에서:  docker build -f api/Dockerfile -t energy-load-predictor .
FROM public.ecr.aws/lambda/python:3.12

COPY api/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 전처리·학습·예측 코드와 학습용 샘플 데이터 (저장소와 같은 폴더 구조)
COPY scripts/resstock_prep.py scripts/resstock_train.py scripts/resstock_predict.py ${LAMBDA_TASK_ROOT}/scripts/
COPY data/resstock_sample_v2.csv.gz ${LAMBDA_TASK_ROOT}/data/

# 모델은 이 이미지의 라이브러리 버전으로 빌드 때 학습 (버전 불일치로 모델을 못 읽는 문제를 막음, 1~3분)
RUN python ${LAMBDA_TASK_ROOT}/scripts/resstock_train.py

COPY api/lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
