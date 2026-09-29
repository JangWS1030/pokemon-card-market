from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.collectors import MarketCollectorError
from cards.collectors.card_data import PokemonKoreaCardCollector
from cards.models import Card


class Command(BaseCommand):
    help = '공개 Pokémon Korea 상세 URL에서 특정 Card의 공식 이미지 URL만 확인/저장합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--card-id', type=int, required=True)
        parser.add_argument('--url', required=True)
        parser.add_argument('--check-image', action='store_true')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--write', action='store_true')

    def handle(self, *args, **options):
        cards = Card.objects.filter(pk=options['card_id'])
        if cards.count() != 1:
            raise CommandError('정확히 한 개의 Card를 선택해야 합니다.')
        card = cards.get()
        if card.source == 'DEMO':
            raise CommandError('DEMO Card에는 공개 이미지를 저장하지 않습니다.')

        collector = PokemonKoreaCardCollector()
        try:
            data = collector.collect_url(
                options['url'],
                check_image=options['check_image'],
            )
        except (MarketCollectorError, ValueError) as error:
            raise CommandError(str(error)) from error
        if not collector.matches_card(card, data):
            raise CommandError('공개 페이지의 카드 정보가 선택한 Card와 일치하지 않습니다.')

        if options['write']:
            with transaction.atomic():
                Card.objects.filter(pk=card.pk).update(image_url=data.image_url)

        self.stdout.write(self.style.SUCCESS('Pokemon Korea image lookup completed.'))
        self.stdout.write(f'Card: {card.display_name_with_number}')
        self.stdout.write('Source: POKEMON_KOREA')
        self.stdout.write('Matched items: 1')
        self.stdout.write('Image available: yes')
        self.stdout.write(f'Requests: {collector.request_count}')
        self.stdout.write(f"Mode: {'write' if options['write'] else 'dry-run'}")
