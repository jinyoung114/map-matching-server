# Shuttle Map Matching Server

셔틀버스의 GPS 데이터를 도로망에 매칭하여 위치를 보정하고,
결과를 Firebase Realtime Database에 저장하는 FastAPI 기반 서버입니다.

GPS 오차로 인해 버스 위치가 도로를 벗어나거나 급격히 튀는 문제를 줄이기 위해,
GPS 전처리와 슬라이딩 윈도우 기반 Viterbi 알고리즘을 적용합니다.

## 주요 기능

- **GPS 전처리**: 이동 속도와 방향 등을 이용한 이상치 필터링
- **도로망 기반 맵매칭**: GPS 관측값을 도로망의 간선 위 좌표에 매칭
- **연속 경로 추정**: 최근 GPS 데이터를 활용하는 Viterbi 알고리즘 적용
- **버스별 상태 관리**: 버스마다 전처리 상태와 GPS 버퍼를 독립적으로 관리
- **운행 관리**: 운행 시작 시 상태 초기화, 운행 종료 시 상태 및 Firebase 위치 삭제
- **Firebase 연동**: 매칭된 좌표와 현재 노드, 운행 상태 저장
- **데이터 재생 및 시각화**: 합성 GPS 데이터로 요청을 재현하고 결과를 지도에서 비교

## 처리 흐름

GPS 수신
→ 이상치 필터링
→ 슬라이딩 윈도우 구성
→ Viterbi 경로 추정
→ 현재 매칭 좌표 및 간선 정보 반환
→ Firebase 위치 갱신

전처리를 통과한 GPS가 3개 이상 쌓이면 맵매칭을 시작합니다.
기본 윈도우 크기는 24개이며, 윈도우가 채워지면 앞쪽 결과부터 확정합니다.

## 기술 스택

- API: Python, FastAPI, Uvicorn
- 데이터 처리: NumPy, pandas
- 도로망 및 공간 연산: NetworkX, scikit-learn, geopy
- 위치 데이터 저장: Firebase Realtime Database
- 결과 시각화: Folium

## 프로젝트 구조

```text
map-matching-server/
├── main.py                       # API 및 운행 상태 관리
├── requirements.txt
├── convert_data_ids.py           # 데이터 ID 변환
├── services/
│   ├── map_matching_service.py   # GPS 처리 및 맵매칭
│   └── firebase_service.py       # Firebase 연동
├── src/
│   ├── config.py                 # 데이터 경로 및 알고리즘 설정
│   ├── preprocessing.py          # GPS 전처리
│   ├── road_network.py           # 도로망 구성
│   ├── transition.py             # 상태 전이 계산
│   ├── viterbi.py                # Viterbi 경로 추정
│   ├── pipeline.py               # 데이터 처리 파이프라인
│   ├── visualization.py          # 시각화
│   └── utils.py
├── scripts/
│   ├── replay_gps_csv.py         # CSV 기반 GPS 요청 재생
│   └── visualize_replay_result.py
└── data/                         # 도로망 및 합성 GPS 데이터
```

## 실행 방법

### 1. 저장소 다운로드 및 패키지 설치

```bash
git clone https://github.com/jinyoung114/map-matching-server.git
cd map-matching-server

python -m venv .venv
```

가상환경 활성화:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

패키지 설치:

```bash
pip install -r requirements.txt
pip install firebase-admin requests folium
```

### 2. Firebase 설정

Firebase 서비스 계정 키를 아래 경로에 배치합니다.

```text
firebase/firebase-service-account.json
```

`services/firebase_service.py`의 `DATABASE_URL`을
사용할 Firebase Realtime Database 주소로 설정합니다.

서비스 계정 키는 저장소에 커밋하지 않습니다.

### 3. 서버 실행

```bash
uvicorn main:app --reload
```

- 서버: http://127.0.0.1:8000
- API 문서: http://127.0.0.1:8000/docs

## API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/` | 서버 응답 확인 |
| GET | `/health` | 서버 내 활성 버스 목록 확인 |
| POST | `/trip/start` | 운행 시작 및 버스 상태 초기화 |
| POST | `/mapmatch` | GPS 입력 및 맵매칭 결과 반환 |
| POST | `/trip/end` | 운행 종료 및 위치 데이터 삭제 |
| POST | `/firebase/test` | Firebase 테스트 데이터 쓰기 |

### 운행 시작

`POST /trip/start`

```json
{
  "bus_id": "bus_001",
  "route_id": "route_001"
}
```

### GPS 전송

`POST /mapmatch`

```json
{
  "bus_id": "bus_001",
  "route_id": "route_001",
  "lat": 37.12345,
  "lon": 127.12345,
  "heading": 90.0,
  "timestamp": "2026-11-26T09:00:00+09:00"
}
```

좌표는 요청 형식 예시이며, 실제 테스트에서는 제공된 도로망에 해당하는
GPS 좌표를 사용합니다. `heading`은 생략할 수 있습니다.

맵매칭 요청 전에 동일한 버스 ID로 운행을 시작해야 합니다.

| 응답 status | 의미 |
| --- | --- |
| `warming` | 맵매칭에 필요한 GPS 데이터 수집 중 |
| `skipped` | 전처리 과정에서 GPS 데이터 제외 |
| `matched` | 맵매칭 처리 완료 |
| `error` | 운행 미시작 또는 잘못된 타임스탬프 등 |

### 운행 종료

`POST /trip/end`

```json
{
  "bus_id": "bus_001",
  "route_id": "route_001"
}
```

## GPS 재생 및 결과 시각화

서버 실행 후, CSV에 포함된 버스 ID와 노선 ID로
`/trip/start`를 호출한 다음 실행합니다.

```bash
python scripts/replay_gps_csv.py bus_001
# 먼저 visualize_replay_result.py의 RESULT_CSV를 재생 결과 경로로 수정합니다.
python scripts/visualize_replay_result.py
```

생성되는 파일:

- `data/아산역/replay_mapmatch_results_bus_001.csv`: bus_001 처리 결과
- `data/replay_mapmatch_visualization.html`: 원본 GPS, 합성 정답 경로, 매칭 결과 비교 지도

## 현재 구현 범위

- route_001(아산역), route_002(천안터미널역)는 각각 별도의 도로망 CSV를 사용합니다.
- 매칭 좌표는 도로 간선 위에 투영된 위치이며, current_node는 호환성을 위한 간선 도착 노드입니다.
- 버스별 상태는 서버 메모리에 저장되므로 서버를 재시작하면 초기화됩니다.
- 상태 공유가 구현되어 있지 않으므로 단일 워커 실행을 기준으로 합니다.

## 정류장 도착 예상 시간 (ETA)

최근 이동 속도와 남은 노선 거리로 정류장별 도착 시간을 계산합니다. 설정, 모의 운행 및 검증 방법은 [ETA.md](ETA.md)를 참고하세요.

CSV 재생 시 bus_001 입력 파일은 data/아산역/multi_bus_test_001.csv입니다. 이 파일은 Git 제외 대상이므로 별도 준비가 필요합니다. bus_002는 천안터미널역 노선의 합성 GPS 파일을 사용합니다.
