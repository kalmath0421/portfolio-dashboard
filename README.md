# 법인 투자 포트폴리오 대시보드

학원 법인 유보금 운용 계좌(IBK WINGS, 농협 나무) 통합 모니터링 로컬 대시보드.

> ⚠️ 본 도구는 **모니터링 보조용**입니다. 실제 법인세 신고는 반드시 세무사 검토를 거치십시오.

## 요구 환경

- Python 3.11+
- Windows 11 (개발 타겟) — macOS/Linux도 동작
- RAM 4GB+ 권장

## 설치 (Windows 11)

PowerShell:

```powershell
cd portfolio-dashboard
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

## 실행 — 두 가지 방식

### A) 콘솔 창과 함께 (간단, 일반)
**`run.bat` 더블클릭** — 검은 콘솔 창이 뜨고 브라우저가 자동으로 열립니다.
종료: 콘솔 창을 닫으면 서버도 같이 꺼집니다.

### B) 창 없이 백그라운드 (원클릭)
**`start_silent.vbs` 더블클릭** — 콘솔 창 없이 백그라운드로 실행되고 브라우저만 열립니다.
종료: **`stop.bat` 더블클릭**.

브라우저 주소: `http://localhost:8501`

## 바탕화면 아이콘으로 원클릭 실행

1. `start_silent.vbs` 파일을 마우스 **오른쪽 클릭** → **"바로가기 만들기"**
2. 만들어진 `start_silent.vbs - 바로가기` 를 **바탕화면으로 끌어다 놓기**
3. 이름을 `포트폴리오` 등으로 변경
4. **(선택) 아이콘 변경**:
   - 바로가기 우클릭 → **속성** → **아이콘 변경** → **찾아보기**
   - `%SystemRoot%\System32\imageres.dll` 입력 후 마음에 드는 아이콘 선택
   - 또는 `.ico` 파일을 인터넷에서 받아 지정 가능 (예: 차트·금융 테마)
5. (선택) `stop.bat` 도 같은 방법으로 바탕화면 바로가기 만들기

이제 **바탕화면 아이콘 더블클릭 → 대시보드 자동 실행** 끝.

## 시작 프로그램으로 등록 (PC 켜면 자동 실행)

원하시면:
1. `Win + R` → `shell:startup` 입력 → 시작 프로그램 폴더가 열림
2. `start_silent.vbs` 의 바로가기를 그 폴더에 넣기
3. 다음부터 PC 부팅 시 대시보드가 자동으로 떠 있음 (브라우저는 매번 안 뜨도록 [start_silent.vbs](start_silent.vbs) 마지막 줄을 주석 처리하면 됨)

## 첫 실행 체크리스트

1. **KODEX CD금리액티브 티커 입력**
   사이드바 → `⚙️ 종목 관리` → 상단 경고 박스에서 6자리 티커 입력.
2. **세금 규칙 확인**
   `config/tax_rules.yaml` 을 세무사와 함께 검토하고 값을 갱신.
3. **CSV 입력 폴더 확인**
   `data/inbox/ibk/` (IBK WINGS), `data/inbox/nh/` (농협 나무) — Phase 2에서 사용.

## 폴더 구조

```
portfolio-dashboard/
├── app.py                    # Streamlit 진입점
├── pyproject.toml
├── config/
│   └── tax_rules.yaml        # 세무사 확인 기준 세율/규칙
├── data/
│   ├── portfolio.db          # SQLite (gitignore)
│   └── inbox/                # 증권사 CSV 떨구는 폴더
│       ├── ibk/
│       └── nh/
├── src/
│   ├── db.py                 # DB 초기화/연결 + 시드 데이터
│   ├── importers/            # IBK / 농협 CSV 파서 (Phase 2)
│   ├── prices.py             # 시세 조회 (Phase 2)
│   ├── tax.py                # 세금 계산 로직 (Phase 4)
│   ├── analytics.py          # 수익률·기여도 계산 (Phase 3)
│   └── views/                # Streamlit 화면들
└── tests/
```

## 개발 단계

- **Phase 1 (현재)** — 뼈대 + 종목 관리 화면 ✅
- Phase 2 — IBK/농협 CSV 임포터 + 시세 조회
- Phase 3 — 요약/계좌별/차트 화면
- Phase 4 — 세금 모듈 + CSV 내보내기
- Phase 5 — README/백업/배치 마무리

