# Utilities

## Responsibility

This folder contains small reusable helpers for product-ID input parsing and
successful-product cleanup.

## Where It Fits

Execution loads input through this folder. Browser classification uses it to
normalize successful JSON responses.

## Inputs

- Newline-delimited product ID files.
- Raw successful API JSON objects.

## Outputs

- Ordered, de-duplicated logical ID batches.
- Product records with `id`, `name`, `url_key`, `price`, cleaned description, and image URLs.

## Important Files

- `input.py` - validates IDs, removes duplicates, and creates logical batches.
- `product.py` - cleans descriptions and selects stable product fields.

## Design Notes

- This folder has no checkpoint, progress, or worker lifecycle logic.
- Input order is kept after de-duplication, so execution partitions are reproducible.
