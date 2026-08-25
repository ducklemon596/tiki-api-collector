import json
import os

with open("output_data/tiki_products_part_0001.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    print(f"Loaded {len(data)} products from JSON file.")
