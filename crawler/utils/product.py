"""Product-record normalization for successful browser API responses."""

import html
import re
from typing import TypeAlias

from config import HTML_TAG_REGEX

ProductRecord: TypeAlias = dict[str, object]


def clean_description(text: str | None) -> str | None:
    """Normalize description whitespace without removing paragraph boundaries."""
    if not text:
        return text
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def clean_html(raw_html: str | None) -> str:
    """Convert a product description's HTML into normalized plain text."""
    if not raw_html:
        return ""
    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    return clean_description(html.unescape(HTML_TAG_REGEX.sub(" ", text))) or ""


def extract_product_info(raw_data: ProductRecord) -> ProductRecord:
    """Select the stable product fields persisted by successful checkpoints."""
    images: list[str] = []
    raw_images = raw_data.get("images")
    if isinstance(raw_images, list):
        for image in raw_images:
            if isinstance(image, dict):
                image_url = (
                    image.get("base_url") or image.get("large_url") or image.get("url")
                )
                if isinstance(image_url, str) and image_url:
                    images.append(image_url)
    description = raw_data.get("description")
    return {
        "id": raw_data.get("id"),
        "name": raw_data.get("name"),
        "url_key": raw_data.get("url_key"),
        "price": raw_data.get("price"),
        "description": clean_html(description if isinstance(description, str) else None),
        "images": images,
    }
