import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import dotenv_values

from cards.collectors import CardData


class JustTCGError(Exception):
    """JustTCG 수집 중 사용자에게 안전하게 표시할 수 있는 오류다."""


class JustTCGMissingCredentialsError(JustTCGError):
    pass


@dataclass(slots=True)
class JustTCGReport:
    returned_cards: int = 0
    korean_variant_cards: int = 0
    without_korean_variant: int = 0
    korean_name_cards: int = 0
    english_name_only_cards: int = 0
    image_url_cards: int = 0
    without_image_url: int = 0
    request_count: int = 0
    meta: dict = field(default_factory=dict)
    metadata_keys: tuple[str, ...] = ()
    card_summaries: list[dict] = field(default_factory=list)


class JustTCGCardCollector:
    BASE_URL = 'https://api.justtcg.com/v1'
    CARDS_URL = f'{BASE_URL}/cards'
    SETS_URL = f'{BASE_URL}/sets'
    SOURCE = 'JUSTTCG'

    def __init__(self, api_key=None, session=None, timeout=10):
        self.api_key = api_key or os.environ.get('JUSTTCG_API_KEY') or self._env_file_key()
        self.session = session or requests.Session()
        self.timeout = timeout
        self.last_report = JustTCGReport()

    @property
    def is_configured(self):
        return bool(self.api_key)

    def collect(self, limit=5, query=None, set_id=None, number=None):
        if not self.is_configured:
            raise JustTCGMissingCredentialsError(
                'JUSTTCG_API_KEY가 설정되지 않았습니다.'
            )
        if not 1 <= limit <= 20:
            raise ValueError('JustTCG Free Tier 요청 수는 1~20 사이여야 합니다.')

        params = {
            'game': 'pokemon',
            'language': 'Korean',
            'limit': limit,
            'offset': 0,
            'include_price_history': 'false',
        }
        if query and query.strip():
            params['q'] = query.strip()
        if set_id and set_id.strip():
            params['set'] = set_id.strip()
        if number and number.strip():
            params['number'] = number.strip()

        try:
            response = self.session.get(
                self.CARDS_URL,
                headers={'x-api-key': self.api_key},
                params=params,
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise JustTCGError('JustTCG API 요청 시간이 초과되었습니다.') from error
        except requests.RequestException as error:
            raise JustTCGError('JustTCG API 요청에 실패했습니다.') from error

        if response.status_code in (401, 403):
            raise JustTCGError('JustTCG API 인증에 실패했습니다.')
        if response.status_code == 429:
            raise JustTCGError('JustTCG Free Tier 호출 한도를 초과했습니다. 재시도하지 않습니다.')
        if not 200 <= response.status_code < 300:
            raise JustTCGError(
                f'JustTCG API가 HTTP {response.status_code} 오류를 반환했습니다.'
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise JustTCGError('JustTCG API 응답이 올바른 JSON이 아닙니다.') from error

        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise JustTCGError('JustTCG API 응답의 data 형식이 올바르지 않습니다.')

        return self._normalize_response(payload)

    def collect_sets(self, query=None):
        if not self.is_configured:
            raise JustTCGMissingCredentialsError('JUSTTCG_API_KEY가 설정되지 않았습니다.')
        params = {'game': 'pokemon'}
        if query and query.strip():
            params['q'] = query.strip()

        payload = self._get_json(self.SETS_URL, params)
        data = payload.get('data')
        if not isinstance(data, list):
            raise JustTCGError('JustTCG Set 응답의 data 형식이 올바르지 않습니다.')
        self.last_report = JustTCGReport(request_count=1)
        return [
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'game': item.get('game'),
                'release_date': item.get('release_date'),
            }
            for item in data
            if isinstance(item, dict)
            and item.get('id')
            and item.get('name')
            and str(item.get('game', '')).casefold() == 'pokemon'
        ]

    def _get_json(self, url, params):
        try:
            response = self.session.get(
                url,
                headers={'x-api-key': self.api_key},
                params=params,
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise JustTCGError('JustTCG API 요청 시간이 초과되었습니다.') from error
        except requests.RequestException as error:
            raise JustTCGError('JustTCG API 요청에 실패했습니다.') from error

        if response.status_code in (401, 403):
            raise JustTCGError('JustTCG API 인증에 실패했습니다.')
        if response.status_code == 429:
            raise JustTCGError('JustTCG Free Tier 호출 한도를 초과했습니다. 재시도하지 않습니다.')
        if not 200 <= response.status_code < 300:
            raise JustTCGError(f'JustTCG API가 HTTP {response.status_code} 오류를 반환했습니다.')
        try:
            payload = response.json()
        except ValueError as error:
            raise JustTCGError('JustTCG API 응답이 올바른 JSON이 아닙니다.') from error
        if not isinstance(payload, dict):
            raise JustTCGError('JustTCG API 응답 형식이 올바르지 않습니다.')
        return payload

    def _normalize_response(self, payload):
        raw_cards = payload['data']
        report = JustTCGReport(
            returned_cards=len(raw_cards),
            request_count=1,
            meta=payload.get('meta') if isinstance(payload.get('meta'), dict) else {},
            metadata_keys=tuple(
                sorted(payload.get('_metadata', {}).keys())
                if isinstance(payload.get('_metadata'), dict)
                else ()
            ),
        )
        cards = []

        for raw_card in raw_cards:
            if not isinstance(raw_card, dict):
                raise JustTCGError('JustTCG Card 항목 형식이 올바르지 않습니다.')

            variants = raw_card.get('variants')
            if not isinstance(variants, list):
                raise JustTCGError('JustTCG Card의 variants 형식이 올바르지 않습니다.')

            variant_languages = sorted(
                {
                    str(variant.get('language'))
                    for variant in variants
                    if isinstance(variant, dict) and variant.get('language')
                }
            )
            korean_variants = [
                variant
                for variant in variants
                if isinstance(variant, dict)
                and str(variant.get('language', '')).casefold() == 'korean'
            ]
            image_url, image_fields = self._image_details(raw_card)
            name = str(raw_card.get('name') or '').strip()
            has_korean_name = bool(re.search(r'[가-힣]', name))

            report.card_summaries.append(
                {
                    'uuid': raw_card.get('uuid'),
                    'name': name,
                    'game': raw_card.get('game'),
                    'set': raw_card.get('set'),
                    'set_name': raw_card.get('set_name'),
                    'number': raw_card.get('number'),
                    'rarity': raw_card.get('rarity'),
                    'variant_count': len(variants),
                    'variant_languages': variant_languages,
                    'image_fields': image_fields,
                }
            )
            report.korean_name_cards += int(has_korean_name)
            report.english_name_only_cards += int(bool(name) and not has_korean_name)
            report.image_url_cards += int(bool(image_url))
            report.without_image_url += int(not image_url)

            if not korean_variants:
                report.without_korean_variant += 1
                continue
            report.korean_variant_cards += 1

            if str(raw_card.get('game', '')).casefold() != 'pokemon':
                raise JustTCGError('Pokemon이 아닌 Card가 응답에 포함되었습니다.')

            required = ('uuid', 'name', 'set_name', 'number')
            missing = [field for field in required if not raw_card.get(field)]
            if missing:
                raise JustTCGError(
                    f"JustTCG Card 필수 필드가 없습니다: {', '.join(missing)}"
                )

            cards.append(
                CardData(
                    external_id=str(raw_card['uuid']),
                    name_ko=name if has_korean_name else '',
                    name_en=None if has_korean_name else name,
                    set_name=str(raw_card['set_name']),
                    card_number=str(raw_card['number']),
                    rarity=(str(raw_card['rarity']) if raw_card.get('rarity') else None),
                    language='KO',
                    image_url=image_url,
                    source=self.SOURCE,
                )
            )

        self.last_report = report
        return cards

    @staticmethod
    def _image_details(raw_card):
        image_fields = tuple(sorted(key for key in raw_card if 'image' in key.casefold()))
        for key in ('image_url', 'imageUrl', 'image'):
            value = raw_card.get(key)
            if isinstance(value, str) and value.startswith(('https://', 'http://')):
                return value, image_fields
        return None, image_fields

    @staticmethod
    def _env_file_key():
        env_path = Path(__file__).resolve().parents[3] / '.env'
        if not env_path.exists():
            return None
        value = dotenv_values(env_path).get('JUSTTCG_API_KEY')
        return value if isinstance(value, str) and value.strip() else None
