# Input Converter

## Responsibility

This optional utility converts the first column of each Excel workbook in
`data/input/` into a same-name, newline-delimited product-ID text file.

## Where It Fits

It prepares input only; it is not part of the Selenium collector runtime. The
collector reads the resulting `.txt` input configured in `collector/config.py`.

## Inputs

- `.xlsx` files in `data/input/`.
- Product IDs in the first worksheet column.

## Outputs

- A matching `.txt` file in `data/input/`, with one ID per line.

## Important Files

- `convert_id.py` — scans input workbooks, skips existing output files, and writes converted IDs.

## Design Notes

- Check the workbook format before running the tool; it assumes the first column contains IDs.
- Existing `.txt` outputs are skipped, not overwritten.
