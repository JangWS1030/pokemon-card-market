from ._disabled_source import DisabledSourceCommand


class Command(DisabledSourceCommand):
    help = 'NAVER CardMVK collector를 실행합니다. 현재 HTTP 수집은 비활성화되어 있습니다.'
    source = 'NAVER CardMVK'
