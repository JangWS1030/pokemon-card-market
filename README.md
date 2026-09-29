# Pokemon Card Market

> 무료 GitHub Actions 수동 수집 workflow의 설정·보안·운영 방법은
> [추가 운영비 0원 수집 스케줄러](docs/FREE_SCHEDULER.md)를 참고한다.

한국판 포켓몬 카드를 중심으로 검색하고, 수집된 국내외 시장 데이터를
가격 유형·상태·등급·통화별 참고 가격으로
보여주는 Django 프로젝트다. 공식 시장가나 실시간 국내 시세를 주장하지 않으며,
데이터 출처와 갱신 시점을 함께 표시한다.

## 문제와 목표

같은 카드도 RAW·PSA·BGS·CGC 상태와 등급, 통화에 따라 가격이 다르다. 이 프로젝트는
외부 데이터를 보수적으로 카드에 연결하고 CURRENT_LISTING, SOLD, AUCTION_RESULT 및 서로
다른 통화를 섞지 않은 참고값을 제공한다.
로그인 없이 카드 검색·상세·가격 변화를 볼 수 있는 작은 포트폴리오 서비스를 목표로 한다.

## 현재 상태

- Phase 1~11 기반 구현 완료
- Phase 12 UI 및 Phase 13 테스트·오류처리 완료
- JustTCG에서 실제 Pikachu `025/165` 기본정보를 Production PostgreSQL에 저장·표시 완료
- eBay Production OAuth/Browse 및 해당 카드의 현재 매물 3건 저장·표시 완료
- 국내 가격 데이터 출처 검토 중
- DEMO 데이터로 UI·검색·그래프 확인 가능
- Render Web Service와 PostgreSQL 배포 및 GitHub 기반 배포 흐름 검증 완료

DEMO는 실제 카드 또는 시세가 아니며 화면 전체에 명확히 표시된다.

## 주요 기능

- 카드명·영문명·세트·카드번호 검색과 pagination
- 카드 기본정보, eBay 현재 매물, 상태·등급·통화별 현재 매물 참고가
- RAW / PSA / BGS / CGC / SEALED 분리
- USD / KRW / EUR 분리 및 환율 미변환
- IQR 이상치 처리 후 median·average·min·max·데이터 수 계산
- 현재 매물 PriceHistory와 Chart.js 참고가 변화 그래프
- 공식 JustTCG v1 CardDataCollector
- 공식 eBay Browse API MarketCollector
- 한국 공식 카드·KREAM·번개장터·NAVER CardMVK용 HTTP 비활성 정규화 경계
- 개발 전용 DEMO seed/clear 명령
- Django Admin과 사용자 친화적 404/500 페이지

## 기술 스택

- Python 3.14, Django 6.1, Django ORM, 로컬 SQLite, Production PostgreSQL
- Django Templates, Bootstrap 5 CDN, Chart.js CDN
- requests, python-dotenv, Python 표준 통계 모듈

numpy, pandas, DRF, Celery, Redis, React, Node, Docker는 사용하지 않는다.

## 아키텍처

```text
JustTCG Card API
       ↓
CardDataCollector → 정규화/중복 확인 → Card
                                      ↓
eBay Browse API → MarketCollector → 카드 매칭
                                      ↓
                               상태·등급 분류
                                      ↓
                                MarketListing
                                      ↓
                         통화별 검증 + IQR 계산
                                      ↓
                                 PriceHistory
                                      ↓
                         Django Templates + Chart.js
```

Collector는 외부 응답 정규화만 담당하고 카드 매칭·상태 분류·가격 계산은 service 계층에
분리한다. 프로젝트는 단일 `cards` App을 유지한다.

## DB 모델

- `Card`: 카드명, 세트, 번호, 언어, 외부 UUID와 출처
- `MarketSource`: 판매 데이터 출처와 국내/해외 구분
- `MarketListing`: 원본 제목·URL·매물 이미지·가격·통화·상태·등급
- `PriceHistory`: 카드·상태·등급·통화별 현재 매물 통계 스냅샷

중복은 Card의 `source + external_id`, Listing의 `market_source + external_id`로 방지한다.

## 데이터 처리 원칙

### 카드 매칭

카드번호 완전 일치를 우선하고 카드명, 세트명, 명시적 언어, 레어도로 후보를 좁힌다.
후보가 정확히 하나일 때만 자동 연결하며 퍼지 매칭이나 AI는 사용하지 않는다.

### 상태 분류

명확한 제목 패턴만 사용한다. `PSA10`, `PSA 10`, `BGS 9.5`, `CGC 10`을 인식하며
등급 없는 회사명, 묶음 상품, 불확실한 상품은 `UNKNOWN`으로 두고 대표 계산에서 제외한다.

### 참고 가격

현재의 가격 통계는 eBay의 **현재 활성 매물(asking price)** 을
`Card + listing_type + condition + grading_score + currency`별로 분리한 참고값이다.
CURRENT_LISTING은 판매자가 요구하는 가격이며 판매완료 가격이나
국내 실거래 시세가 아니다. 표본 5개 이상이면
1.5×IQR 범위 밖 값을 제외하되 남는 값이 3개 미만이면 원본으로 되돌린다. median을
참고 시세로 사용하고 average·min·max·listing_count를 함께 기록한다.

