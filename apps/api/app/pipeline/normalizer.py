import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from app.llm.schemas import ExtractedFact


@dataclass(frozen=True)
class NormalizedValue:
    value_kind: str
    numeric_value: float | None
    normalized_value: str | None
    unit_canonical: str | None
    canonical_numeric_value: float | None


@dataclass(frozen=True)
class NormalizedPeriod:
    label: str | None
    start: datetime | None
    end: datetime | None


def canonical_slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold())).strip("_")


def canonical_subject(value: str) -> str:
    slug = canonical_slug(value)
    return re.sub(r"_(?:private_)?(?:limited|ltd)$", "", slug)


def canonical_predicate(candidate: ExtractedFact) -> str:
    supplied = candidate.predicate_canonical.casefold().strip()
    supplied = re.sub(r"[^a-z0-9._]+", "_", supplied)
    if supplied and "." in supplied:
        return supplied
    return f"semantic.{canonical_slug(candidate.predicate)}"


def _number(value: str) -> float | None:
    match = re.search(r"[-+]?\(?\s*(\d[\d,]*(?:\.\d+)?)\s*\)?", value)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    stripped = value.strip()
    if stripped.startswith("(") and ")" in stripped:
        number = -number
    return number


def normalize_value(raw_value: str, raw_unit: str | None) -> NormalizedValue:
    combined = f"{raw_value} {raw_unit or ''}".casefold()
    numeric = _number(raw_value)
    if numeric is None:
        return NormalizedValue("STRING", None, raw_value.strip(), None, None)

    is_money = any(token in combined for token in ("₹", "inr", "rs.", "rs ", "rupee"))
    is_money = is_money or "crore" in combined or bool(re.search(r"\bcr\b", combined))
    is_percent = "%" in combined or "per cent" in combined or "percent" in combined
    multiplier = 1.0
    if re.search(r"\b(bn|billion)\b", combined):
        multiplier = 1_000_000_000
    elif re.search(r"\b(mn|million)\b", combined):
        multiplier = 1_000_000
    elif re.search(r"\b(k|thousand)\b", combined):
        multiplier = 1_000

    if is_percent:
        return NormalizedValue("NUMBER", numeric, str(numeric), "percent", numeric)
    if is_money:
        if "crore" in combined or re.search(r"\bcr\b", combined):
            crore_value = numeric
        else:
            crore_value = numeric * multiplier / 10_000_000
        return NormalizedValue("NUMBER", numeric, str(crore_value), "INR crore", crore_value)

    if any(token in combined for token in ("ton", "shipment", "parcel", "customer")):
        count = numeric * multiplier
        unit = "tonnes" if "ton" in combined else "count"
        return NormalizedValue("NUMBER", numeric, str(count), unit, count)

    return NormalizedValue(
        "NUMBER", numeric, str(numeric * multiplier), raw_unit, numeric * multiplier
    )


def normalize_period(raw_period: str | None) -> NormalizedPeriod:
    if not raw_period:
        return NormalizedPeriod(None, None, None)
    value = raw_period.strip()
    fy = re.search(r"\bFY\s*(?:20)?(\d{2})(?:\s*[/\-]\s*(\d{2}))?\b", value, re.I)
    if not fy:
        year_pair = re.search(r"\b(20\d{2})\s*[/\-]\s*(\d{2})\b", value)
        if year_pair:
            end_year = int(year_pair.group(1)[:2] + year_pair.group(2))
        else:
            return NormalizedPeriod(value, None, None)
    else:
        end_year = 2000 + int(fy.group(2) or fy.group(1))

    label = f"FY{end_year - 1}/{str(end_year)[-2:]}"
    quarter = re.search(r"\bQ([1-4])\b", value, re.I)
    if quarter:
        q = int(quarter.group(1))
        start_month = {1: 4, 2: 7, 3: 10, 4: 1}[q]
        start_year = end_year - 1 if q < 4 else end_year
        end_month = {1: 6, 2: 9, 3: 12, 4: 3}[q]
        end_day = {1: 30, 2: 30, 3: 31, 4: 31}[q]
        end_year_for_quarter = start_year
        label = f"Q{q} {label}"
        return NormalizedPeriod(
            label,
            datetime(start_year, start_month, 1, tzinfo=UTC),
            datetime(end_year_for_quarter, end_month, end_day, tzinfo=UTC),
        )
    return NormalizedPeriod(
        label,
        datetime(end_year - 1, 4, 1, tzinfo=UTC),
        datetime(end_year, 3, 31, tzinfo=UTC),
    )
