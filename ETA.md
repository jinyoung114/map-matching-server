# ETA v1 사용 및 검증

기존 HMM/Viterbi 알고리즘은 그대로 사용하며 `services/eta_service.py`가 결과의 edge_u, edge_v, fraction으로 노선상의 누적 거리를 계산합니다.
기존 busLocations 필드를 유지하면서 `busLocations/{bus_id}/eta`만 추가합니다. RTDB 규칙이나 인증키를 변경할 필요는 없습니다.

## 계산과 한계

- CSV의 seq 순서로 연결된 forward 간선을 사용합니다. 터미널 CSV의 `_reverse` 간선은 direction 값과 무관하게 제외합니다.
- Firebase `routes/{route_id}/directions/outbound/stops` 순서와 `stops` 좌표를 사용합니다. 터미널의 outbound 데이터에는 학교로 돌아오는 구간도 포함됩니다.
- 최근 최대 45초의 노선상 이동 거리 / GPS 시간 차이로 속도를 계산합니다. 최소 3개 위치와 6초의 이동 이력이 필요합니다.
- ETA = 남은 노선 거리 / 추정 속도. 실측 정차 시간이 없어 추가 정차 시간은 0초입니다. 신호, 정차, 교통 상황에 따라 실제 도착과 차이가 납니다.
- 정차, 역방향 이동, 큰 위치 점프, 30초 넘게 갱신되지 않은 GPS는 숫자 예측을 숨깁니다. 학생 앱도 expires_at 이후 숫자를 숨깁니다.
- 다음 회차나 별도의 inbound는 추측하지 않습니다. 새 운행은 반드시 `/trip/start`로 시작합니다.
- 정류장 좌표의 경로 이격은 최대 120m까지만 허용합니다. 현재 학교 출발 지점은 약 49~51m, 터미널 노선의 학교 도착 지점은 약 86m 이격되어 있어 실제 승하차 지점으로 정밀 보정하면 더 좋아집니다.
- `stops_remaining`은 목표 정류장을 포함한 남은 정류장 수입니다.
- 운행 상태는 기존 방식대로 프로세스 메모리에 있으므로 단일 worker로 실행합니다.

## 실행

백엔드 폴더에서 기존 서버를 재시작합니다. 실행 중인 서버가 있으면 해당 터미널에서 Ctrl+C 후 실행합니다.

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

실제 운행은 기존 `/trip/start` 요청을 그대로 사용합니다. simulation의 기본값은 false입니다.
과거 CSV 재생은 테스트용 bus_id로 `/trip/start`에 `"simulation": true`를 명시해야 합니다. 이 모드는 과거 GPS 시간으로 속도를 계산하고 현재 시각을 기준으로 화면 카운트다운을 제공합니다. 학생 앱에 '모의 운행'을 표시합니다. 사용 후 `/trip/end`를 호출합니다.
재생을 너무 빠르게 하면 예상 시간이 재생 속도와 일치하지 않으므로 UI 확인은 GPS 간격에 맞춰 재생합니다.

예시 요청 본문(기존 GPS 재생 전에 호출):

```json
{"bus_id":"eta_test_001","route_id":"route_001","simulation":true}
```

학생 앱에서 정류장을 선택하면 경유 노선별 가장 먼저 도착하는 버스의 `약 N분 N초`와 남은 정류장 수를 표시합니다.

## 자동 검증 (Firebase 데이터 쓰기 없음)

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p test_eta.py -v
```

프론트엔드 폴더:

```powershell
node --test tests/eta.test.mjs
npx expo export --platform ios --output-dir .expo/verify-eta --clear
```

실차 도착 시각과의 오차 측정은 아직 수행하지 않았습니다. 단위 테스트 통과가 실차 ETA 정확도를 보장하지는 않습니다.

2026-11-25 검증: ETA 및 서버 연결 로직 테스트는 HMM 모듈과 Firebase 쓰기를 테스트용 객체로 대체합니다. 두 실제 CSV 노선의 전체 구간을 일정 속도로 진행하는 합성 위치 테스트도 포함합니다. 기존 HMM을 포함한 실제 서버 import는 Windows 응용 프로그램 제어 정책이 SciPy `_batched_linalg` DLL을 차단하여 실패했습니다. 해당 실행 환경 문제를 해결한 후 실제 GPS 재생과 휴대폰 표시를 추가 확인해야 합니다. 보안 정책이나 라이브러리를 임의로 변경하지 않았습니다.
