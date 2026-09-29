from datetime import timedelta

from django.utils import timezone

from cards.models import PriceHistory


DUPLICATE_WINDOW = timedelta(minutes=5)


def save_price_histories(calculations, calculated_at=None):
    calculated_at = calculated_at or timezone.now()
    histories = []

    for calculation in calculations:
        values = {
            'card_id': calculation.card_id,
            'listing_type': calculation.listing_type,
            'condition': calculation.condition,
            'grading_score': calculation.grading_score,
            'currency': calculation.currency,
            'median_price': calculation.median_price,
            'average_price': calculation.average_price,
            'min_price': calculation.min_price,
            'max_price': calculation.max_price,
            'listing_count': calculation.listing_count,
        }
        duplicate = PriceHistory.objects.filter(
            **values,
            calculated_at__gte=calculated_at - DUPLICATE_WINDOW,
            calculated_at__lte=calculated_at,
        ).order_by('-calculated_at').first()
        if duplicate:
            histories.append(duplicate)
            continue
        histories.append(
            PriceHistory.objects.create(calculated_at=calculated_at, **values)
        )
    return histories
