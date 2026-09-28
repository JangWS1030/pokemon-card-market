from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cards.collectors import MarketCollectorError
from cards.collectors.markets import EbayMarketCollector
from cards.models import Card, MarketListing, MarketRegion, MarketSource
from cards.services.card_matching import is_listing_relevant_to_card, match_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.market_search import build_ebay_search_query
from cards.services.price_calculator import calculate_price_groups
from cards.services.price_history import save_price_histories


class Command(BaseCommand):
    help = 'eBay 해외 현재 매물을 수동으로 수집하고 통화별 참고가를 계산합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--card-id', type=int, help='특정 Card ID 한 개만 갱신합니다.')
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='처리할 카드 수입니다. 기본 5개, 최대 20개입니다.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='eBay API는 호출하지만 DB에는 저장하지 않습니다.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 20:
            raise CommandError('--limit은 1~20 사이여야 합니다.')

        collector = EbayMarketCollector()
        if not collector.is_configured:
            self.stdout.write(
                self.style.WARNING(
                    'eBay 개발자 인증정보가 없습니다. '
                    'EBAY_CLIENT_ID와 EBAY_CLIENT_SECRET을 설정해 주세요.'
                )
            )
            return

        cards = self._get_cards(options['card_id'], limit)
        if not cards:
            self.stdout.write(self.style.WARNING('갱신할 카드가 없습니다.'))
            return

        dry_run = options['dry_run']
        run_timestamp = timezone.now()
        source = None
        totals = {
            'cards': 0,
            'fetched': 0,
            'matched': 0,
            'created': 0,
            'updated': 0,
            'unmatched': 0,
            'histories': 0,
            'errors': 0,
        }

        for card in cards:
            card_matched_count = 0
            query = build_ebay_search_query(card)
            self.stdout.write(f'Card {card.pk}: {query}')

            try:
                market_data_items = collector.collect(query, limit=20)
            except (MarketCollectorError, ValueError) as error:
                totals['errors'] += 1
                self.stderr.write(self.style.ERROR(f'Card {card.pk} 수집 실패: {error}'))
                continue

            totals['cards'] += 1
            totals['fetched'] += len(market_data_items)
            if not dry_run and source is None:
                source, _ = MarketSource.objects.update_or_create(
                    code='EBAY',
                    defaults={
                        'name': 'eBay',
                        'base_url': 'https://www.ebay.com',
                        'market_region': MarketRegion.GLOBAL,
                        'is_active': True,
                    },
                )

            run_listings = []
            for market_data in market_data_items:
                matched_card = match_card(market_data.title, Card.objects.all())
                if (
                    matched_card is None
                    or matched_card.pk != card.pk
                    or not is_listing_relevant_to_card(card, market_data.title)
                ):
                    totals['unmatched'] += 1
                    continue

                totals['matched'] += 1
                card_matched_count += 1
                condition_result = classify_condition(market_data.title, card_matched=True)

                if dry_run:
                    run_listings.append(
                        SimpleNamespace(
                            card_id=card.pk,
                            condition=condition_result.condition,
                            grading_score=condition_result.grading_score,
                            currency=market_data.currency,
                            price=market_data.price,
                            is_active=True,
                        )
                    )
                    continue

                save_result = save_market_listing(
                    market_data,
                    card,
                    source,
                    condition_result,
                )
                totals['created' if save_result.created else 'updated'] += 1

            if not card_matched_count:
                continue

            if dry_run:
                calculation_listings = run_listings
            else:
                calculation_listings = MarketListing.objects.filter(
                    card=card,
                    is_active=True,
                )

            calculations = calculate_price_groups(calculation_listings)
            if dry_run:
                totals['histories'] += len(calculations)
            else:
                totals['histories'] += len(
                    save_price_histories(calculations, calculated_at=run_timestamp)
                )

        mode = 'DRY RUN (DB 저장 없음)' if dry_run else '저장 완료'
        self.stdout.write(self.style.SUCCESS(f'[{mode}]'))
        self.stdout.write(
            '처리 카드: {cards}, 수집: {fetched}, 매칭: {matched}, '
            '미매칭: {unmatched}, Listing 생성: {created}, Listing 갱신: {updated}, '
            '참고가 기록: {histories}, 오류: {errors}'.format(**totals)
        )

    @staticmethod
    def _get_cards(card_id, limit):
        if card_id is not None:
            try:
                return [Card.objects.get(pk=card_id)]
            except Card.DoesNotExist as error:
                raise CommandError(f'Card ID {card_id}를 찾을 수 없습니다.') from error
        return list(Card.objects.order_by('pk')[:limit])
