import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.collectors import MarketCollectorError
from cards.collectors.markets import EbayMarketCollector
from cards.models import Card, Condition, MarketListing, MarketRegion, MarketSource
from cards.services.card_matching import match_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.market_search import build_ebay_search_query
from cards.services.price_calculator import calculate_price_groups
from cards.services.price_history import save_price_histories


class Command(BaseCommand):
    help = '환경변수로 지정한 Card 한 장의 eBay listing을 한 번만 수집하고 저장합니다.'

    def handle(self, *args, **options):
        card_source = os.environ.get('EBAY_IMPORT_CARD_SOURCE', '').strip()
        card_number = os.environ.get('EBAY_IMPORT_CARD_NUMBER', '').strip()
        card_set = os.environ.get('EBAY_IMPORT_CARD_SET', '').strip()
        if not card_source or not card_number or not card_set:
            self.stdout.write(
                self.style.WARNING('eBay import configuration is incomplete; skipping.')
            )
            return
        if card_source.casefold() == 'demo':
            self.stdout.write(self.style.WARNING('DEMO cards are not eligible; skipping.'))
            return

        raw_limit = os.environ.get('EBAY_IMPORT_LIMIT', '').strip() or '3'
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 0
        if not 1 <= limit <= 3:
            self.stdout.write(
                self.style.WARNING(
                    'eBay import limit must be an integer between 1 and 3; skipping.'
                )
            )
            return

        cards = Card.objects.filter(
            source=card_source,
            card_number=card_number,
            set_name=card_set,
        )
        card_count = cards.count()
        if card_count == 0:
            self.stdout.write(self.style.WARNING('eBay import card was not found; skipping.'))
            return
        if card_count > 1:
            self.stdout.write(self.style.WARNING('eBay import card is ambiguous; skipping.'))
            return
        card = cards.first()

        collector = EbayMarketCollector()
        if not collector.is_configured:
            self.stdout.write(
                self.style.WARNING('eBay credentials are not configured; skipping.')
            )
            return

        query = build_ebay_search_query(card)
        try:
            returned_items = collector.collect(query=query, limit=limit)
        except (MarketCollectorError, ValueError) as error:
            raise CommandError(str(error)) from error
        market_data_items = list(returned_items)[:limit]

        prepared_items = []
        skipped = 0
        unknown_condition = 0
        for market_data in market_data_items:
            if match_card(market_data.title, [card]) is None:
                skipped += 1
                continue
            condition_result = classify_condition(market_data.title, card_matched=True)
            unknown_condition += int(condition_result.condition == Condition.UNKNOWN)
            prepared_items.append((market_data, condition_result))

        created = 0
        updated = 0
        history_count = 0
        if prepared_items:
            with transaction.atomic():
                market_source, _ = MarketSource.objects.update_or_create(
                    code='EBAY',
                    defaults={
                        'name': 'eBay',
                        'base_url': 'https://www.ebay.com',
                        'market_region': MarketRegion.GLOBAL,
                        'is_active': True,
                    },
                )
                for market_data, condition_result in prepared_items:
                    save_result = save_market_listing(
                        market_data,
                        card,
                        market_source,
                        condition_result,
                    )
                    if save_result.created:
                        created += 1
                    else:
                        updated += 1

                calculations = calculate_price_groups(
                    MarketListing.objects.filter(card=card, is_active=True)
                )
                history_count = len(save_price_histories(calculations))

        self.stdout.write(self.style.SUCCESS('eBay one-time import completed.'))
        self.stdout.write(f'Card: {card.display_name} {card.card_number}')
        self.stdout.write(f'Query: {query}')
        self.stdout.write(f'Returned: {len(market_data_items)}')
        self.stdout.write(f'Created: {created}')
        self.stdout.write(f'Updated: {updated}')
        self.stdout.write(f'Skipped: {skipped}')
        self.stdout.write(f'Unknown condition: {unknown_condition}')
        self.stdout.write(f'Price histories calculated: {history_count}')
