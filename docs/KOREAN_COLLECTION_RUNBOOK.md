# 국내 시장 수집 운영 Runbook

## 현재 결론

2026-09-29 조사 기준 실제 HTTP collector가 승인된 `READY` source는 없다. 모든 국내 source
command는 안전하게 `SKIPPED (collector disabled)`를 반환한다. Production 데이터를 쓰는
one-shot command를 임의로 만들거나 실행하지 않는다.

## 현재 가능한 검증

로컬에서 외부 HTTP와 DB write 없이 orchestration을 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py update_korean_market --dry-run
```

GitHub Actions의 `Collect market data` workflow도 같은 dry-run만 실행한다. 이미 확인된 수동
workflow는 Django boot, External `DATABASE_URL`, migration 상태, command orchestration을
검증하는 용도다.

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

- Pokémon Korea: metadata 저장, 자동 조회, 이미지 hotlink를 각각 허용하는지 권리자 확인
- KREAM: 자동 조회 허용 여부와 공식적인 데이터 제공 interface 확인
- 번개장터: 자동 조회 허용 여부와 공식/문서화된 상품 interface 확인
- NAVER CardMVK: NAVER와 카페 운영자의 명시적 자동 수집 허가 없이는 진행하지 않음

허가 확인 전에는 실제 데이터 입력 명령이 없다. disabled command를 실제 collector처럼
오해하지 않는다.
