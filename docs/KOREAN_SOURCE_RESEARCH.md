# 한국판 카드·국내 시장 source 조사

최종 검증일: 2026-09-30

이 문서는 공개 페이지, 공식 약관, robots.txt만 확인한 결과다. 로그인, private API,
브라우저 개발자 도구, CAPTCHA 우회, browser automation은 사용하지 않았다. robots 허용은
콘텐츠 재사용이나 상업적 이용 허가와 같지 않으며, 접근 가능하다는 사실만으로 자동 수집을
활성화하지 않는다.

## 상태 요약

| Source | 조사 상태 | HTTP collector | 운영 판단 |
|---|---|---|---|
| Pokémon Card Game Korea | HTTP 410 IN USER ENVIRONMENT | Disabled + manual image URL | PUBLIC PAGE NOT USABLE BY COLLECTOR |
| BREAK | PUBLIC PRODUCT VERIFIED | Explicit URL only | READY FOR DRY RUN |
| KREAM | LIMITED | Disabled | PUBLIC PAGE NOT USABLE |
| 번개장터 | OFFICIAL API VERIFIED | Official API | NEEDS CREDENTIAL |
| NAVER CardMVK | DISABLED | Disabled | DO NOT AUTOMATE |

이번 개인용·소량 Phase에서는 로그인·CAPTCHA·private API 없이 보이는 공개 URL에 한해
one-shot 조회를 허용한다. 401/403/429, 로그인 요구 또는 challenge가 나오면 즉시 중단하며
우회하지 않는다. 자동 scheduler는 계속 꺼져 있다.

## Pokémon Card Game Korea

- 공개 카드 검색: <https://pokemoncard.co.kr/cards>
- 공식 이용약관: <https://pokemonkorea.co.kr/terms>
- robots.txt 확인 결과: `User-agent: *`, `Allow: /`
- 이전 조사 환경에서는 카드 HTML과 `cards.image.pokemonkorea.co.kr` 이미지 참조가
  보였지만, 실제 Windows 사용자 환경의 일반 requests와 Mozilla User-Agent 요청은 모두
  상세 URL에서 nginx `410 Gone`을 반환했다.
- 사이트 footer는 콘텐츠 무단 복제·도용 금지를 명시한다.

### 판단

사용자 환경에서 재현되지 않은 이전 접근 결과를 운영 근거로 삼지 않는다. 자동 상세 페이지
collector는 HTTP 요청 전에 중단하도록 비활성화했다. cookie/session 복사, 브라우저 위장,
Selenium/Playwright, CAPTCHA·anti-bot 우회는 구현하지 않는다. 기존 HTML parser와
normalizer는 향후 정상적인 공식 공개 응답이 제공될 경우를 위해 pure code로 보존한다.

순수 normalizer는 공식 source가 제공한 값만 받아 `language=KO`,
`source=POKEMON_KOREA`로 변환한다. 대표 이미지는 명시적으로 제공된 HTTPS URL이면서
`cards.image.pokemonkorea.co.kr` host인 경우만 보존한다. 카드번호로 URL을 만들거나
filename/CDN path를 추측하지 않는다.

사용자가 별도로 확인한 공식 CDN URL은 `set_card_image`로 수동 등록할 수 있다. HTTPS와
정확한 `cards.image.pokemonkorea.co.kr` host만 허용하고 URL을 조합하거나 추측하지 않는다.
기본 동작은 HTTP 0회이며 `--check-image`를 명시할 때만 HEAD 1회를 수행한다. 403/410 또는
잘못된 content-type이면 우회 없이 저장을 중단한다. URL reference만 저장하고 binary를
다운로드하지 않는다. 상태는 `PUBLIC PAGE NOT USABLE BY COLLECTOR`,
`MANUAL OFFICIAL IMAGE URL SUPPORTED`다.

## BREAK

- 공개 웹: <https://app.break.market/>
- robots.txt는 일반 공개 페이지를 허용하고 `/api/`, 로그인·프로필·채팅 등 개인 경로는
  차단한다. 공개 product sitemap도 제공한다.
- 공개 상품 HTML의 `og:title`, `og:description`, `og:image`에서 product ID, 제목,
  현재 입찰가/즉시구매가, 공개 URL, seller 상품 이미지를 확인할 수 있다.
- 실제 공개 페이지의 `현재 입찰가`는 종료·낙찰·결제 완료 근거가 아니므로
  `CURRENT_LISTING`으로만 저장한다. 제목에는 `진행 중 경매`를 명시한다.
- 종료 시각과 최종가가 동시에 명확한 입력만 `AUCTION_RESULT`가 될 수 있으며 SOLD로
  바꾸지 않는다. 현재 조사한 공개 페이지에서는 그런 종료 결과를 확인하지 못했다.
- seller 별명 등 개인정보는 parser 단계에서 제거한다.

검색 자동화나 sitemap 순회는 구현하지 않았다. 사용자가 직접 확인한
`https://app.break.market/products/<숫자>/...` URL 하나만 `--url`로 받으며 GET 1회,
pagination/retry 0회다. 가격문의 상품, 다른 카드번호, bundle/box/sealed, 안전하게
매칭되지 않는 상품은 저장하지 않는다. 따라서 명시적 URL one-shot 범위에서
`READY FOR DRY RUN`이다.

## KREAM

- 공개 상품 예시: <https://kream.co.kr/products/660881>
- 공식 이용약관: <https://kream.co.kr/agreement>
- `dev.cre.ma`의 CREMA는 별도 서비스이므로 사용하지 않는다.
- 공개 페이지에서 product ID, 상품명, 이미지, 체결 거래·판매 입찰·구매 입찰이라는
  구분과 일부 가격·거래일이 보인다.
