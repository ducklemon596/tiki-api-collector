# Input Converter

## Responsibility

Provides an optional utility that turns the first column of each Excel workbook in `data/input/` into a same-name newline-delimited product-ID text file.

## Where It Fits

It is a preparation tool, not part of the Selenium crawler runtime. The crawler itself reads the resulting `.txt` input configured in `crawler/config.py`.

## Inputs

- `.xlsx` files stored in `data/input/`.
- Product IDs in the first worksheet column.

## Outputs

- A corresponding `.txt` file in `data/input/`, one ID per line.

## Important Files

- `convert_id.py` — scans input workbooks, skips output files that already exist, and writes converted IDs.

## Design Notes

- Review source workbook format before running; the script intentionally assumes the first column contains the IDs.
- Existing `.txt` outputs are skipped rather than overwritten.
