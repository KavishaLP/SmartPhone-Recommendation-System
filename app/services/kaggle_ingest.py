"""Ingest Griko Nibras / Kaggle *Amazon Cell Phones Reviews* into SQLite.

Dataset: https://www.kaggle.com/datasets/grikomsn/amazon-cell-phones-reviews

Files (date-prefixed, e.g. ``20191226-items.csv``):

    items.csv   — asin, brand, title, url, image, rating, totalReviews, price, …
    reviews.csv — asin, reviewer, rating, date, verified, title, content, …

Phones and reviews join on **ASIN**. No accessory filtering or HF streaming required.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.entities import Smartphone
from app.scrapers.base import ScrapedPrice, ScrapedProduct, ScrapedReview
from app.scrapers.parsers import extract_model, parse_number
from app.scrapers.pipeline import store_price, store_reviews, upsert_product
from app.services.corpus_import import reset_corpus
from sqlalchemy.orm import Session

logger = get_logger(__name__)

ProgressCallback = Callable[[int, int, str], None]

KAGGLE_DATASET = "grikomsn/amazon-cell-phones-reviews"
SOURCE = "amazon_kaggle"

# Published CSV headers (lowercased in normalisation).
ITEM_ALIASES: dict[str, tuple[str, ...]] = {
    "asin": ("asin", "product_asin", "product id", "product_id"),
    "brand": ("brand",),
    "title": ("title", "product title", "product_title", "name"),
    "url": ("url", "product url", "product_url"),
    "image": ("image", "image url", "image_url"),
    "rating": ("rating", "average rating", "average_rating", "avg_rating"),
    "total_reviews": ("totalreviews", "total reviews", "total_reviews", "review_count"),
    "price": ("price",),
    "original_price": ("originalprice", "original price", "original_price", "list_price"),
}

REVIEW_ALIASES: dict[str, tuple[str, ...]] = {
    "asin": ("asin", "product_asin", "product id", "product_id"),
    "reviewer": ("reviewer", "name", "reviewer name", "reviewer_name", "user", "user_name"),
    "rating": ("rating", "stars", "score"),
    "review_date": ("date", "review date", "review_date", "timestamp"),
    "verified": ("verified", "verified purchase", "verified_purchase"),
    "title": ("title", "review title", "review_title"),
    "content": ("content", "body", "review content", "review_content", "text", "review"),
    "helpful_votes": ("helpfulvotes", "helpful votes", "helpful_votes", "helpful"),
}


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def _rename_columns(frame: pd.DataFrame, aliases: dict[str, tuple[str, ...]]) -> pd.DataFrame:
    lookup = {_norm_header(col): col for col in frame.columns}
    rename: dict[str, str] = {}
    for canonical, options in aliases.items():
        for option in options:
            key = _norm_header(option)
            if key in lookup:
                rename[lookup[key]] = canonical
                break
    out = frame.rename(columns=rename)
    missing = [c for c in aliases if c not in out.columns]
    if missing:
        raise ValueError(
            f"CSV is missing expected columns {missing}. Found: {list(frame.columns)}"
        )
    return out


def _find_csv(dataset_dir: Path, kind: str) -> Path:
    """Find ``*items*.csv`` or ``*reviews*.csv`` under the download folder."""
    kind = kind.lower()
    if kind == "items":
        matches = [p for p in dataset_dir.rglob("*.csv") if "items" in p.name.lower()]
    elif kind == "reviews":
        matches = [p for p in dataset_dir.rglob("*.csv") if "reviews" in p.name.lower()]
    else:
        matches = list(dataset_dir.rglob(f"*{kind}*.csv"))
    matches = sorted(set(matches), key=lambda p: len(p.name))
    if not matches:
        raise FileNotFoundError(
            f"No *{kind}*.csv under {dataset_dir}. Download the Kaggle dataset first."
        )
    return matches[0]


def download_kaggle_dataset() -> Path:
    """Download via kagglehub; requires Kaggle credentials on the machine."""
    try:
        import kagglehub
    except ImportError as exc:
        raise RuntimeError(
            "Install kagglehub: pip install kagglehub\n"
            "Then configure Kaggle API credentials (see https://www.kaggle.com/docs/api)."
        ) from exc

    path = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    logger.info("Kaggle dataset downloaded to %s", path)
    return path


def load_kaggle_frames(dataset_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    items_path = _find_csv(dataset_dir, "items")
    reviews_path = _find_csv(dataset_dir, "reviews")
    logger.info("Loading items from %s", items_path)
    logger.info("Loading reviews from %s", reviews_path)

    items = _rename_columns(pd.read_csv(items_path), ITEM_ALIASES)
    reviews = _rename_columns(pd.read_csv(reviews_path), REVIEW_ALIASES)
    return items, reviews


def _parse_date(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except (TypeError, ValueError):
        return None


def _parse_verified(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "verified"}:
        return True
    if text in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _item_row_to_product(row: pd.Series) -> ScrapedProduct:
    asin = str(row["asin"]).strip().upper()
    title = str(row["title"]).strip()
    brand = str(row["brand"]).strip() if pd.notna(row.get("brand")) else None
    if brand and brand.lower() in {"nan", "none", ""}:
        brand = None

    model = extract_model(title, brand or "", "")
    canonical = f"{brand} {model}".strip() if brand or model else title[:200]

    price_val = parse_number(str(row["price"])) if pd.notna(row.get("price")) else None
    list_val = (
        parse_number(str(row["original_price"]))
        if pd.notna(row.get("original_price"))
        else None
    )

    try:
        site_rating = float(row["rating"]) if pd.notna(row.get("rating")) else None
    except (TypeError, ValueError):
        site_rating = None
    try:
        site_rating_count = int(row["total_reviews"]) if pd.notna(row.get("total_reviews")) else None
    except (TypeError, ValueError):
        site_rating_count = None

    url = str(row["url"]).strip() if pd.notna(row.get("url")) else f"https://www.amazon.com/dp/{asin}"
    image = str(row["image"]).strip() if pd.notna(row.get("image")) else None

    return ScrapedProduct(
        source=SOURCE,
        source_product_id=asin,
        product_url=url,
        raw_title=title,
        brand=brand,
        model=model or None,
        canonical_name=canonical,
        image_url=image,
        site_rating=site_rating,
        site_rating_count=site_rating_count,
        specs_raw={
            "dataset": KAGGLE_DATASET,
            "original_price": str(row.get("original_price") or ""),
        },
        price=ScrapedPrice(price=price_val, list_price=list_val, currency="USD") if price_val else None,
    )


def _review_row_to_scraped(row: pd.Series, product_url: str | None) -> ScrapedReview | None:
    body = str(row.get("content") or "").strip()
    if not body:
        return None

    asin = str(row["asin"]).strip().upper()
    reviewer = str(row.get("reviewer") or "")[:64] or None
    title = str(row.get("title") or "").strip() or None

    try:
        rating = float(row["rating"]) if pd.notna(row.get("rating")) else None
    except (TypeError, ValueError):
        rating = None

    helpful = None
    if pd.notna(row.get("helpful_votes")):
        try:
            helpful = int(row["helpful_votes"])
        except (TypeError, ValueError):
            helpful = None

    stamp = str(row.get("review_date") or "")
    source_review_id = f"{asin}:{reviewer}:{stamp}"[:120]

    return ScrapedReview(
        body=body,
        source_review_id=source_review_id,
        source_url=product_url,
        title=title,
        rating=rating,
        review_date=_parse_date(row.get("review_date")),
        reviewer_name=reviewer,
        verified_purchase=_parse_verified(row.get("verified")),
        helpful_votes=helpful,
    )


def ingest_kaggle_cell_phones(
    db: Session,
    *,
    dataset_dir: Path | None = None,
    download: bool = True,
    replace: bool = True,
    max_phones: int = 0,
    max_reviews_per_phone: int = 0,
    min_total_reviews: int = 0,
    brand_filter: list[str] | None = None,
    settings: Settings | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Load Kaggle items + reviews into SQLite with Step 1 preprocessing on insert."""
    settings = settings or get_settings()

    def report(done: int, total: int, message: str) -> None:
        if progress is not None:
            progress(done, total, message)
        logger.info("[%s/%s] %s", done, total, message)

    if dataset_dir is None:
        if not download:
            raise ValueError("Pass --dataset-dir or enable download.")
        dataset_dir = download_kaggle_dataset()
    else:
        dataset_dir = Path(dataset_dir)

    items_df, reviews_df = load_kaggle_frames(dataset_dir)

    if brand_filter:
        wanted = {b.strip().lower() for b in brand_filter if b.strip()}
        items_df = items_df[
            items_df["brand"].astype(str).str.lower().isin(wanted)
        ]

    if min_total_reviews > 0:
        items_df = items_df[items_df["total_reviews"].fillna(0) >= min_total_reviews]

    items_df = items_df.sort_values("total_reviews", ascending=False, na_position="last")
    if max_phones > 0:
        items_df = items_df.head(max_phones)

    summary: dict[str, Any] = {
        "dataset": KAGGLE_DATASET,
        "dataset_dir": str(dataset_dir),
        "items_in_csv": int(len(items_df)),
        "reviews_in_csv": int(len(reviews_df)),
        "phones_upserted": 0,
        "prices_recorded": 0,
        "reviews_inserted": 0,
        "reviews_duplicate": 0,
        "reviews_excluded": 0,
        "phone_ids": [],
        "asins": [],
        "brands": sorted(items_df["brand"].dropna().astype(str).unique().tolist()),
    }

    if replace:
        report(0, 1, "Clearing existing corpus…")
        reset_corpus(db)
        db.commit()

    selected_asins = set(items_df["asin"].astype(str).str.upper())
    url_by_asin = {
        str(row["asin"]).strip().upper(): str(row.get("url") or "")
        for _, row in items_df.iterrows()
    }

    report(0, len(items_df), f"Importing {len(items_df)} phone(s)…")
    asin_to_id: dict[str, int] = {}

    for index, (_, row) in enumerate(items_df.iterrows(), start=1):
        product = _item_row_to_product(row)
        phone = upsert_product(db, product)
        if store_price(db, phone, product.price):
            summary["prices_recorded"] += 1
        asin_to_id[product.source_product_id] = phone.id
        summary["phones_upserted"] += 1
        summary["phone_ids"].append(phone.id)
        summary["asins"].append(product.source_product_id)
        if index % 25 == 0:
            db.commit()
            report(index, len(items_df), phone.display_name)

    db.commit()

    reviews_df = reviews_df[reviews_df["asin"].astype(str).str.upper().isin(selected_asins)]
    by_asin: dict[str, list[ScrapedReview]] = defaultdict(list)

    for _, row in reviews_df.iterrows():
        asin = str(row["asin"]).strip().upper()
        if asin not in asin_to_id:
            continue
        scraped = _review_row_to_scraped(row, url_by_asin.get(asin) or None)
        if scraped is None:
            continue
        bucket = by_asin[asin]
        if max_reviews_per_phone > 0 and len(bucket) >= max_reviews_per_phone:
            continue
        bucket.append(scraped)

    report(0, len(by_asin), f"Importing reviews for {len(by_asin)} phone(s)…")
    for index, (asin, scraped_list) in enumerate(by_asin.items(), start=1):
        phone = db.get(Smartphone, asin_to_id[asin])
        if phone is None:
            continue
        counts = store_reviews(db, phone, scraped_list, settings=settings)
        summary["reviews_inserted"] += counts["inserted"]
        summary["reviews_duplicate"] += counts["duplicates"]
        summary["reviews_excluded"] += counts["excluded"]
        if index % 25 == 0:
            db.commit()
            report(index, len(by_asin), f"{phone.display_name}: +{counts['inserted']}")

    db.commit()
    report(len(by_asin), len(by_asin), "Kaggle ingest finished")
    return summary