## 백업

`data/portfolio.db` 한 파일이 모든 거래/시세 데이터를 보관합니다.

### 즉시 백업 (수동)
**`backup.bat` 더블클릭** → `data/backup/portfolio_YYYYMMDD_HHMMSS.db` 생성.
30일 이전 백업은 자동으로 정리됩니다.

### 자동 백업 (매일 23:30)
1. `register_autobackup.bat` 더블클릭 → Windows 작업 스케줄러에 등록
2. 이후 매일 23:30 에 자동으로 `backup_silent.bat` 실행
3. 해제하려면 `unregister_autobackup.bat`

확인: 작업 스케줄러에서 **"PortfolioDashboardBackup"** 작업으로 확인 가능.

### CLI 옵션
```powershell
python -m src.backup            # 즉시 백업
python -m src.backup --silent   # 출력 없이 (자동 실행용)
python -m src.backup --list     # 백업 목록만 출력
python -m src.backup --keep-days 60   # 보관 기간 60일로 변경
```

## 🔧 데이터 유지하며 소스 업데이트하는 법

> **핵심 원칙**: 데이터(`data/portfolio.db`)와 소스코드(`app.py`, `src/`, `config/`)는 완전히 분리되어 있습니다.
> **`data/` 폴더만 건드리지 않으면 데이터는 절대 사라지지 않습니다.**

### 어떤 폴더가 무엇인지

| 폴더/파일 | 역할 | 업데이트 시 처리 |
|---|---|---|
| `data/portfolio.db` | 입력한 모든 데이터 (계좌·종목·거래·분배금) | **절대 덮어쓰지 말 것** |
| `data/inbox/` | CSV 임포트용 (현재 미사용) | 그대로 둠 |
| `app.py`, `src/` | 코드 — 화면·계산 로직 | 새 버전으로 덮어쓰기 OK |
| `config/tax_rules.yaml` | 세금 규칙 — 본인 수정값 있을 수 있음 | **백업 후** 새 버전 비교 |
| `pyproject.toml` | 의존성 목록 | 덮어쓰기 OK |
| `.venv/` | 가상환경 | 새 의존성 추가됐으면 재설치 |

### 안전 절차 (3분 안에 끝)

```powershell
# 1. 데이터 백업 (안전망)
copy data\portfolio.db data\portfolio.db.backup

# 2. 새 소스 받기 — 두 가지 방식 중 택 1

# 방식 A: 같은 폴더에 덮어쓰기
#   - 새 소스를 압축 해제하거나 git pull
#   - data/ 폴더는 보존됨 (.gitignore 처리되어 있음)

# 방식 B: 새 폴더에 풀고 데이터만 복사
copy 기존폴더\data\portfolio.db 새폴더\data\portfolio.db
copy 기존폴더\config\tax_rules.yaml 새폴더\config\tax_rules.yaml

# 3. 의존성이 추가됐으면 재설치 (run.bat 안에서 자동 처리됨)
.venv\Scripts\activate
pip install -e .

# 4. 정상 동작 확인
streamlit run app.py
# 또는 start_silent.vbs / run.bat 더블클릭
```

### 만약 DB 스키마가 바뀌었다면?

새 소스가 DB 스키마를 변경한 경우, 기존 `data/portfolio.db` 그대로 쓰면 오류가 날 수 있습니다.
이때:

1. **반드시 백업부터** (`portfolio.db.backup`)
2. 변경 내역 확인 — README 또는 CHANGELOG 참조
3. 마이그레이션 스크립트가 제공되면 실행
4. 안 되면 백업으로 즉시 복구

이 프로젝트는 거래·계좌 데이터가 손실되지 않도록 **소스 측에서 절대 자동 삭제하지 않습니다**. `db.initialize()`는 테이블이 없을 때만 생성하고, 기존 데이터는 건드리지 않습니다.

## 면책

- ETF 과세 구분은 세법 개정 가능성이 있어 매년 세무사와 `tax_rules.yaml` 갱신.
- 가격·환율은 공식 소스(yfinance, pykrx)만 사용하며 임의로 만들어내지 않습니다.
- 시세 조회 실패 시 마지막 스냅샷을 사용하고 화면에 경고를 표시합니다.