## 데이터 출처

### JustTCG

공식 stable v1 `GET /v1/cards`와 `GET /v1/sets`만 사용한다. JustTCG는 Card 기본
metadata 출처다. Korean variant가 없더라도 정상 카드 기본정보는 `language=UNKNOWN`으로
저장할 수 있으며 JustTCG variant 가격은 카드 기본정보 흐름에서 저장하지 않는다.

현재 확인한 JustTCG v1 Card schema에는 공식 카드 대표 이미지 URL 필드가 없다. 따라서
`Card.image_url`이 비어 있는 것은 정상이며 URL을 추측하지 않는다. Collector의
`image_url`/`imageUrl`/`image` 확인 코드는 이전 또는 확장 응답과의 호환을 위한 방어적
fallback일 뿐, 현재 공식 schema의 이미지 제공을 의미하지 않는다. 카드 대표 이미지는
향후 이용 조건이 명확한 합법적 provider를 별도로 연결한다(TODO).

```powershell
.\.venv\Scripts\python.exe manage.py import_cards --source justtcg --query Pikachu --set SET_ID --number 25/100 --limit 5 --dry-run
.\.venv\Scripts\python.exe manage.py import_cards --source justtcg --list-sets --query Academy
```

명령 한 번은 한 페이지/API 요청만 사용하며 자동 pagination이나 retry를 하지 않는다.

### eBay

공식 Browse API `item_summary/search`와 OAuth Client Credentials를 사용한다. eBay
Browse 결과는 해외 **현재 판매 매물**이며 판매완료 거래가 아니다. `image.imageUrl`은
판매자가 등록한 해당 매물 이미지로만 저장·표시하고 공식 카드 artwork 또는
`Card.image_url`로 사용하지 않는다.

`PriceHistory`는 listing type·상태·등급·통화별 중앙값 등 통계를 저장한다.
SOLD 데이터는 CURRENT_LISTING 및 AUCTION_RESULT와 분리하며 기존 데이터와 합치지 않는다.
모델에는 `CURRENT_LISTING`, `SOLD`,
`AUCTION_RESULT` 구분을 준비했지만 국내 실제 데이터 source는 아직 연결되지 않았다.

한국 중심 데이터 source와 접근 정책, 비활성 collector 및 향후 scheduler 설계는
[한국판 카드·국내 시장 아키텍처](docs/KOREAN_MARKET_ARCHITECTURE.md)에 정리했다.

```powershell
.\.venv\Scripts\python.exe manage.py update_prices --card-id 1 --dry-run
.\.venv\Scripts\python.exe manage.py update_prices --limit 5
```

## 개발용 DEMO 데이터

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo_data
.\.venv\Scripts\python.exe manage.py clear_demo_data
```

`seed_demo_data`는 `source=DEMO`인 가상 카드 12개, Listing 8개, PriceHistory 24개를
만든다. 재실행해도 중복되지 않는다. `clear_demo_data`는 DEMO Card와 관련 데이터 및
`code=DEMO` MarketSource만 삭제하며 JUSTTCG/eBay 등 실제 출처는 보호한다.

## 설치와 실행

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

브라우저에서 `http://127.0.0.1:8000/`에 접속한다.

## 환경변수

`.env.example`에는 이름만 제공하며 실제 Secret은 `.env` 또는 운영 환경변수에 둔다.

```text
JUSTTCG_API_KEY=
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
DJANGO_SECRET_KEY=
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=
```

운영에서는 강한 `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, 실제 host/origin을 반드시
설정한다. 존재하지 않는 배포 URL은 코드에 하드코딩하지 않았다.

## 테스트

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

테스트는 외부 API를 실제 호출하지 않으며 Mock 응답만 사용한다.

## 배포 준비와 제한사항

- Render용 Gunicorn, WhiteNoise, PostgreSQL 설정과 `build.sh`가 준비되어 있다.
- 운영에서는 `DATABASE_URL`로 PostgreSQL을 쓰며, 로컬에서는 계속 SQLite를 쓴다.
- Render 무료 PostgreSQL은 영구 운영 DB로 가정하지 않고 포트폴리오·친구 테스트·기능
  검증 용도로만 사용한다. 무료 정책은 실제 배포 직전에 다시 확인한다.
- 실제 Render 서비스·DB·배포 URL은 아직 만들지 않았다.
- Dashboard 설정 순서와 무료 플랜 제한은 [Render 배포 안내](docs/DEPLOY_RENDER.md)를 따른다.
- 실제 카드·가격 데이터가 부족하며 DEMO를 실데이터로 사용하지 않는다.

## 향후 계획

1. 검증된 범위에서 여러 실제 Pokémon Card를 소량 import
2. 여러 Card의 eBay 현재 매물을 보수적으로 매칭·수집하는 운영 흐름 마련
3. 합법적인 카드 대표 이미지 provider와 국내 판매완료 가격 source 조사
