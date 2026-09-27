# Pokemon Card Market - Project Guide

## 1. 프로젝트 개요

프로젝트명: Pokemon Card Market

목표:
여러 외부 데이터 소스에서 포켓몬 카드 기본정보와 판매 가격을 가져와
카드별 가격을 비교하고 통합 시세를 보여주는 웹사이트를 만든다.

최종적으로 웹에 배포하여 다른 사용자가 URL로 접속할 수 있도록 한다.

이 프로젝트는 취업 포트폴리오 용도이면서 실제 사용 가능한 웹사이트를 목표로 한다.

개발자는 프로그래밍 초심자이므로
기능을 불필요하게 복잡하게 만들지 않는다.

이 사이트는 소수의 지인이 별도 계정 없이 URL로 접속하여 사용하는
포켓몬 카드 시세 조회 사이트다.

일반 사용자는 로그인 없이 다음 기능을 사용한다.

- 카드 검색 및 목록 조회
- 카드 상세 조회
- 현재 통합 시세 조회
- 판매처별 가격 조회
- RAW / PSA 등 상태별 가격 조회
- 가격 변화 그래프 조회

일반 사용자용 회원가입, 로그인, 로그아웃, 프로필, 소셜 로그인,
사용자별 권한, 즐겨찾기 및 사용자별 데이터는 프로젝트 범위에서 제외한다.
Django Admin은 개발자/관리자용으로 유지하며 Django 관리자 인증을 사용한다.
일반 사용자 사이트와 Django Admin 인증은 서로 다른 범위다.


---

# 2. 현재 개발 환경

OS:
Windows

IDE:
VS Code

프로젝트 경로:

C:\Users\gogwm\Desktop\포켓몬

Python:
3.14.7

Django:
6.1.1

가상환경:
.venv

현재 .venv는 생성되어 있으며 정상적으로 작동한다.

현재 생성된 파일:

- .gitignore
- requirements.txt
- PROJECT_GUIDE.md
- docs/PHASE1_DESIGN.md
- manage.py
- config/
- cards/
- templates/
- db.sqlite3


---

# 3. 개발 환경 규칙

반드시 현재 프로젝트의 `.venv`를 사용한다.

전역 Python 환경에는 패키지를 설치하지 않는다.

새로운 Python 패키지가 필요한 경우:

1. 정말 필요한 패키지인지 확인한다.
2. 현재 `.venv`에 설치한다.
3. `requirements.txt`를 업데이트한다.

Python 3.14 또는 Django 6.1과 호환성 문제가 발생하면
억지로 우회하지 말고 원인을 먼저 확인한다.

현재 데이터베이스는 Django 기본 SQLite를 사용한다.

현재 사용하지 않는 기술:

- ChromaDB
- PostgreSQL
- MySQL
- Redis
- Celery
- React
- Node.js
- Kafka
- Elasticsearch
- Kubernetes
- Scheduler

Docker 역시 초기 개발 단계에서는 사용하지 않는다.

필요성이 생기면 프로젝트 후반부에 검토한다.


---

# 4. 개발 원칙

이 프로젝트의 개발자는 초심자다.

따라서 다음 원칙을 지킨다.

1. 최대한 단순한 구조를 사용한다.
2. Django App을 불필요하게 많이 나누지 않는다.
3. 어려운 디자인 패턴을 남용하지 않는다.
4. 함수와 변수 이름을 이해하기 쉽게 작성한다.
5. 중요한 코드에는 짧은 주석을 작성한다.
6. 한 파일에 모든 코드를 몰아넣지 않는다.
7. 새로운 라이브러리를 최소화한다.
8. 기존 파일을 수정하기 전에 현재 코드를 확인한다.
9. 같은 기능을 중복 구현하지 않는다.
10. 오류를 숨기지 않고 원인을 찾아 해결한다.
11. 실제 실행되지 않는 기능을 완료했다고 표시하지 않는다.
12. 주요 기능을 구현한 후 실제 실행 또는 테스트한다.
13. 과도한 최적화를 하지 않는다.
14. 기능이 정상 작동하는 것을 우선한다.


---

