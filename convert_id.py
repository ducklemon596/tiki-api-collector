import pandas as pd
import os

input_dir = "excel_files/"  # Thư mục chứa file Excel
output_dir = "txt_files/"  # Thư mục lưu file txt

os.makedirs(output_dir, exist_ok=True)

for filename in os.listdir(input_dir):
    if filename.endswith(".xlsx"):
        file_path = os.path.join(input_dir, filename)
        df = pd.read_excel(file_path)

        product_ids = df.iloc[:, 0].dropna().astype(str)

        output_file = os.path.join(output_dir, f"{filename.split('.')[0]}.txt")

        if os.path.exists(output_file):
            print(f"File {output_file} already exists. Skipping.")
            continue

        product_ids.to_csv(output_file, index=False, header=False)

        print(f"Created file {output_file} with {len(product_ids):,} product IDs.")
