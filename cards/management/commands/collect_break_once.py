from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.collectors import MarketCollectorError
from cards.collectors.markets import BreakMarketCollector
from cards.models import Card, Condition, MarketListing, MarketRegion, MarketSource
from cards.services.card_matching import is_listing_relevant_to_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.price_calculator import calculate_price_groups
from cards.services.price_history import save_price_histories


class Command(BaseCommand):
    help = '명시적으로 제공한 BREAK 공개 상품 URL 하나를 확인/저장합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--card-id', type=int, required=True)
        parser.add_argument('--url', required=True)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--write', action='store_true')

    def handle(self, *args, **options):
        cards = Card.objects.filter(pk=options['card_id'])
        if cards.count() != 1:
            raise CommandError('정확히 한 개의 Card를 선택해야 합니다.')
        card = cards.get()
        if card.source == 'DEMO':
            raise CommandError('DEMO Card에는 공개 매물을 저장하지 않습니다.')

        collector = BreakMarketCollector()
        try:
            market_data = collector.collect_url(options['url'])
        except (MarketCollectorError, ValueError) as error:
            raise CommandError(str(error)) from error
        if not is_listing_relevant_to_card(card, market_data.title):
            raise CommandError('BREAK 상품이 선택한 Card와 안전하게 매칭되지 않습니다.')
        condition = classify_condition(market_data.title, card_matched=True)
        if condition.condition in (Condition.UNKNOWN, Condition.SEALED):
            raise CommandError('단일 카드 가격으로 안전하게 분류할 수 없는 상품입니다.')

        created = updated = histories = 0
        if options['write']:
            with transaction.atomic():
                source, _ = MarketSource.objects.update_or_create(
                    code='BREAK',
                    defaults={
                        'name': 'BREAK',
                        'base_url': 'https://app.break.market',
                        'market_region': MarketRegion.KR,
                        'is_active': True,
                    },
                )
                result = save_market_listing(market_data, card, source, condition)
                created = int(result.created)
                updated = int(not result.created)
                calculations = calculate_price_groups(
                    MarketListing.objects.filter(card=card, is_active=True)
                )
                histories = len(save_price_histories(calculations))

        self.stdout.write(self.style.SUCCESS('BREAK one-time collection completed.'))
        self.stdout.write(f'Card: {card.display_name_with_number}')
        self.stdout.write('Source: BREAK')
        self.stdout.write('Matched items: 1')
        self.stdout.write(f'Price: {market_data.price:.0f} KRW')
        self.stdout.write(f'Listing type: {market_data.listing_type}')
        self.stdout.write(f"Image available: {'yes' if market_data.image_url else 'no'}")
        self.stdout.write(f'Requests: {collector.request_count}')
        self.stdout.write(f"Mode: {'write' if options['write'] else 'dry-run'}")
        self.stdout.write(f'Created: {created}; Updated: {updated}; Price histories: {histories}')
