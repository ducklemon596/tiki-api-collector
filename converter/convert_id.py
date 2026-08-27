import pandas as pd
import os
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
input_dir = project_root / "data" / "input"
output_dir = project_root / "data" / "input"

os.makedirs(output_dir, exist_ok=True)

for filename in os.listdir(input_dir):
    if filename.endswith(".xlsx"):
        file_path = input_dir / filename
        df = pd.read_excel(file_path)

        product_ids = df.iloc[:, 0].dropna().astype(str)

        output_file = output_dir / f"{filename.split('.')[0]}.txt"

        if os.path.exists(output_file):
            print(f"File {output_file} already exists. Skipping.")
            continue

        product_ids.to_csv(output_file, index=False, header=False)

        print(f"Created file {output_file} with {len(product_ids):,} product IDs.")
