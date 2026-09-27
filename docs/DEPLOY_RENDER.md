# Render 배포 안내

이 문서는 배포 준비 설정을 설명한다. 현재 저장소에서는 Render 서비스나 PostgreSQL을
실제로 생성하지 않았으며, 존재하지 않는 배포 URL도 코드에 넣지 않았다.

## 구성 요약

- 운영 서버: `gunicorn config.wsgi:application`
- 정적 파일: WhiteNoise + 압축/해시 manifest storage
- 운영 DB: Render PostgreSQL의 `DATABASE_URL`
- 로컬 DB: `DATABASE_URL`이 없으면 기존 `db.sqlite3`
- 빌드: 의존성 설치 → `collectstatic` → `migrate`
- 상태 확인: 인증과 DB 조회가 필요 없는 `GET /health/`

## Dashboard에서 직접 배포하기

1. 준비된 GitHub 저장소의 최신 `main` 브랜치를 확인하고 Render에 가입하거나 로그인한다.
2. **New > PostgreSQL**에서 데이터베이스를 만든다. 리전은 뒤에서 만들 Web Service와
   같게 선택한다.
3. DB 상세 화면의 **Internal Database URL**을 확인한다. 외부에 공개하거나 저장소에
   기록하지 않는다.
4. **New > Web Service**에서 이 저장소를 선택한다.
5. Runtime은 Python, Branch는 배포할 Git 브랜치(일반적으로 `main`)로 지정한다.
6. Build Command를 `./build.sh`로 설정한다.
7. Start Command를 `gunicorn config.wsgi:application`으로 설정한다.
8. Health Check Path를 `/health/`로 설정한다.
9. 아래 표의 환경변수를 Dashboard에서 등록한다.
10. 서비스를 생성하고 첫 빌드 로그에서 패키지 설치, static 수집, migration 완료를
    확인한다.
11. Render가 실제 hostname을 발급하면 `DJANGO_ALLOWED_HOSTS`에 scheme 없이 hostname을
    입력한다.
12. `DJANGO_CSRF_TRUSTED_ORIGINS`에는 같은 주소를 `https://`부터 입력한다.
13. 환경변수 변경 후 재배포한다.
14. 발급된 서비스 주소의 `/health/`, `/`, `/cards/`, `/admin/`을 차례로 확인한다.
15. Dashboard Events와 Logs에서 오류 및 반복 재시작이 없는지 확인한다.

`build.sh`가 배포 빌드 중 `collectstatic`과 `migrate`를 자동 실행하므로 Dashboard에 같은
명령을 중복 등록할 필요는 없다. 로컬 SQLite의 데이터는 자동 복사하지 않는다. 화면
확인용 DEMO 데이터가 필요하면 배포가 끝난 뒤, 아래 관리자 계정 생성과 같은 방식으로
명시적으로 실행한다.

```bash
python manage.py seed_demo_data
```

이 명령은 Django ORM만 사용하므로 PostgreSQL에서도 동작한다. 실제 데이터와 혼동하지
말아야 하며 `build.sh`에서는 자동 실행하지 않는다.

저장소의 `render.yaml`을 이용해 Blueprint로 Web Service 설정을 불러올 수도 있다.
이 파일은 DB를 자동 생성하지 않으며, `sync: false`인 비밀값은 Dashboard에서 직접
입력해야 한다. Python 버전을 별도로 고정하려면 실제 배포 시점에 Render가 지원하는
버전을 확인한 뒤 Dashboard 환경변수나 `.python-version`으로 지정한다.

## 환경변수

