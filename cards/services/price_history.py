from django.utils import timezone

from cards.models import PriceHistory


def save_price_histories(calculations, calculated_at=None):
    calculated_at = calculated_at or timezone.now()
    histories = []

    for calculation in calculations:
        histories.append(
            PriceHistory.objects.create(
                card_id=calculation.card_id,
                condition=calculation.condition,
                grading_score=calculation.grading_score,
                currency=calculation.currency,
                calculated_at=calculated_at,
                median_price=calculation.median_price,
                average_price=calculation.average_price,
                min_price=calculation.min_price,
                max_price=calculation.max_price,
                listing_count=calculation.listing_count,
            )
        )
    return histories