# 5. 외부 데이터 사용 원칙

카드 정보와 가격 데이터를 사용자가 하나씩 직접 입력하는 것을
기본 방식으로 사용하지 않는다.

가능하면 외부 API 또는 합법적으로 사용할 수 있는 데이터 소스에서
자동으로 가져오는 구조를 사용한다.

데이터는 크게 두 종류로 구분한다.


## 카드 기본정보

예:

- 카드 이름
- 영문 이름
- 세트
- 카드 번호
- 레어도
- 카드 이미지


## 판매/가격 정보

예:

- 판매 사이트
- 상품 제목
- 가격
- 상품 URL
- 카드 상태
- PSA/BGS/CGC 여부
- 등급


카드 기본정보와 판매가격은
서로 다른 데이터 출처를 사용할 수 있다.


---

# 6. 외부 API 관련 중요 규칙

외부 데이터 출처는 실제 사용 가능 여부를 확인한 후 구현한다.

후보:

- 포켓몬 카드 데이터 API
- 네이버 관련 서비스
- 번개장터
- KREAM
- 와이스
- 기타 카드 거래 사이트

후보라는 이유만으로 구현하지 않는다.

다음을 금지한다.

- 존재하지 않는 API 임의 생성
- 확인되지 않은 API URL 사용
- 비공개 내부 API 무단 사용
- 로그인 우회
- CAPTCHA 우회
- 접근 제한 우회
- 차단 우회

공식 API가 없거나 이용 가능 여부가 불확실하면
구현하지 말고 TODO로 남긴다.

실제 데이터 소스는 해당 Phase에서 별도로 검토 후 결정한다.

카드 기본정보 출처와 판매가격 출처는 서로 별도로 조사하며, 현재는 어느 후보도
사용한다고 확정하지 않는다. 출처가 확정되기 전에는 가짜 API, 임의의 크롤링,
후보 사이트 전용 Collector를 구현하지 않는다.


---

# 7. 초기 기술 스택

Backend / Frontend:

- Python
- Django
- Django ORM
- SQLite
- Django Templates
- Bootstrap

데이터 처리:

- requests
- Python 기본 통계 기능
- 필요할 경우 검토 후 추가 라이브러리 사용

환경변수:

- python-dotenv 또는 Django에서 적절한 단순한 방식

그래프:

- Chart.js


---

# 8. 핵심 기능

최종적으로 다음 기능을 구현한다.


## 8.1 카드 검색

사용자가 포켓몬 카드 이름을 검색한다.

예:

리자몽

검색 결과에는 다음을 표시한다.

- 카드 이미지
- 카드 이름
- 세트
- 카드 번호
- 레어도
- 현재 시세


## 8.2 카드 상세 페이지

다음 정보를 표시한다.

- 카드 이미지
- 카드 이름
- 세트
- 카드 번호
- 레어도

시세:

- 현재 통합 시세
- 평균 가격
- 최저 가격
- 최고 가격
- 가격 데이터 개수


## 8.3 거래처별 판매가격

예:

| 판매처 | 상품 | 가격 |
|---|---|---:|
| 거래처 A | 리자몽 ex SAR | 110,000원 |
| 거래처 B | 리자몽 ex SAR | 115,000원 |

가능하면 원본 상품 페이지 링크를 제공한다.


## 8.4 가격 변화

PriceHistory를 이용해서 가격 변화를 보여준다.

기간 후보:

- 1일
- 7일
- 30일
- 3개월

Chart.js를 사용한다.


---

# 9. 데이터 모델

초기에는 다음 네 모델을 기준으로 설계한다.


## Card

포켓몬 카드 자체의 정보.

예상 필드:

- id
- external_id
- name_ko
- name_en
- set_name
- card_number
- rarity
- language
- image_url
- source
- created_at
- updated_at


## MarketSource

판매 데이터 출처.

추가 필드:

- market_region: KR 또는 GLOBAL

예:

- NAVER
- BUNJANG
- KREAM
- WISE
- 기타


## MarketListing

외부에서 수집한 판매 상품.

예상 필드:

