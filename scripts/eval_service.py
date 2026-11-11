"""배포된 서비스의 점수 재기: 평가 전용(holdout) 건물을 API 에 보내 실제값과 비교합니다.

사용 (저장소 루트에서):
    python scripts/eval_service.py --url http://<EC2 주소>/predict --label before   # 재학습 전(v1)
    python scripts/eval_service.py --url http://<EC2 주소>/predict --label after    # 재배포 후(v2)

- 두 번 모두 같은 건물(--n, 고정 seed)을 쓰므로 결과를 그대로 비교할 수 있습니다.
- holdout 건물은 v1·v2 어느 쪽도 학습하지 않았습니다. 이 스크립트는 정답(피드백)을 보내지 않습니다.
- 결과는 화면에 표로 나오고 docs/service_eval_<label>.json 으로도 저장됩니다. 이 화면을 캡처하세요.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrain_common import ROOT, actuals, load_xy, post, row_inputs  # noqa: E402


def metrics(actual, pred):
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    ss_res, ss_tot = ((a - p) ** 2).sum(), ((a - a.mean()) ** 2).sum()
    return {"r2": float(1 - ss_res / ss_tot), "mae": float(np.abs(a - p).mean()),
            "accuracy": float(100 * (1 - np.abs(a - p).sum() / np.abs(a).sum()))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--label", required=True, help="결과 파일 이름표 (before / after)")
    ap.add_argument("--focus", action="store_true", help="보고서의 focus 구간 건물만 평가 (random 분할: 30평 미만 소형, cold 분할: 한랭 기후)")
    ap.add_argument("--n", type=int, default=600, help="평가 건물 수 (클수록 안정적, 기본 600)")
    args = ap.parse_args()

    X, y, split = load_xy()
    idx = list(split["focus_holdout"] if args.focus else split["holdout"])
    random.Random(7).shuffle(idx)
    idx = idx[:args.n]
    print(f"[{split['scheme']}] holdout 중 {split['focus_label'] + ' ' if args.focus else ''}{len(idx)}채로 평가 -> {args.url}\n")

    out, tags, fails = {}, set(), 0
    for mode in ["detail", "simple"]:
        act_h, act_c, pr_h, pr_c = [], [], [], []
        for i in idx:
            status, res = post(args.url, row_inputs(X, i, mode))
            if status != 200 or "heating_mbtu_per_year" not in res:
                fails += 1
                continue
            tags.add(res.get("model_tag", "?"))
            ah, ac = actuals(y, i)
            act_h.append(ah); act_c.append(ac)
            pr_h.append(res["heating_mbtu_per_year"]); pr_c.append(res["cooling_mbtu_per_year"])
        if act_h:
            out[mode] = {"n": len(act_h), "heating": metrics(act_h, pr_h), "cooling": metrics(act_c, pr_c)}
    if not out:
        sys.exit("응답을 하나도 받지 못했습니다. --url 과 서버 상태를 확인하세요.")

    print(f"응답한 모델 태그: {sorted(tags)}   (요청 실패 {fails}건)")
    print(f"{'모드':<8}{'대상':<6}{'건수':>6}{'R²':>8}{'MAE(MBtu)':>12}{'정확도%':>9}")
    for mode, r in out.items():
        for k, name in (("heating", "난방"), ("cooling", "냉방")):
            m = r[k]
            print(f"{mode:<8}{name:<6}{r['n']:>6}{m['r2']:>8.3f}{m['mae']:>12.2f}{m['accuracy']:>9.1f}")
    path = ROOT / "docs" / f"service_eval_{args.label}{'_focus' if args.focus else ''}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"label": args.label, "url_host": args.url.split("/")[2], "model_tags": sorted(tags), "n_requested": len(idx), "scheme": split["scheme"], "focus": bool(args.focus), "result": out},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {path}")


if __name__ == "__main__":
    main()
