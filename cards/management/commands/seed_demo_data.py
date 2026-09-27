from django.core.management.base import BaseCommand

from cards.services.demo_data import seed_demo_data


class Command(BaseCommand):
    help = '개발 UI 확인용 DEMO Card와 가격 데이터를 생성합니다.'

    def handle(self, *args, **options):
        result = seed_demo_data()
        self.stdout.write(
            self.style.SUCCESS(
                'DEMO 데이터 준비 완료 '
                f'(Card {result.cards}, Listing {result.listings}, PriceHistory {result.histories})'
            )
        )
        self.stdout.write(self.style.WARNING('모든 DEMO 데이터는 테스트용이며 실제 시세가 아닙니다.'))