- id
- card
- market_source
- external_id
- title
- price: 통화의 소수 단위를 보존하는 십진수
- currency: KRW, USD, EUR 등의 통화 코드
- url
- condition
- grading_company
- grading_score
- collected_at


## PriceHistory

계산된 시세 기록.

예상 필드:

- id
- card
- condition
- currency: KRW, USD, EUR 등의 통화 코드
- calculated_at
- median_price
- average_price
- min_price
- max_price
- listing_count


필드 변경이 필요한 경우
이유를 설명하고 가능한 한 단순하게 수정한다.


---

# 10. 데이터 관계

기본 관계:

MarketSource
    |
    | 1:N
    |
MarketListing
    |
    | N:1
    |
Card
    |
    | 1:N
    |
PriceHistory


하나의 Card에는 여러 MarketListing이 존재할 수 있다.

하나의 Card에는 여러 PriceHistory가 존재할 수 있다.

하나의 MarketSource에는 여러 MarketListing이 존재할 수 있다.


---

# 11. Collector 구조

외부 데이터 수집 로직은 다른 비즈니스 로직과 분리한다.

개념적으로 두 종류의 Collector를 사용한다.


## CardDataCollector

카드 기본정보 수집.

흐름:

외부 카드 데이터
→ CardDataCollector
→ 정규화
→ 중복 확인
→ Card DB 저장


## MarketCollector

판매 상품 및 가격 수집.

흐름:

외부 판매 데이터
→ MarketCollector
→ 정규화
→ 카드 매칭
→ 상태 분류
→ MarketListing 저장


예상 구조:

collectors/
    base.py

    card_data/
        ...

    markets/
        ...


실제 API가 결정되기 전에는
사이트별 Collector를 가짜로 구현하지 않는다.


---

# 12. 카드 중복 방지

외부에서 카드 데이터를 다시 가져오더라도
같은 카드가 계속 생성되면 안 된다.

우선순위 후보:

1. 외부 데이터의 고유 ID
2. 세트 + 카드번호
3. 카드명 + 세트 + 카드번호

실제 데이터 소스가 결정되면
해당 데이터에 가장 적합한 방식을 선택한다.


---

# 13. 동일 카드 매칭

판매 상품을 실제 Card와 연결해야 한다.

예:

외부 상품:

포켓몬카드 리자몽 ex SAR 201/165


DB:

name_ko = 리자몽 ex
card_number = 201/165
rarity = SAR


초기 버전에서는 AI/머신러닝을 사용하지 않는다.

다음을 활용한다.

- 문자열 정규화
- 카드 이름
- 카드 번호
- 세트
- 레어도

정확한 카드 번호가 상품명에 존재한다면
높은 우선순위로 사용한다.


---

# 14. 카드 상태 분류

같은 카드라도 상태 또는 등급에 따라 가격이 다르다.

초기 분류:

- RAW
- PSA
- BGS
- CGC
- SEALED
- UNKNOWN

예:

PSA10 리자몽 ex SAR

이면:

grading_company = PSA
grading_score = 10

으로 분류한다.

PSA 10 가격을 RAW 카드 시세에 포함하지 않는다.

초기에는 AI를 사용하지 않고
상품 제목의 문자열/키워드를 이용한다.


---

# 15. 가격 이상치 처리

예:

10000
110000
115000
120000
125000
130000
500000

10,000원이나 500,000원 같은 값 때문에
시세가 크게 왜곡될 수 있다.

초기에는 IQR 등의
간단하고 설명 가능한 통계 방법을 고려한다.

단:

가격 데이터 개수가 너무 적으면
무조건 이상치를 제거하지 않는다.

구체적인 기준은 시세 계산 Phase에서 테스트를 통해 결정한다.


---

# 16. 통합 시세

Card + 상태별로 계산한다.

계산 항목:

- median
- average
- min
- max
- listing_count

대표 시세는 기본적으로 median을 사용한다.

평균값은 참고값으로 제공한다.

국내/해외 판매처는 `MarketSource.market_region`으로 구분하고 개별 가격과 계산 이력의
통화는 `MarketListing.currency`, `PriceHistory.currency`에 저장한다. 환율 변환은
구현하지 않으며 서로 다른 통화의 가격을 하나의 시세로 합치지 않는다.


