from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cards.models import (
    Card,
    Condition,
    GradingCompany,
    MarketListing,
    MarketRegion,
    MarketSource,
    PriceHistory,
)


DEMO_CARDS = (
    ('Demo Fire Card', '001/012', 'Demo Rare'),
    ('Demo Water Card', '002/012', 'Demo Common'),
    ('Demo Leaf Card', '003/012', 'Demo Uncommon'),
    ('Demo Spark Card', '004/012', 'Demo Rare'),
    ('Demo Moon Card', '005/012', 'Demo Common'),
    ('Demo Stone Card', '006/012', 'Demo Uncommon'),
    ('Demo Wind Card', '007/012', 'Demo Rare'),
    ('Demo Frost Card', '008/012', 'Demo Common'),
    ('Demo Light Card', '009/012', 'Demo Uncommon'),
    ('Demo Shadow Card', '010/012', 'Demo Rare'),
    ('Demo Metal Card', '011/012', 'Demo Common'),
    ('Demo Star Card', '012/012', 'Demo Special'),
)


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    cards: int
    listings: int
    histories: int


@dataclass(frozen=True, slots=True)
class DemoClearResult:
    cards: int
    listings: int
    histories: int
    sources: int


@transaction.atomic
def seed_demo_data():
    source, _ = MarketSource.objects.update_or_create(
        code='DEMO',
        defaults={
            'name': 'Demo Market',
            'base_url': 'https://example.com/demo',
            'market_region': MarketRegion.GLOBAL,
            'is_active': True,
        },
    )

    cards = []
    for index, (name, number, rarity) in enumerate(DEMO_CARDS, start=1):
        card, _ = Card.objects.update_or_create(
            source='DEMO',
            external_id=f'demo-card-{index:03d}',
            defaults={
                'name_ko': '',
                'name_en': name,
                'set_name': 'Demo Starter Set',
                'card_number': number,
                'rarity': rarity,
                'language': 'DEMO',
                'image_url': None,
            },
        )
        cards.append(card)

    listing_specs = (
        (0, 'raw-usd', Condition.RAW, None, None, '12.00', 'USD'),
        (0, 'psa9-usd', Condition.PSA, GradingCompany.PSA, '9.0', '24.00', 'USD'),
        (0, 'psa10-usd', Condition.PSA, GradingCompany.PSA, '10.0', '40.00', 'USD'),
        (0, 'raw-krw', Condition.RAW, None, None, '15000', 'KRW'),
        (1, 'bgs95-usd', Condition.BGS, GradingCompany.BGS, '9.5', '31.50', 'USD'),
        (1, 'raw-usd', Condition.RAW, None, None, '8.75', 'USD'),
        (2, 'cgc10-usd', Condition.CGC, GradingCompany.CGC, '10.0', '36.00', 'USD'),
        (3, 'sealed-usd', Condition.SEALED, None, None, '18.00', 'USD'),
    )
    now = timezone.now()
    listing_ids = []
    for card_index, suffix, condition, company, score, price, currency in listing_specs:
        external_id = f'demo-listing-{card_index + 1:03d}-{suffix}'
        listing_ids.append(external_id)
        MarketListing.objects.update_or_create(
            market_source=source,
            external_id=external_id,
            defaults={
                'card': cards[card_index],
                'title': f'DEMO 테스트 상품 - {cards[card_index].display_name} - {suffix}',
                'price': Decimal(price),
                'currency': currency,
                'url': f'https://example.com/demo/{external_id}',
                'condition': condition,
                'grading_company': company,
                'grading_score': Decimal(score) if score else None,
                'is_active': True,
                'collected_at': now,
            },
        )
    MarketListing.objects.filter(market_source=source).exclude(
        external_id__in=listing_ids
    ).delete()

    # 재실행 시 같은 그래프 시점을 누적하지 않고 DEMO 이력만 다시 만든다.
    PriceHistory.objects.filter(card__source='DEMO').delete()
    history_specs = (
        (cards[0], Condition.RAW, None, 'USD', Decimal('10.00')),
        (cards[0], Condition.PSA, Decimal('10.0'), 'USD', Decimal('36.00')),
        (cards[0], Condition.RAW, None, 'KRW', Decimal('14000')),
        (cards[1], Condition.BGS, Decimal('9.5'), 'USD', Decimal('28.00')),
    )
    histories = []
    for card, condition, score, currency, base_price in history_specs:
        for step, days_ago in enumerate((30, 24, 18, 12, 6, 0)):
            median = base_price + Decimal(step)
            histories.append(
                PriceHistory(
                    card=card,
                    condition=condition,
                    grading_score=score,
                    currency=currency,
                    calculated_at=now - timedelta(days=days_ago),
                    median_price=median,
                    average_price=median + Decimal('0.50'),
                    min_price=median - Decimal('1.00'),
                    max_price=median + Decimal('1.00'),
                    listing_count=5,
                )
            )
    PriceHistory.objects.bulk_create(histories)

    return DemoSeedResult(
        cards=Card.objects.filter(source='DEMO').count(),
        listings=MarketListing.objects.filter(market_source=source).count(),
        histories=PriceHistory.objects.filter(card__source='DEMO').count(),
    )


@transaction.atomic
def clear_demo_data():
    demo_cards = Card.objects.filter(source='DEMO')
    history_count, _ = PriceHistory.objects.filter(card__in=demo_cards).delete()
    listing_count, _ = MarketListing.objects.filter(
        Q(card__in=demo_cards) | Q(market_source__code='DEMO')
    ).delete()
    card_count, _ = demo_cards.delete()
    source_count, _ = MarketSource.objects.filter(code='DEMO').delete()
    return DemoClearResult(card_count, listing_count, history_count, source_count)
