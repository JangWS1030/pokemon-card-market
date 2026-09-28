import os

from django.core.management.base import BaseCommand, CommandError

from cards.collectors import MarketCollectorError
from cards.collectors.markets import EbayMarketCollector


class Command(BaseCommand):
    help = 'DB 저장 없이 eBay Production OAuth와 Browse 검색 연결을 한 번 확인합니다.'

    def handle(self, *args, **options):
        query = os.environ.get('EBAY_TEST_QUERY', '').strip()
        if not query:
            self.stdout.write(
                self.style.WARNING('eBay test query is not configured; skipping.')
            )
            return

        collector = EbayMarketCollector()
        if not collector.is_configured:
            self.stdout.write(
                self.style.WARNING('eBay credentials are not configured; skipping.')
            )
            return

        try:
            results = collector.collect(query=query, limit=3)
        except (MarketCollectorError, ValueError) as error:
            raise CommandError(str(error)) from error

        self.stdout.write('eBay production connection check completed.')
        self.stdout.write(f'Marketplace: {collector.MARKETPLACE_ID}')
        self.stdout.write('OAuth: OK')
        self.stdout.write('Browse API: OK')
        self.stdout.write(f'Results: {len(results)}')
