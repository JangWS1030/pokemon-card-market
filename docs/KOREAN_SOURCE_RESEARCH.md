# 한국판 카드·국내 시장 source 조사

조사일: 2026-09-29

이 문서는 공개 페이지, 공식 약관, robots.txt만 확인한 결과다. 로그인, private API,
브라우저 개발자 도구, CAPTCHA 우회, browser automation은 사용하지 않았다. robots 허용은
콘텐츠 재사용이나 상업적 이용 허가와 같지 않으며, 접근 가능하다는 사실만으로 자동 수집을
활성화하지 않는다.

## 상태 요약

| Source | 조사 상태 | HTTP collector | 운영 판단 |
|---|---|---|---|
| Pokémon Card Game Korea | LIMITED | Disabled | NEEDS MANUAL CHECK |
| KREAM | LIMITED | Disabled | NEEDS MANUAL CHECK |
| 번개장터 | LIMITED | Disabled | NEEDS MANUAL CHECK |
| NAVER CardMVK | DISABLED | Disabled | DO NOT AUTOMATE |

현재 `READY` source는 없다. 따라서 Production write용 one-shot command도 만들지 않는다.

## Pokémon Card Game Korea

- 공개 카드 검색: <https://pokemoncard.co.kr/cards>
- 공식 이용약관: <https://pokemonkorea.co.kr/terms>
- robots.txt 확인 결과: `User-agent: *`, `Allow: /`
- 로그인하지 않고 카드 검색 화면, 한국어 카드명·제품·카드번호와
  `cards.image.pokemonkorea.co.kr` 이미지 참조를 확인할 수 있다.
- 사이트 footer는 콘텐츠 무단 복제·도용 금지를 명시한다.

### 판단

공개 metadata의 **발견 가능성**과 공식 이미지 URL의 **발견 가능성**은 확인했다. 그러나
metadata의 자동 저장, 외부 `<img>` hotlink, 이미지 다운로드·복제 권한은 확인되지 않았다.
robots 허용만으로 이 권한을 추정하지 않는다. `PokemonKoreaCardCollector`의 HTTP는
비활성 상태를 유지한다.

순수 normalizer는 공식 source가 제공한 값만 받아 `language=KO`,
`source=POKEMON_KOREA`로 변환한다. 대표 이미지는 명시적으로 제공된 HTTPS URL이면서
`cards.image.pokemonkorea.co.kr` host인 경우만 보존한다. 카드번호로 URL을 만들거나
filename/CDN path를 추측하지 않는다.

필요한 수동 확인은 포켓몬코리아에 카드 metadata 저장, 주기적 자동 조회, 이미지 hotlink
각각의 허용 범위와 적정 요청 빈도를 문의하는 것이다.

## KREAM

- 공개 상품 예시: <https://kream.co.kr/products/660881>
- 공식 이용약관: <https://kream.co.kr/agreement>
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

- 공개 상품 페이지: <https://m.bunjang.co.kr/products/428711864>
- 공개 검색 결과에서 stable product ID, 제목, KRW 표시 가격, 상품 URL, seller image,
  상대 게시 시점을 확인했다.
- robots.txt는 `/login`, `/apps`, `/talk2`를 제외한 일반 경로를 허용한다.
- 그러나 투명한 일반 User-Agent의 직접 HTTP 1회 응답은 실제 상품 metadata가 없는
  client shell뿐이었다. 안정적인 server-rendered parser를 만들 수 없었다.
- private API 조사나 browser automation은 하지 않았다.

### 판단

공개 상품의 `CURRENT_LISTING` 가능성은 확인했지만 안전하고 안정적인 자동 수집 interface와
이용 조건을 확정하지 못해 `LIMITED`다. HTTP collector는 비활성이다. 판매완료 표시는 실제
결제·체결 가격을 보장하지 않으므로 `SOLD`를 만들지 않는다. 배송비도 상품 가격에 합산하지
않는다.

자동 조회 허용 범위와 공식/문서화된 상품 데이터 interface가 있는지 번개장터에 수동 문의해야
한다.

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
