"""서비스 로그 쌓기: '서비스 풀' 건물을 API 에 예측시키고, 정답(실제값)을 피드백으로 되돌려 보냅니다.

사용 (저장소 루트에서, 팀원마다 자기 몫 번호로):
    python scripts/send_test_requests.py --url http://<EC2 주소>/predict --part 1/5 --n 300

- 건물은 resstock_prep.experiment_split 의 pool(재학습 전 모델이 본 적 없는 건물)에서만 뽑습니다.
- --part i/K : pool 을 K등분 하여 i번째 조각만 씁니다. 팀원이 서로 다른 i 를 쓰면 건물이 겹치지 않습니다.
- 같은 조각에서 더 보내려면 --skip 으로 이미 보낸 개수만큼 건너뜁니다(예: 처음 300 -> 다음은 --skip 300).
- 서버는 예측(predict)과 피드백(feedback)을 request_id 로 이어 기록합니다. 정답은 ResStock 데이터의 실제 시뮬레이션 값입니다.
  즉 '실제 사용자'가 아니라 '정답을 아는 테스터가 보내는 요청'이며, 보고서에 그렇게 적어야 합니다.
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrain_common import actuals, load_xy, post, row_inputs  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="예: http://<EC2 주소>/predict  (Lambda 는 함수 URL)")
    ap.add_argument("--part", default="1/1", help="i/K 형식. 팀원마다 다른 i (기본 1/1)")
    ap.add_argument("--n", type=int, default=300, help="보낼 건물 수")
    ap.add_argument("--skip", type=int, default=0, help="이 조각에서 앞쪽 몇 개를 건너뛸지")
    ap.add_argument("--focus", action="store_true", help="보고서에서 따로 보는 구간(resstock_prep.SPLIT_SCHEME 의 focus)의 건물만 보냄")
    ap.add_argument("--mode", default="detail", choices=["detail", "simple"], help="detail 로 보내면 상세·간편 모델 모두 재학습에 쓸 수 있음")
    args = ap.parse_args()

    i_part, k_part = (int(v) for v in args.part.split("/"))
    if not 1 <= i_part <= k_part:
        sys.exit("--part 는 i/K 형식이고 1 <= i <= K 여야 합니다. 예: 2/5")

    X, y, split = load_xy()
    pool = list(split["focus_pool"] if args.focus else split["pool"])
    mine = pool[i_part - 1::k_part]
    random.Random(42).shuffle(mine)                        # 모든 팀원이 같은 순서 규칙 -> 재실행해도 같은 건물
    chosen = mine[args.skip:args.skip + args.n]
    print(f"[{split['scheme']}] pool {len(pool)}채{'(' + split['focus_label'] + '만)' if args.focus else ''} 중 내 조각 {len(mine)}채, 이번에 {len(chosen)}채 전송 -> {args.url}")
    if not chosen:
        sys.exit("보낼 건물이 없습니다. --skip 을 줄이세요.")

    ok = pred_fail = fb_fail = 0
    abs_err_h = abs_err_c = 0.0
    tag = None
    for n, i in enumerate(chosen, 1):
        status, res = post(args.url, row_inputs(X, i, args.mode))
        if status != 200 or "request_id" not in res:
            pred_fail += 1
            if pred_fail <= 3:
                print(f"  예측 실패({status}): {str(res)[:150]}")
            continue
        tag = tag or res.get("model_tag")
        ah, ac = actuals(y, i)
        status, _ = post(args.url, {"feedback": {"request_id": res["request_id"], "actual_heating_mbtu": ah, "actual_cooling_mbtu": ac}})
        if status != 200:
            fb_fail += 1
            continue
        ok += 1
        abs_err_h += abs(res["heating_mbtu_per_year"] - ah)
        abs_err_c += abs(res["cooling_mbtu_per_year"] - ac)
        if n % 50 == 0:
            print(f"  {n}/{len(chosen)} 전송")
    print(f"\n완료: 예측+피드백 성공 {ok}건 / 예측 실패 {pred_fail}건 / 피드백 실패 {fb_fail}건   (응답 모델 태그: {tag})")
    if ok:
        print(f"이번에 보낸 건물에서의 평균 오차(MAE): 난방 {abs_err_h / ok:.2f} MBtu, 냉방 {abs_err_c / ok:.2f} MBtu")
    if pred_fail or fb_fail:
        print("실패가 있으면 --url 과 서버 상태(/health)를 확인하세요.")


if __name__ == "__main__":
    main()
