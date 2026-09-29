# 추가 운영비 0원 수집 스케줄러

## 현재 구조

```text
GitHub Actions (collector command)
                 |
                 | TLS External DATABASE_URL
                 v
          Render PostgreSQL
                 ^
                 | Internal DATABASE_URL
                 |
       Render Django Web Service
```

데이터베이스를 복제하지 않는다. Render Web Service와 GitHub Actions는 같은
PostgreSQL을 사용하고, 로컬 개발만 `DATABASE_URL`이 없을 때 SQLite를 사용한다.
Render Cron Job, Background Worker, Celery, Redis, APScheduler는 사용하지 않는다.

## 현재 workflow

`.github/workflows/collect-market.yml`은 현재 `workflow_dispatch`만 지원한다.
`update_korean_market --dry-run`은 기존 source command의 안전한 orchestration 확인만 하며
외부 HTTP나 DB write를 수행하지 않는다. 새 공개 collector는 명시적 URL이 필요한 별도
one-shot command라 workflow에 연결하지 않았다.

실행 순서는 checkout, Python 3.13 설정, dependency 설치, Django system check,
PostgreSQL 연결 및 migration 상태 확인, collector orchestration 검증 순서다.
workflow는 migration을 적용하지 않으며 destructive command도 실행하지 않는다.

GitHub Actions 수동 실행에서 Django check, Production PostgreSQL 연결, migration 상태,
국내 collector orchestration이 모두 성공한 것을 확인했다. 이 성공은 실제 국내 HTTP 수집
승인을 의미하지 않는다. source 조사 결과는 `docs/KOREAN_SOURCE_RESEARCH.md`를 따른다.

## GitHub Repository Secret

현재 필요한 secret은 하나뿐이다.

- `DATABASE_URL`: Render PostgreSQL의 **External Database URL**

workflow 파일, 문서, 로그에 실제 URL을 넣지 않는다. GitHub Actions는 Render
네트워크 밖에서 실행되므로 Internal Database URL을 사용할 수 없다. 외부 연결은
TLS를 강제하도록 URL의 query에 `sslmode=require`가 포함되어 있는지 확인한다.
현재 `dj-database-url` 설정은 이 query option을 Django PostgreSQL connection
option으로 전달한다.

향후 collector를 실제 활성화할 때만 해당 provider secret을 별도로 추가한다.
현재 workflow는 eBay와 JustTCG를 실행하지 않으므로 관련 secret을 요구하지 않는다.

## 첫 수동 실행

1. GitHub repository의 **Settings > Secrets and variables > Actions**로 이동한다.
2. **New repository secret**을 선택한다.
3. 이름에 `DATABASE_URL`, 값에 Render PostgreSQL의 External Database URL을 넣는다.
4. URL에 `sslmode=require`가 포함되었는지 확인하되 URL을 issue나 로그에 붙여넣지 않는다.
5. repository의 **Actions** 탭에서 **Collect market data**를 선택한다.
6. **Run workflow**를 누르고 `main` branch에서 실행한다.
7. 로그에서 `Database connection: OK`, `Backend: PostgreSQL`, `Migrations: OK`와
   국내 source 4개의 `SKIPPED` summary를 확인한다.

연결 오류가 나더라도 로그에 URL, host, username, password는 출력되지 않는다.
`Migrations: unapplied` 오류가 나면 scheduler에서 migrate하지 말고 Render deploy의
기존 `python manage.py migrate` 절차를 먼저 확인한다.

## 향후 schedule 활성화 예시

여러 차례의 one-shot 검증과 source 정책 재검토가 끝난 뒤에만 아래 trigger를
workflow의 `on` 아래에 추가한다. 지금 workflow에는 추가하지 않는다.

```yaml
schedule:
  - cron: "0 9,21 * * *"
    timezone: "Asia/Seoul"
```

이는 서울 시간 09:00, 21:00 실행 예시다. 활성화 전 source별 request budget,
이용 약관, robots 정책, rate limit, 데이터 정확성을 다시 검토해야 한다.

## 중복 및 실패 안전성

- listing은 `market_source + external_id` unique constraint와 upsert로 중복을 막는다.
- source별 command는 별도 transaction 경계에서 실행된다. 한 source의 예상하지 못한
  실패는 그 source를 rollback하지만, 나머지 source 실행은 계속한다.
- 정책상 비활성 source는 정상 `SKIPPED`이며 workflow 실패가 아니다.
- 예상하지 못한 source 오류가 하나라도 있으면 모든 source 시도 후 non-zero로 끝난다.
- 값이 완전히 같은 PriceHistory snapshot은 5분 안에 재실행된 경우 재사용한다.
  5분이 지난 정상적인 시간별/일별 history는 계속 생성한다.
- 공통 request safety 기본값은 timeout 10초, 최대 1 page, 20 items, retry 0회,
  request budget 1회다. 이는 향후 실제 collector가 명시적으로 적용할 한도다.

## Render Free PostgreSQL 주의사항

Render의 무료 PostgreSQL은 영구 운영 DB로 가정하면 안 된다. 현재 공식 안내 기준으로
무료 DB는 생성 후 30일에 만료되며, 만료 후 유료 전환 유예 기간이 지나면 삭제될 수
있다. 저장 용량은 1GB이고 backup과 point-in-time recovery를 지원하지 않는다.

이번 단계에서는 자동 backup, 자동 migration, DB 이전 기능을 추가하지 않는다.
운영 지속 전에 장기 보존과 backup을 지원하는 managed PostgreSQL 또는 당시 이용 가능한
무료 DB 대안을 다시 비교하는 작업을 TODO로 남긴다.
