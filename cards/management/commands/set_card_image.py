from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.collectors import MarketCollectorError
from cards.collectors.card_data.pokemon_korea import (
    OFFICIAL_IMAGE_HOSTS,
    validate_official_image_url,
)
from cards.collectors.public_http import PublicHttpClient
from cards.models import Card


class Command(BaseCommand):
    help = '특정 Card에 검증된 Pokemon Korea 공식 이미지 URL reference만 설정합니다.'

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
        if options['write'] and card.source == 'DEMO':
            raise CommandError('DEMO Card의 이미지는 실제 모드에서 변경할 수 없습니다.')

        try:
            image_url = validate_official_image_url(options['url'])
        except MarketCollectorError as error:
            raise CommandError(str(error)) from error

        request_count = 0
        if options['check_image']:
            client = PublicHttpClient(OFFICIAL_IMAGE_HOSTS)
            try:
                client.head_image(image_url)
            except MarketCollectorError as error:
                raise CommandError(
                    f'공식 이미지 URL 확인에 실패하여 저장하지 않았습니다: {error}'
                ) from error
            request_count = client.request_count

        if options['write']:
            with transaction.atomic():
                Card.objects.filter(pk=card.pk).update(image_url=image_url)

        self.stdout.write('Card image URL validation completed.')
        self.stdout.write(f'Card: {card.display_name_with_number}')
        self.stdout.write('Image source: POKEMON_KOREA (manual official URL)')
        self.stdout.write(f"Current image URL: {card.image_url or '(empty)'}")
        self.stdout.write(f'New image URL: {image_url}')
        self.stdout.write(f'Image check requests: {request_count}')
        self.stdout.write(f'DB writes: {1 if options["write"] else 0}')
        self.stdout.write(f"Mode: {'write' if options['write'] else 'dry-run'}")
