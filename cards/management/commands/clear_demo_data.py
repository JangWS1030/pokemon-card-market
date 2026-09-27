from django.core.management.base import BaseCommand

from cards.services.demo_data import clear_demo_data


class Command(BaseCommand):
    help = 'source=DEMO인 개발 데이터만 안전하게 삭제합니다.'

    def handle(self, *args, **options):
        result = clear_demo_data()
        self.stdout.write(
            self.style.SUCCESS(
                'DEMO 데이터 삭제 완료 '
                f'(Card {result.cards}, Listing {result.listings}, '
                f'PriceHistory {result.histories}, MarketSource {result.sources})'
            )
        )
