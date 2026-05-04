import os.path
import warnings

import pandas as pd

from mhc.config import *
from mhc.util import *

method_dir = Path(f"{CACHE_DIRECTORY}/data/method")
ground_truth_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth-updated")
output_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth-updated")
output_dir.mkdir(parents=True, exist_ok=True)


def update_ground_truth():
    for gt_file in ground_truth_dir.glob("*.csv"):
        method_file = method_dir / gt_file.name

        if method_file.exists():
            try:
                gt_df = pd.read_csv(gt_file)
                method_df = pd.read_csv(method_file)

                new_rows = []

                for _, row in gt_df.iterrows():
                    updated_row = {
                        'from_url': None,
                        'to_url': None
                    }

                    for url_key, fqs_key, fqs_value in [("from_url", "from_tctracer_fqs", row.get('from_tctracer_fqs')),
                                                        ("to_url", "to_tctracer_fqs", row.get('to_tctracer_fqs'))]:
                        matched_df = method_df[method_df["tctracer_fqs"] == fqs_value]
                        if len(matched_df) == 1:
                            updated_row[url_key] = matched_df.iloc[0].get('url')
                    new_rows.append(updated_row)

                new_df = pd.DataFrame(new_rows)
                for col in ["from_url", "to_url"]:
                    if col not in gt_df.columns:
                        gt_df[col] = pd.NA
                    gt_df[col] = gt_df[col].fillna(new_df[col])

                gt_df = convert_float_int_columns_to_nullable_int(gt_df)
                gt_df.to_csv(output_dir / gt_file.name, index=False)

            except Exception as e:
                warnings.warn(f"Fail for {gt_file.name}: {e}")

        else:
            warnings.warn(f"Skipping {gt_file.name}: no matching callgraph file found")


def parse_three_columns(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        # Skip or yield the header separately
        header = next(f).strip().split(',')

        for line in f:
            line = line.strip()
            if not line:
                continue
            # split(separator, maxsplit)
            # 2 means: split at 1st comma, then 2nd comma, then stop.
            yield line.split(',', 2)


def escape_ground_truth_of_author_sun(projects: [str]):
    for file_name in projects:
        input_file = f'{DATA_DIRECTORY}/ground-truth/{file_name}.csv'
        # Use the generator to create the DataFrame
        # This is much safer for Slurm environments
        data_gen = parse_three_columns(input_file)
        df = pd.DataFrame(data_gen, columns=['project', 'test-fqn', 'tested-method-fqn'])
        df.rename(columns={'test-fqn': 'from_tctracer_fqs', 'tested-method-fqn':'to_tctracer_fqs'}, inplace=True)
        output_file = f'{DATA_DIRECTORY}/ground-truth-escaped/{file_name}.csv'
        os.makedirs(os.path.basename(output_file), exist_ok=True)
        # Save with QUOTE_ALL (quoting=1) to ensure columns 2 and 3 are escaped
        df.to_csv(output_file, index=False)

        print(f"Successfully processed and saved to {output_file}")


if __name__ == "__main__":
    # Escape unescaped ground truth and move into the t2p-ground-truth-updated folder
    # escape_ground_truth_of_author_sun(['jenkins', "dubbo"])
    update_ground_truth()
