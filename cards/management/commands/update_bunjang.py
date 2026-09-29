from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.collectors import MarketCollectorError
from cards.collectors.markets import BunjangMarketCollector
from cards.models import Card, Condition, MarketListing, MarketRegion, MarketSource
from cards.services.card_matching import is_listing_relevant_to_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.market_search import build_bunjang_search_query
from cards.services.price_calculator import calculate_price_groups
from cards.services.price_history import save_price_histories


class Command(BaseCommand):
    help = '공식 Bunjang Open API에서 명시적인 Card 한 장의 현재 매물을 소량 조회합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--card-id', type=int)
        parser.add_argument('--limit', type=int, default=3)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--write', action='store_true')

    def handle(self, *args, **options):
        if options['card_id'] is None:
            self.stdout.write('Bunjang: SKIPPED (explicit --card-id is required)')
            return
        if not 1 <= options['limit'] <= 5:
            raise CommandError('Bunjang limit must be between 1 and 5.')

        cards = Card.objects.filter(pk=options['card_id'])
        if cards.count() != 1:
            raise CommandError('정확히 한 개의 Card를 선택해야 합니다.')
        card = cards.get()
        if card.source == 'DEMO':
            raise CommandError('DEMO Card에는 Bunjang 매물을 저장하지 않습니다.')

        collector = BunjangMarketCollector()
        if not collector.is_configured:
            self.stdout.write('Bunjang: SKIPPED (Open API credentials are not configured)')
            return

        query = build_bunjang_search_query(card)
        try:
            candidates = collector.collect(query, limit=options['limit'])
        except (MarketCollectorError, ValueError) as error:
            raise CommandError(str(error)) from error

        prepared = []
        skipped = 0
        for market_data in candidates:
            if not is_listing_relevant_to_card(card, market_data.title):
                skipped += 1
                continue
            condition = classify_condition(market_data.title, card_matched=True)
            if condition.condition in (Condition.UNKNOWN, Condition.SEALED):
                skipped += 1
                continue
            prepared.append((market_data, condition))

        created = updated = histories = 0
        if options['write'] and prepared:
            with transaction.atomic():
                source, _ = MarketSource.objects.update_or_create(
                    code='BUNJANG',
                    defaults={
                        'name': '번개장터',
                        'base_url': 'https://m.bunjang.co.kr',
                        'market_region': MarketRegion.KR,
                        'is_active': True,
                    },
                )
                for market_data, condition in prepared:
                    result = save_market_listing(market_data, card, source, condition)
                    created += int(result.created)
                    updated += int(not result.created)
                calculations = calculate_price_groups(
                    MarketListing.objects.filter(card=card, is_active=True)
                )
                histories = len(save_price_histories(calculations))

        self.stdout.write('Bunjang collection completed.')
        self.stdout.write('Source: BUNJANG')
        self.stdout.write(f'Card: {card.display_name_with_number}')
        self.stdout.write(f'Requests: {collector.request_count}')
        self.stdout.write(f'Candidates: {len(candidates)}')
        self.stdout.write(f'Matched: {len(prepared)}')
        self.stdout.write(f'Skipped: {skipped}')
        self.stdout.write(f'CURRENT_LISTING: {len(prepared)}')
        self.stdout.write(f"DB writes: {created + updated if options['write'] else 0}")
        self.stdout.write(f'Price histories: {histories}')
        self.stdout.write(f"Mode: {'write' if options['write'] else 'dry-run'}")
