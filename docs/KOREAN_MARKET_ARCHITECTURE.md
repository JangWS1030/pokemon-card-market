# 한국판 카드·국내 시장 데이터 아키텍처

## 원칙

서비스의 우선 시장은 대한민국이며 한국판 Card와 KRW 데이터를 먼저 보여준다. eBay는
해외 비교용 CURRENT_LISTING이다. CURRENT_LISTING, SOLD, AUCTION_RESULT는 서로 다른
증거 수준과 의미를 가지므로 같은 통계 그룹에 절대 섞지 않는다.

## 공개 구조 조사 결과 (2026-09-29)

### Pokémon Card Game Korea

- 공개 카드 검색: `https://pokemoncard.co.kr/cards`
- 공개 카드 상세: `/cards/detail/<공개 식별자>` 형태가 검색 엔진에서 확인된다.
- 상세 페이지에는 한국어 카드명, 컬렉션 번호, 제품 링크와
  `cards.image.pokemonkorea.co.kr`의 이미지 참조가 노출될 수 있다.
- 사이트는 콘텐츠 무단 복제·도용 금지를 명시한다. 자동 수집 및 이미지 hotlink 허용
  조건과 robots 정책은 이번 조사에서 확정하지 못했다.

따라서 `PokemonKoreaCardCollector`는 HTTP를 비활성화하고, 허가된 공개 입력을 나중에
연결할 수 있는 순수 `normalize()` 경계만 제공한다. 이미지 URL을 추측하거나 다운로드,
복제하지 않는다. 실제 연결 전 운영자에게 자동 수집·저장·hotlink 허용 범위를 확인한다.

### KREAM

공개 상품 페이지에서 상품명, 모델 번호, 이미지, 체결 거래, 판매 입찰, 구매 입찰이라는
서로 다른 개념이 보인다. 일부 시세는 로그인 후 확인하도록 제한된다. 문서화된 공개 API나
자동 수집 권한을 확인하지 못했으므로 HTTP는 비활성화한다.

- 확인된 체결 거래 + 거래 시점: `SOLD` 후보
- 판매 입찰/판매 희망가: `CURRENT_LISTING` 후보
- 구매 입찰: 아직 모델링하지 않는 `BID` TODO
- 체결 여부나 시점이 불명확한 데이터: 저장하지 않음

### 번개장터

공개 robots 문서는 로그인·앱·대화 경로를 제외한 일반 공개 경로를 일부 허용하지만,
robots 허용은 데이터 재사용 권한이나 안정적인 공개 API를 뜻하지 않는다. 문서화된 공개
수집 인터페이스와 판매완료 가격의 의미를 확인하지 못했으므로 HTTP는 비활성화한다.

- 공개 판매 게시물: `CURRENT_LISTING` 후보
- 예약중·판매완료 문구·게시물 소멸: 실제 체결 증거로 사용하지 않음
- 명확한 체결 가격과 시점이 별도로 검증되기 전에는 `SOLD` 생성 금지

### NAVER CardMVK

대상 카페는 로그인, 회원 등급, 게시판 권한 및 NAVER 정책의 영향을 받을 수 있고 이번
조사 환경에서도 직접 콘텐츠 접근이 제한됐다. URL 추측이나 접근 우회 없이 HTTP를
비활성화한다.

- 공개 확인된 트레이드 게시물: `CURRENT_LISTING` 후보
- 명확한 최종 가격과 종료 시점이 있는 종료 경매: `AUCTION_RESULT` 후보
- 댓글 가격 전체, 종료 표시만 있는 경매: 저장하지 않음
- `AUCTION_RESULT`를 자동으로 `SOLD`로 변환하지 않음

## 모델 의미

`Card`의 현재 필드는 한국판 카드에 충분하다. `source=POKEMON_KOREA`, `language=KO`를
사용하고 natural key는 같은 source 안에서 `set_name + card_number + language`이며
한국어 이름을 보조 신호로 사용한다.

`MarketSource`는 변경 없이 다음 값을 표현할 수 있다.

| code | 이름 | region |
|---|---|---|
| `KREAM` | KREAM | `KR` |
| `BUNJANG` | 번개장터 | `KR` |
| `NAVER_CARDMVK` | 카드마켓 네이버 카페 | `KR` |
| `EBAY` | eBay | `GLOBAL` |

`MarketListing.listing_type`과 `PriceHistory.listing_type`은
`CURRENT_LISTING`, `SOLD`, `AUCTION_RESULT` 중 하나다. 완료형 데이터의 실제 기준 시점은
nullable `MarketListing.occurred_at`, 수집 시점은 `collected_at`에 별도로 저장한다.

가격 계산 key는 `Card + listing_type + condition + grading_score + currency`다. KRW와
USD, 현재 매물과 실거래, 경매 결과를 합치지 않는다.

## 이미지 정책

- `Card.image_url`: 한국판 카드 자체의 대표 이미지 URL
- `MarketListing.image_url`: 판매자가 올린 개별 매물 이미지 URL

둘 사이에 fallback이나 자동 복사를 두지 않는다. Pokémon Korea의 사용 허가가 불명확한
동안 이미지 hotlink 및 서버 복제를 하지 않는다. 공식 이미지가 없으면 placeholder를 쓴다.

## 비활성 collector 경계

`PokemonKoreaCardCollector`, `KreamMarketCollector`, `BunjangMarketCollector`,
`NaverCafeCardmvkCollector`는 synthetic fixture를 정규화하는 순수 함수만 제공한다.
`collect()`는 명시적으로 실패하므로 실제 HTTP, 로그인, private API 또는 우회가 발생하지
않는다. 개인정보 필드는 normalized schema에 없으며 판매자 이름·닉네임·전화번호·주소·ID를
저장하지 않는다.

## 향후 scheduler

각 source는 독립 management command로 실행한다.

```text
collect → normalize → match → classify → upsert → calculate history
```

후보 명령은 `update_korean_market`, `update_kream`, `update_bunjang`,
`update_naver_cardmvk`, `update_ebay`다. 실제 collector 승인 전에는 만들거나 실행하지
않는다. 구현 시 source별 timeout, 낮은 빈도, 명시적 pagination limit, 작은 request
budget, 제한된 retry를 적용하고 한 source 실패가 다른 source를 막지 않게 한다. Celery,
Redis, cron, APScheduler는 현재 도입하지 않는다.
