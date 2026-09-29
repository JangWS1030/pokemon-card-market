from dataclasses import dataclass

from cards.collectors import MarketData
from cards.models import MarketListing

from .condition_classifier import ConditionResult


@dataclass(frozen=True, slots=True)
class ListingSaveResult:
    listing: MarketListing
    created: bool


def save_market_listing(market_data, card, market_source, condition_result):
    if not isinstance(market_data, MarketData):
        raise TypeError('market_data는 MarketData 형식이어야 합니다.')
    if not isinstance(condition_result, ConditionResult):
        raise TypeError('condition_result는 ConditionResult 형식이어야 합니다.')

    listing, created = MarketListing.objects.update_or_create(
        market_source=market_source,
        external_id=market_data.external_id,
        defaults={
            'card': card,
            'title': market_data.title,
            'price': market_data.price,
            'currency': market_data.currency,
            'url': market_data.url,
            'image_url': market_data.image_url,
            'listing_type': market_data.listing_type,
            'condition': condition_result.condition,
            'grading_company': condition_result.grading_company,
            'grading_score': condition_result.grading_score,
            'is_active': True,
            'occurred_at': market_data.occurred_at,
            'collected_at': market_data.collected_at,
        },
    )
    return ListingSaveResult(listing=listing, created=created)