- 전체 시세는 로그인 후 확인하도록 제한된다는 안내가 표시된다.
- robots.txt는 10초 제한의 1회 요청에서 응답을 받지 못했고 재시도하지 않았다.
- 문서화된 공개 수집 API나 자동 수집 허가를 확인하지 못했다.

### 판단

브라우저에 공개된 일부 정보의 의미는 확인할 수 있어 `LIMITED`다. 다만 정책 범위와 안정적인
공개 interface가 확인되지 않아 HTTP collector는 비활성이다. 숨겨진 API나 로그인 세션은
사용하지 않는다.

- 명확한 체결 거래 + KRW 가격 + 거래 시점: 향후 `SOLD` 후보
- 판매 입찰/판매 희망가: `CURRENT_LISTING` 후보
- 구매 입찰: 현재 모델에 없는 `BID`; 저장하지 않음
- 최근가·현재가·희망가를 `SOLD`로 변환하지 않음

KREAM의 자동 조회 허용 여부와 공개적으로 지원되는 데이터 제공 interface를 수동 문의해야
한다.

## 번개장터

- 공식 Open API 문서: <https://api.bgzt.guide/doc-662202>
- 파트너 계약과 계정 설정 뒤 발급되는 공식 `access key`, Base64 encoded `secret key`가
  필요하다. 환경변수명은 `BUNJANG_ACCESS_KEY`, `BUNJANG_SECRET_KEY`다.
- secret을 Base64 decode한 bytes로 HS256 JWT를 서명한다. GET JWT claim은 `accessKey`,
  `iat`이며 문서상 유효 시간은 발급 후 30초다. POST/PUT/DELETE에만 UUID v4 `nonce`를
  추가한다. `Authorization: Bearer <JWT>`로 전송한다.
- Production base URL은 `https://openapi.bunjang.co.kr`, 상품 검색은
  `GET /api/v1/products`이고 `q`, `size`를 사용한다.
- 응답에서 확인한 필드는 `pid`, `name`, `quantity`, `price`, `shippingFee`, `condition`,
  `saleStatus`, `imageUrlTemplate`, `imageCount`, `categoryId`, `brandId`, `options`, `uid`,
  `updatedAt`, `createdAt`, `nextCursor`, `hasNext`다.
- 공식 schema의 활성 판매 상태는 `SELLING`이다. `SELLING`만 `CURRENT_LISTING`으로
  정규화하며 다른 상태를 SOLD로 변환하지 않는다.
- API의 `condition`은 판매자가 표시한 일반 상품 상태이며 PSA/BGS/CGC 카드 등급과 의미가
  다르므로 grading 필드로 변환하지 않는다. 카드 상태는 기존 제목 기반 보수적 분류를 거친다.
- 공식 문서에는 일반적인 rate-limit 숫자가 표시되지 않는다. 따라서 429에서 즉시
  중단하고 retry하지 않으며, 명령 자체는 검색 GET 1회, 결과 최대 5건으로 제한한다.

### 판단

공식 API client, JWT signer, 검색 normalizer와 `update_bunjang` 명령은 mock으로 구현했다.
credential 발급 전에는 HTTP 0회로 SKIPPED되므로 상태는 `NEEDS CREDENTIAL`이다. 전체 catalog,
cursor pagination, 주문 API는 사용하지 않는다. API 응답의 `uid`는 seller 식별자이므로
저장하지 않는다. 상품 이미지는 공식 `imageUrlTemplate`에서 첫 번째 `{cnt}`만 치환하고
`media.bunjang.co.kr`을 allowlist한다. 배송비는 카드 가격에 합산하지 않는다.

## NAVER CardMVK

- 대상: <https://cafe.naver.com/cardmvk>
- cafe.naver.com robots.txt는 `User-agent: *`, `Disallow: /`다.
- NAVER 이용약관은 사전 허락 없이 bot, spider, scraper 등 자동화 수단으로 게시물이나
  ID 등을 수집하는 행위를 금지한다: <https://policy.naver.com/rules/service_pre_20250710.html>
- 이번 조사 환경에서도 카페 콘텐츠를 직접 공개 조회할 수 없었다.

### 판단

`DISABLED`, `DO NOT AUTOMATE`다. 로그인 여부나 카페 회원 등급을 우회하지 않고 NAVER
내부 API도 조사하지 않는다. 운영자와 NAVER의 명시적 허가 및 별도 공개 interface가 생기기
전까지 collector를 구현하지 않는다.

향후 허가된 입력이 생기더라도 가격이 있는 공개 트레이드는 `CURRENT_LISTING`, 종료·최종
낙찰가·종료 시점이 모두 명확한 경매만 `AUCTION_RESULT`다. `AUCTION_RESULT`는 자동으로
`SOLD`가 되지 않는다.

## 공통 데이터 원칙

- 개인정보: seller 이름, nickname, NAVER ID, 전화번호, 주소, profile image를 저장하지 않음
- 카드 이미지: 공식 카드 대표 이미지만 `Card.image_url` 후보
- seller 상품 이미지: `MarketListing.image_url`에만 저장
- 가격: `₩12,000`, `12,000원`, `12000`, `KRW 12000`처럼 명확한 원화 정수만 허용
- `1.2`, `1.5` 같은 축약 가격은 추측하지 않음
- 매칭: 한국어 이름과 정확한 카드번호를 우선하고, 다른 번호·이름·묶음·랜덤·대량은 skip
- source마다 실제 collector가 승인될 때 timeout 10초, 최대 3 items, retry 0회,
  request budget 1회를 기본 상한으로 다시 검토
- Pokepolio는 여러 플랫폼 데이터를 가공한 2차 시세 서비스이므로 collector를 만들지 않는다.
  사람이 우리 계산 결과와 공개 시세를 sanity check하는 용도로만 사용한다.
