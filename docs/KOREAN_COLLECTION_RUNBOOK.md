# 국내 시장 수집 운영 Runbook

## 현재 결론

2026-09-29 개인용·소량 정책 기준 Pokémon Korea 공개 상세 URL의 이미지 lookup은
`READY FOR DRY RUN`, BREAK 공개 상품 URL도 `READY FOR DRY RUN`이다. 번개장터는
공식 Open API client가 준비됐지만 파트너 credential 발급 전이므로 `NEEDS CREDENTIAL`이다.
KREAM과 NAVER CardMVK는 비활성이다. 자동 schedule과 Production write는 켜지 않았다.

## 현재 가능한 검증

로컬에서 외부 HTTP와 DB write 없이 orchestration을 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py update_korean_market --dry-run
```

GitHub Actions의 `Collect market data` workflow도 같은 dry-run만 실행한다. 이미 확인된 수동
workflow는 Django boot, External `DATABASE_URL`, migration 상태, command orchestration을
검증하는 용도다.

## One-shot 명령

명시적인 `--write`가 없으면 두 명령 모두 dry-run이며 DB write는 0이다. 정확히 한 Card만
선택하고 DEMO Card를 거부한다.

```powershell
.\.venv\Scripts\python.exe manage.py collect_pokemon_korea_image --card-id 13 --url "https://pokemoncard.co.kr/cards/detail/BS2023014025" --check-image --dry-run
.\.venv\Scripts\python.exe manage.py collect_break_once --card-id 13 --url "https://app.break.market/products/<PUBLIC_ID>/<PUBLIC_SLUG>" --dry-run
.\.venv\Scripts\python.exe manage.py update_bunjang --card-id 13 --limit 3 --dry-run
```

Pokémon Korea write는 매칭된 Card의 `image_url`만 바꾼다. BREAK write는 명시 가격이 있고
카드가 안전하게 매칭된 단일 상품만 transaction으로 저장하며 `market_source + external_id`
중복 방지를 재사용한다. BREAK URL은 사용자가 브라우저에서 공개 여부·가격·카드 식별을
먼저 확인해야 하며 예시 placeholder를 그대로 실행하면 안 된다.

## 실제 source 활성화 전 필수 순서

1. source 운영자에게 자동 조회, metadata 저장, 가격 저장, 이미지 URL 저장/hotlink 허용
   범위를 서면으로 확인한다.
2. 공식 API 또는 문서화되고 공개적으로 지원되는 interface를 확인한다.
3. source 하나만 대상으로 synthetic 최소 fixture와 mock HTTP 테스트를 먼저 추가한다.
4. timeout, item/request hard limit, retry 0회, 401/403/429/challenge 즉시 중단을 검증한다.
5. 명시적인 Card 한 장만 선택하고 DEMO·0개·복수 match를 차단하는 one-shot command를 만든다.
6. 로컬 mock → 명시적 one-shot dry-run → 사용자 결과 확인 순서로 검증한다.
7. 사용자가 Production one-shot 1건을 실행하고 DB/UI에서 source, 카드, 가격 유형을 확인한다.
8. 그 뒤에만 GitHub Actions manual actual run을 별도로 검토한다.
9. 여러 번의 수동 검증 후에만 자동 schedule을 별도 변경으로 제안한다.

## 현재 source별 다음 확인

- Pokémon Korea: 공개 상세 URL one-shot만 사용; 자동 검색·주기 수집은 별도 검토
- BREAK: 공개 product URL one-shot만 사용; 검색/sitemap 순회와 자동 schedule 금지
- 번개장터: 공식 파트너 access key/secret key 발급 후 Card 1장 dry-run부터 검증
- KREAM: 자동 조회 허용 여부와 공식적인 데이터 제공 interface 확인
- 번개장터: 자동 조회 허용 여부와 공식/문서화된 상품 interface 확인
- NAVER CardMVK: NAVER와 카페 운영자의 명시적 자동 수집 허가 없이는 진행하지 않음

Pokepolio는 자동 수집하지 않고 사람이 sanity check에만 사용한다. disabled command를 실제
collector처럼 오해하지 않는다.