| 이름 | 필수 | 값/설명 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | 운영 필수 | 길고 예측 불가능한 새 값. 저장소나 로그에 기록하지 않는다. |
| `DJANGO_DEBUG` | 운영 필수 | `False` |
| `DJANGO_ALLOWED_HOSTS` | 운영 필수 | Render가 실제 발급한 hostname. 쉼표로 여러 개 지정 가능. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 운영 필수 | 실제 origin 전체(`https://` 포함). 쉼표 구분. |
| `DATABASE_URL` | 운영 필수 | Render PostgreSQL의 Internal Database URL. |
| `JUSTTCG_API_KEY` | 해당 기능 사용 시 | 실제 JustTCG 키. 없어도 웹 서비스는 시작된다. |
| `EBAY_CLIENT_ID` | 해당 기능 사용 시 | 실제 eBay Client ID. |
| `EBAY_CLIENT_SECRET` | 해당 기능 사용 시 | 실제 eBay Client Secret. |

`DJANGO_DEBUG=False`인데 `DJANGO_SECRET_KEY`가 없으면 애플리케이션이 명확한 오류로
시작을 중단한다. 운영에서 개발용 기본 키를 실수로 쓰는 것을 막기 위한 동작이다.

## 관리자 계정

Render 요금제에서 Shell을 제공한다면 Web Service의 Shell에서 다음을 실행한다.

```bash
python manage.py createsuperuser
```

무료 Web Service처럼 Shell을 제공하지 않는 요금제라면, PostgreSQL의 External Database
URL을 로컬 터미널의 임시 `DATABASE_URL`로만 설정한 뒤 같은 명령을 실행할 수 있다.
외부 URL을 `.env`, 셸 기록, 문서 또는 저장소에 남기지 말고 작업 후 환경변수를 지운다.
관리자 계정 생성 때문에 빌드 스크립트에 비밀번호를 넣지 않는다.

## 배포 후 확인

- `/health/`가 상태 코드 200과 `{"status":"ok"}`를 반환한다.
- `/`, `/cards/`, 카드 상세와 `/admin/`의 CSS가 정상이다.
- 새 배포 후에도 데이터가 남아 있고 PostgreSQL에 저장된다.
- `DisallowedHost`, CSRF, migration, static manifest 오류가 로그에 없다.
- 필요 시 로컬에서 `DJANGO_DEBUG=False`와 운영 필수값을 임시 지정해
  `python manage.py check --deploy`를 다시 실행한다.
- 커스텀 도메인의 모든 하위 도메인이 HTTPS인지 확정하기 전에는 HSTS
  `includeSubDomains`와 preload를 켜지 않는다. 이 때문에 배포 검사에 두 보안 권고가
  남는 것은 의도한 상태다.
- 현재 이메일 기능은 없고 운영 설정은 공급자 중립적인 SMTP 백엔드다. 이메일 기능을
  추가할 때 실제 SMTP host/port/TLS/인증 환경변수를 별도로 구성한다.
- 일반 Django 오류는 Render의 Web Service **Logs**에서 확인한다. 별도 logging
  프레임워크는 사용하지 않으며 API 키, Secret, Authorization header를 출력하지 않는다.
- `DEBUG=False`에서는 기존 `404.html`과 `500.html`이 상세 예외나 민감정보 없이
  사용자용 오류 화면을 제공한다.

## 무료 플랜 주의사항

Render 무료 Web Service의 파일 시스템은 영구 저장소가 아니다. 따라서 운영 데이터에
SQLite를 사용하면 재시작이나 재배포 때 데이터가 사라질 수 있어 PostgreSQL을 사용해야
한다. 무료 서비스는 유휴 상태에서 sleep/spin-down되어 첫 요청이 느릴 수 있다.
무료 PostgreSQL은 현재 용량, 만료 기간, 백업 등에 제한이 있으며 장기 영구 운영용으로
간주하면 안 된다. 포트폴리오, 친구 테스트, 기능 검증 용도로만 취급한다. 무료 정책은
변경될 수 있으므로 실제 생성 직전에 Render 공식 문서를 다시 확인한다.

## 로컬 개발 유지

로컬에서는 `DATABASE_URL`을 비워 두면 SQLite를 그대로 쓴다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Render 설정을 추가해도 기존 로컬 개발 흐름과 DEMO 명령은 바뀌지 않는다.
