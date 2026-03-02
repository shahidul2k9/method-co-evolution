from pathlib import Path
import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, matthews_corrcoef
from mhc.config import *
import warnings
from mhc.util import *

ground_truth_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth")
link_root_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-link")
output_dir = Path(f"{CACHE_DIRECTORY}/data/aggregate")
mismatch_root_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-link-missmatch")

output_dir.mkdir(parents=True, exist_ok=True)
mismatch_root_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "t2p_link_metrics.csv"


def load_link_df(csv_file: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_file, na_filter=False, keep_default_na=False)
    return df.drop_duplicates()


rows = []

for gt_file in ground_truth_dir.glob("*.csv"):
    repo_name = gt_file.stem

    try:
        gt_detail_df = load_link_df(gt_file)
        gt_url_df = gt_detail_df[["from_url", "to_url"]].drop_duplicates()
        gt_url_pairs = set(map(tuple, gt_url_df.to_records(index=False)))

        for strategy_dir in link_root_dir.iterdir():
            if strategy_dir.is_dir():
                strategy_name = strategy_dir.name
                pred_file = strategy_dir / gt_file.name

                if pred_file.exists():
                    pred_detail_df = load_link_df(pred_file)
                    pred_detail_df = pred_detail_df[pred_detail_df["from_url"].isin(gt_detail_df["from_url"])]
                    pred_url_df = pred_detail_df[["from_url", "to_url"]].drop_duplicates()
                    pred_url_pairs = set(map(tuple, pred_url_df.to_records(index=False)))

                    tp_pairs = gt_url_pairs & pred_url_pairs
                    fp_pairs = pred_url_pairs - gt_url_pairs
                    fn_pairs = gt_url_pairs - pred_url_pairs

                    tp = len(tp_pairs)
                    fp = len(fp_pairs)
                    fn = len(fn_pairs)

                    y_true = [1] * tp + [0] * fp + [1] * fn
                    y_pred = [1] * tp + [1] * fp + [0] * fn

                    precision = precision_score(y_true, y_pred, zero_division=0)
                    recall = recall_score(y_true, y_pred, zero_division=0)
                    f1 = f1_score(y_true, y_pred, zero_division=0)

                    all_pairs = gt_url_pairs | pred_url_pairs
                    from_urls = {from_url for from_url, _ in all_pairs}
                    to_urls = {to_url for _, to_url in all_pairs}
                    candidate_pairs = {(from_url, to_url) for from_url in from_urls for to_url in to_urls}

                    if len(candidate_pairs) == 0:
                        mcc = 0.0
                    else:
                        mcc_y_true = [1 if pair in gt_url_pairs else 0 for pair in candidate_pairs]
                        mcc_y_pred = [1 if pair in pred_url_pairs else 0 for pair in candidate_pairs]
                        mcc = matthews_corrcoef(mcc_y_true, mcc_y_pred)

                    rows.append(
                        {
                            "repo_name": repo_name,
                            "strategy": strategy_name,
                            "gt_links": len(gt_url_pairs),
                            "pred_links": len(pred_url_pairs),
                            "tp": tp,
                            "fp": fp,
                            "fn": fn,
                            "precision": round(precision, 2),
                            "recall": round(recall, 2),
                            "f1": round(f1, 2),
                            "mcc": round(mcc, 2)
                        }
                    )

                    mismatch_df = pred_detail_df.copy()
                    mismatch_df["pair"] = list(zip(mismatch_df["from_url"], mismatch_df["to_url"]))
                    mismatch_df["label"] = mismatch_df["pair"].map(
                        lambda pair: "TP" if pair in gt_url_pairs else "FP"
                    )

                    missing_df = gt_detail_df.copy()
                    missing_df["pair"] = list(zip(missing_df["from_url"], missing_df["to_url"]))
                    missing_df = missing_df[~missing_df["pair"].isin(pred_url_pairs)].copy()
                    missing_df["label"] = "FN"

                    mismatch_df = pd.concat(
                        [mismatch_df.drop(columns=["pair"]), missing_df.drop(columns=["pair"])],
                        ignore_index=True,
                        sort=False,
                    )

                    mismatch_df = convert_float_int_columns_to_nullable_int(mismatch_df)

                    strategy_mismatch_dir = mismatch_root_dir / strategy_name
                    strategy_mismatch_dir.mkdir(parents=True, exist_ok=True)
                    mismatch_df.to_csv(strategy_mismatch_dir / gt_file.name, index=False)

    except Exception as e:
        warnings.warn(f"Could not process {gt_file}: {e}")

result_df = pd.DataFrame(rows)
result_df = convert_float_int_columns_to_nullable_int(result_df)
result_df = result_df.sort_values(["repo_name", "strategy"]).reset_index(drop=True)
result_df.to_csv(output_file, index=False)

print(f"Saved evaluation to {output_file}")
print(f"Saved mismatch files to {mismatch_root_dir}")
