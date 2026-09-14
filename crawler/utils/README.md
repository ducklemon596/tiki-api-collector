# Utilities

## Responsibility

Contains only small, reusable data helpers: product-ID input parsing and successful-product cleanup.

## Where It Fits

Execution loads input through this folder, while browser classification normalizes successful JSON responses through it.

## Inputs

- Newline-delimited product ID files.
- Raw successful API JSON objects.

## Outputs

- Ordered, de-duplicated logical ID batches.
- Product records with `id`, `name`, `url_key`, `price`, cleaned description, and image URLs.

## Important Files

- `input.py` - ID validation, de-duplication, and logical batching.
- `product.py` - description cleanup and stable product-field selection.

## Design Notes

- This folder intentionally contains no checkpoint, progress, or worker lifecycle logic.
- Input order is preserved after de-duplication, which makes execution partitions reproducible.