---

# 17. 가격 기록

시세 계산 결과는 PriceHistory에 저장한다.

이를 이용해서 향후 가격 변화 그래프를 만든다.

예:

리자몽 ex SAR / RAW

9월 1일
115,000원

9월 7일
120,000원

9월 14일
118,000원

9월 21일
125,000원


---

# 18. 가격 갱신

초기 버전에서는 자동 Scheduler를 사용하지 않는다.

수동 가격 갱신을 사용한다.

예:

python manage.py update_prices


최종적인 동작 흐름:

외부 데이터 가져오기
→ 데이터 정규화
→ 동일 카드 매칭
→ 카드 상태 분류
→ MarketListing 저장
→ 이상치 처리
→ 시세 계산
→ PriceHistory 저장


자동 갱신 기능은 사이트가 정상적으로 완성된 후 별도로 검토한다.

최종 목표는 사용자가 사이트에 접속했을 때 가능한 최신 가격을 확인할 수 있게
반복 갱신 가능한 구조를 만드는 것이다. 초기에는 위 관리 명령을 통한 수동 갱신만
사용한다. 실제 배포 후 외부 데이터 출처의 Rate Limit과 이용 조건을 확인한 뒤에만
필요할 경우 자동 갱신을 검토하며, 자동 갱신 주기는 지금 확정하지 않는다.


---

# 19. 웹 페이지

Django Templates + Bootstrap을 사용한다.

일반 사용자는 로그인 없이 아래 페이지를 조회한다. 일반 사용자 인증 페이지와
사용자별 기능은 만들지 않는다.


## 메인

예상 URL:

/

기능:

- 사이트 제목
- 카드 검색창
- 카드 목록


## 검색

예상 URL:

/cards/?q=리자몽

표시:

- 카드 이미지
- 이름
- 세트
- 카드번호
- 레어도
- 시세


## 카드 상세

예상 URL:

/cards/<id>/

표시:

카드 정보

통합 시세

평균

최저가

최고가

판매 데이터 개수

거래처별 판매상품

가격

원본 링크

가격 변화 그래프


---

# 20. Django Admin

Django Admin을 적극 활용한다.

관리 대상:

- Card
- MarketSource
- MarketListing
- PriceHistory

가능하면 검색과 필터를 추가한다.

별도의 관리자 사이트를 처음부터 만들지 않는다.

Django Admin의 인증은 개발자/관리자 전용이다. 일반 사용자가 이용하는 공개 조회
페이지에 Django 관리자 로그인을 요구하지 않는다.


---

# 21. 보안

API Key 또는 Secret을 코드에 작성하지 않는다.

환경변수 또는 `.env`를 사용한다.

`.env`는 `.gitignore`에 포함한다.

API Key를 GitHub에 업로드하지 않는다.

외부 API Rate Limit을 준수한다.

로컬 기본 SECRET_KEY는 개발 전용 문자열만 사용한다. 운영에서는 `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` 환경변수를
반드시 설정하고 실제 Secret을 Git에 저장하지 않는다.


---

# 22. 테스트

핵심 비즈니스 로직에는 테스트를 작성한다.

중요 테스트:

- 카드 중복 방지
- 동일 카드 매칭
- PSA 등급 인식
- RAW / PSA 가격 분리
- median 계산
- average 계산
- 이상치 제거
- MarketListing 중복 방지

테스트 명령:

python manage.py test

주요 Phase가 끝나면 테스트한다.


---

# 23. 개발 Phase

## Phase 1 - 설계

- 프로젝트 구조
- Django App 구성
- DB 설계
- ERD
- Collector 구조
- 가격 계산 구조


## Phase 2 - Django 기본 프로젝트

- Django 프로젝트 생성
- Django App 생성
- 기본 settings
- 기본 URL
- 초기 페이지
- 서버 실행 확인


## Phase 3 - DB

- Card
- MarketSource
- MarketListing
- PriceHistory

- migration
- Django Admin


## Phase 4 - 카드 기본정보 데이터

