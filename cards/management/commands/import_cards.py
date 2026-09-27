from django.core.management.base import BaseCommand, CommandError

from cards.collectors.card_data import JustTCGCardCollector, JustTCGError
from cards.services.card_importer import import_cards


class Command(BaseCommand):
    help = '확정된 외부 데이터 출처에서 카드 기본정보를 가져옵니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            choices=('justtcg',),
            help='카드 기본정보 출처입니다.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='한 번에 요청할 Card 수입니다. 기본 5개, 최대 20개입니다.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='실제 API 응답을 검증하지만 DB에는 저장하지 않습니다.',
        )
        parser.add_argument(
            '--query',
            help='공식 q 파라미터로 검색 범위를 좁힙니다.',
        )
        parser.add_argument('--set', dest='set_id', help='공식 set ID로 범위를 좁힙니다.')
        parser.add_argument('--number', help='공식 number 파라미터로 카드번호를 지정합니다.')
        parser.add_argument(
            '--list-sets',
            action='store_true',
            help='Pokemon set 목록을 한 번 요청하고 저장 없이 출력합니다.',
        )

    def handle(self, *args, **options):
        if not options['source']:
            self.stdout.write(
                self.style.WARNING('사용 가능한 카드 데이터 Collector가 아직 설정되지 않았습니다.')
            )
            return

        limit = options['limit']
        if not 1 <= limit <= 20:
            raise CommandError('--limit은 1~20 사이여야 합니다.')

        collector = JustTCGCardCollector()
        try:
            if options['list_sets']:
                sets = collector.collect_sets(query=options['query'])
                self.stdout.write(f'이번 실행 API 요청 횟수: {collector.last_report.request_count}')
                self.stdout.write(f'Pokemon set 수: {len(sets)}')
                for item in sets:
                    self.stdout.write(
                        f'- {item["id"]}: {item["name"]}'
                        + (f' ({item["release_date"]})' if item['release_date'] else '')
                    )
                return
            cards = collector.collect(
                limit=limit,
                query=options['query'],
                set_id=options['set_id'],
                number=options['number'],
            )
        except (JustTCGError, ValueError) as error:
            raise CommandError(str(error)) from error

        self._write_report(collector.last_report)
        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[DRY RUN] 저장 가능한 Korean variant Card: {len(cards)}, DB 저장 없음'
                )
            )
            return

        result = import_cards(cards)
        self.stdout.write(
            self.style.SUCCESS(
                'JustTCG import 완료: '
                f'생성 {result.created}, 갱신 {result.updated}, '
                f'건너뜀 {result.skipped}, 오류 {result.errors}'
            )
        )
        for message in result.messages:
            self.stdout.write(self.style.WARNING(message))

    def _write_report(self, report):
        self.stdout.write('JustTCG stable v1 응답 요약')
        self.stdout.write(f'- API 요청 횟수: {report.request_count}')
        self.stdout.write(f'- 반환 Card 수: {report.returned_cards}')
        self.stdout.write(f'- Korean variant Card 수: {report.korean_variant_cards}')
        self.stdout.write(f'- Korean variant 없는 Card 수: {report.without_korean_variant}')
        self.stdout.write(f'- 실제 한국어 이름 수: {report.korean_name_cards}')
        self.stdout.write(f'- 영문 이름만 제공된 수: {report.english_name_only_cards}')
        self.stdout.write(f'- image URL 제공 수: {report.image_url_cards}')
        self.stdout.write(f'- image URL 없는 수: {report.without_image_url}')
        self.stdout.write(
            '- pagination: total={total}, limit={limit}, offset={offset}, hasMore={has_more}'.format(
                total=report.meta.get('total'),
                limit=report.meta.get('limit'),
                offset=report.meta.get('offset'),
                has_more=report.meta.get('hasMore'),
            )
        )
        self.stdout.write(f'- _metadata 필드: {", ".join(report.metadata_keys) or "없음"}')

        for index, card in enumerate(report.card_summaries, start=1):
            self.stdout.write(
                f'[{index}] uuid={card["uuid"]}, name={card["name"]}, '
                f'game={card["game"]}, set={card["set"]}, '
                f'set_name={card["set_name"]}, number={card["number"]}, '
                f'rarity={card["rarity"]}, variants={card["variant_count"]}, '
                f'korean_variant={bool(card["variant_count"])}, '
                f'languages={card["variant_languages"]}, '
                f'image_fields={card["image_fields"]}'
            )
