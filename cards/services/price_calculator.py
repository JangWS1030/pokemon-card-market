from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean, median, quantiles


MONEY_QUANTUM = Decimal('0.01')


@dataclass(frozen=True, slots=True)
class OutlierResult:
    prices: tuple[Decimal, ...]
    removed_count: int
    used_fallback: bool


@dataclass(frozen=True, slots=True)
class PriceCalculation:
    card_id: int
    listing_type: str
    condition: str
    grading_score: Decimal | None
    currency: str
    median_price: Decimal
    average_price: Decimal
    min_price: Decimal
    max_price: Decimal
    listing_count: int
    outliers_removed: int
    used_fallback: bool


def calculate_price_groups(listings):
    groups = defaultdict(list)

    for listing in listings:
        price = Decimal(str(listing.price))
        if not listing.is_active or price <= 0 or listing.condition == 'UNKNOWN':
            continue
        currency = listing.currency.upper()
        listing_type = getattr(listing, 'listing_type', 'CURRENT_LISTING')
        key = (
            listing.card_id,
            listing_type,
            listing.condition,
            listing.grading_score,
            currency,
        )
        groups[key].append(price)

    calculations = []
    for (card_id, listing_type, condition, grading_score, currency), prices in groups.items():
        outlier_result = remove_iqr_outliers(prices)
        final_prices = outlier_result.prices
        calculations.append(
            PriceCalculation(
                card_id=card_id,
                listing_type=listing_type,
                condition=condition,
                grading_score=grading_score,
                currency=currency,
                median_price=_money(median(final_prices)),
                average_price=_money(mean(final_prices)),
                min_price=_money(min(final_prices)),
                max_price=_money(max(final_prices)),
                listing_count=len(final_prices),
                outliers_removed=outlier_result.removed_count,
                used_fallback=outlier_result.used_fallback,
            )
        )
    return calculations


def remove_iqr_outliers(prices):
    original = tuple(sorted(Decimal(str(price)) for price in prices))
    if len(original) < 5:
        return OutlierResult(original, 0, False)

    q1, _, q3 = quantiles(original, n=4, method='inclusive')
    iqr = q3 - q1
    lower_bound = q1 - Decimal('1.5') * iqr
    upper_bound = q3 + Decimal('1.5') * iqr
    filtered = tuple(price for price in original if lower_bound <= price <= upper_bound)
    removed_count = len(original) - len(filtered)

    if len(filtered) < 3:
        return OutlierResult(original, 0, True)
    return OutlierResult(filtered, removed_count, False)


def _money(value):
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