실제 사용 가능한 외부 데이터 소스를 확정한 후 구현한다.

목표:

외부 데이터
→ Card DB 자동 등록

현재 CardData dataclass, Collector 기본 인터페이스, Card import 서비스와
`python manage.py import_cards` 진입점이 구현되어 있다. JustTCG 공식 stable v1
`GET /v1/cards` Collector와 `--source justtcg`, `--limit`, `--query`, `--dry-run`을
추가했다. 실제 API에서 Pokemon/Korean 필터와 응답 구조를 5건씩 두 번 확인했으나
모든 Card의 `variants`가 비어 있어 Korean variant Card DB 저장은 아직 대기한다.
JustTCG 가격은 이번 Card 기본정보 import에 저장하지 않는다.


## Phase 5 - 카드 화면

- 카드 목록
- 검색
- 상세 페이지


## Phase 6 - 실제 판매가격 데이터

eBay 공식 Browse API의 `item_summary/search`를 해외 참고 가격 출처로 사용한다.
OAuth Client Credentials, timeout과 오류 구분, 공통 MarketData 정규화 구조를 구현했다.
실제 개발자 인증정보가 없어 Mock 테스트까지 완료했으며 실제 호출 검증은 대기한다.
eBay 데이터는 한국/국내 시세로 표시하지 않는다.


## Phase 7 - 카드 매칭

- 문자열 정규화
- 카드번호
- 카드명
- 세트
- 레어도


## Phase 8 - 상태 분류

- RAW
- PSA
- BGS
- CGC
- SEALED


## Phase 9 - 시세 계산

- 이상치 처리
- median
- average
- min
- max
- listing_count


## Phase 10 - PriceHistory

- 가격 기록
- Chart.js 그래프


## Phase 11 - 수동 가격 갱신

python manage.py update_prices

`--card-id`, `--limit`, `--dry-run`을 지원한다. 인증정보가 없으면 네트워크나 DB 변경
없이 안내 후 종료한다. dry-run은 인증정보가 있을 때 API는 호출하지만 DB에 저장하지 않는다.


## Phase 12 - UI

- Bootstrap 기반 Home, 검색, pagination, 상세 정보 구조
- 모바일·태블릿·PC 반응형 화면과 접근성 보완
- DEMO 표시, empty state, 상태·등급·통화별 가격 및 그래프


## Phase 13 - 테스트

- DEMO seed/clear와 실제 source 보호
- API Mock, 검색 pagination, 그래프 그룹, 환경변수, 404 테스트
- 외부 API를 호출하지 않는 전체 회귀 테스트


## Phase 14 - GitHub

- 포트폴리오 README, 프로젝트 구조, 실행·환경변수 설명 완료
- `.gitignore` 및 Secret 검사 준비 완료
- 표준 설치 경로의 Git으로 `git init`과 staging 완료
- Git 사용자 이름/email이 없어 첫 commit은 대기
- GitHub repository와 remote는 아직 만들지 않음


## Phase 15 - 배포

로컬에서 모든 핵심 기능이 정상 작동한 후 진행한다.

GitHub와 적절한 웹 호스팅 서비스를 이용해
인터넷에서 접속 가능한 URL을 만든다.

친구가 별도 프로그램을 설치하지 않고
휴대폰/PC 브라우저에서 사용할 수 있도록 한다.


---

# 24. README 최종 목표

README.md에는 최종적으로 다음 내용을 포함한다.

- 프로젝트 소개
- 개발 목적
- 주요 기능
- 기술 스택
- 시스템 구조
- ERD
- 데이터 출처
- 데이터 수집 방식
- 카드 매칭 방식
- 상태 분류 방식
- 시세 계산 방식
- 설치 방법
- 실행 방법
- 환경변수
- 테스트 방법
- 주요 화면
- 배포 URL
- 향후 개선사항


---

# 25. Codex 작업 규칙

Codex는 새로운 작업을 시작할 때:

1. 이 PROJECT_GUIDE.md를 먼저 읽는다.
2. 현재 프로젝트 파일을 확인한다.
3. 기존 구현 상태를 확인한다.
4. 현재 요청받은 Phase만 작업한다.
5. 필요 이상의 기능을 미리 구현하지 않는다.
6. 기존 정상 기능을 불필요하게 변경하지 않는다.
7. 작업 후 실행 또는 테스트한다.


각 Phase 완료 후 다음을 보고한다.

1. 이번에 구현한 내용
2. 생성한 파일
3. 수정한 파일
4. 핵심 코드 설명
5. 실행한 명령
6. 테스트 결과
7. 직접 확인해야 할 방법
8. 남아 있는 문제
9. 다음 Phase에서 할 내용


---

# 26. 현재 진행 상태

- [x] Phase 1 - 설계
- [x] Phase 2 - Django 기본 프로젝트
- [x] Phase 3 - DB
- [x] Phase 4 - 카드 기본정보 기반 (JustTCG 실제 연결 확인, Korean variant import 대기)
- [x] Phase 5 - 카드 화면
- [x] Phase 6 - 판매가격 데이터 기반 (eBay Mock 검증 완료, 실제 인증 검증 대기)
- [x] Phase 7 - 카드 매칭
- [x] Phase 8 - 상태 분류
- [x] Phase 9 - 시세 계산
- [x] Phase 10 - PriceHistory
- [x] Phase 11 - 수동 가격 갱신
- [x] Phase 12 - UI
- [x] Phase 13 - 테스트 및 오류처리
- [x] Phase 14 - 로컬 Git/README 준비 완료 (identity 설정과 commit/push 대기)
- [ ] Phase 15 - 배포 (Render 배포 준비 완료, 실제 서비스 생성·배포 대기)


# 27. 현재 작업

Phase 1~14와 Render 배포용 코드 준비가 완료되었다. 실제 Render 서비스와 PostgreSQL은
생성하지 않았고 배포도 진행하지 않았다.

현재 구현된 범위:

- `config` Django 프로젝트
- 단일 `cards` App
- `/` Home 페이지
- `/admin/` Django Admin URL
- Django 기본 migration
- Card, MarketSource, MarketListing, PriceHistory 모델
- `cards.0001_initial` migration
- 네 모델의 Django Admin 등록
- CardData와 CardDataCollector 기본 구조
- Card 생성·갱신·중복 확인 import 서비스
- JustTCG stable v1 Collector와 소량 dry-run용 `import_cards` 관리 명령
- `/cards/` 카드 검색 및 24개 단위 목록
- `/cards/<int:pk>/` 카드 상세와 가격 데이터 안전 표시
- eBay 공식 Browse API Collector와 Application access token 발급 구조
- 설명 가능한 카드 매칭 및 RAW/PSA/BGS/CGC/SEALED/UNKNOWN 분류
- 통화·상태·등급별 IQR/중앙값 시세 계산과 PriceHistory 저장
- `update_prices --card-id/--limit/--dry-run` 수동 갱신 명령
- eBay 해외 판매가격 표시와 상태·통화별 Chart.js 그래프
- JustTCG `--query/--set/--number/--list-sets` 제한 탐색 구조
- 재실행 가능한 DEMO seed와 실제 source 보호형 clear 명령
- 데이터 상태 안내, 검색 UX, 반응형 상세, 404/500 페이지
- 배포용 Django 환경변수와 `STATIC_ROOT` 구조
- Gunicorn, WhiteNoise, `DATABASE_URL` 기반 PostgreSQL, 로컬 SQLite fallback
- Render build script, Blueprint, `/health/`, 상세 배포 문서
- Mock/DB/UI/배포 설정 회귀 테스트
- GitHub 원격 저장소 연결 및 기존 코드 push 완료

Phase 4의 JustTCG 공식 API 연결은 실제 응답으로 확인했다. 다만 확인한 10개 Card에는
Korean variant가 없어 Card DB import는 완료하지 않았다. eBay 판매가격 파이프라인은
Developer 승인 대기 상태이며 Mock 테스트까지만 검증되었다. 국내 가격 데이터 출처는 계속 검토 중이며,
확인되지 않은 API나 크롤링은 구현하지 않는다.
