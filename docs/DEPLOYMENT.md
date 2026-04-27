# NAS 배포 가이드 & 진행 기록

> 2026-04-26 1차 배포 완료. 이 문서는 배포 절차 + 현재 상태 + 미완료 항목 정리.

## 한눈에 보는 현재 배포

NAS 한 대에 **두 인스턴스가 동시에 운영 중**. 같은 코드베이스(같은 이미지)에서
환경변수만 다르게 띄움.

| 항목 | 인스턴스 1 (법인) | 인스턴스 2 (아란) |
|---|---|---|
| 호스트 | 시놀로지 NAS (`synol918`, `192.168.50.20`) | 동일 |
| 컨테이너 경로 | `/volume1/docker/portfolio-dashboard/` | `/volume1/docker/portfolio-dashboard-aran/` |
| 컨테이너 이름 | `portfolio-dashboard` | `portfolio-dashboard-aran` |
| 내부 포트 | `8501` | `4444 → 8501` |
| 프로파일 | `corp` (기본) | `personal` |
| 외부 URL | `https://portfolio.kalmath.i234.me:4443` | `https://aran.kalmath.i234.me:4443` |
| 인증서 | Let's Encrypt (`portfolio.kalmath.i234.me`) | Let's Encrypt (`aran.kalmath.i234.me`) |
| DB 위치 | `data/portfolio.db` (호스트 볼륨) | 동일 (각자 별도 폴더) |

## 오늘 한 일 요약 (2026-04-26)

### 코드 개선 (PC 작업)

1. 매매 거래 입력 페이지의 **위젯 키 중복 버그** 수정 (`StreamlitDuplicateElementKey`)
2. **이모지/Material Symbols 폰트** Google Fonts 웹폰트로 강제 로드
3. 요약 페이지에 **🔄 시세 갱신 버튼** 추가
4. **매수 수수료**를 원가·실현손익에 반영 (잔량 비례 소진 로직 + 테스트 3개)
5. **계좌별 기본 매매 수수료율** 컬럼 추가 (DB 마이그레이션 + UI 안내 캡션)
6. **모바일 레이아웃** — 사이드바 자동 접힘, 가로 오버플로우 방지, 메트릭 폰트 축소

### 인프라 셋업 (NAS)

1. Container Manager / Docker 환경 확인
2. 코드를 `wget`으로 다운로드 (private 리포 → public 전환 후 가능)
3. `Dockerfile`, `docker-compose.yml`, `.dockerignore` 추가 후 빌드 & 실행
4. ASUS 공유기 포트포워딩 추가 (4443, 80)
5. DSM 리버스 프록시: `https://portfolio.kalmath.i234.me:4443` → `http://localhost:8501` + WebSocket 헤더
6. Let's Encrypt 인증서 발급 + 리버스 프록시에 매핑
7. 폰 외부 접속 검증 (모바일 데이터로 정상 로드)

## 미완료

### ~~1) Material Symbols 아이콘~~ ✅ 해결 (2026-04-26)
모바일에서 사이드바 토글 버튼이 `keyboard_double_arrow_right` ligature 텍스트로 노출되던 문제. 원인은 `style.py`의 글로벌 `font-family !important` 룰이 아이콘 element의 Material Symbols 폰트까지 덮어버린 것. 해결: 아이콘 element selector(`[data-testid="stIconMaterial"]`, `.material-symbols-*` 등)에 명시적으로 `font-family: 'Material Symbols Rounded'` + `font-feature-settings: 'liga'` 강제 지정.

### ~~2) 두 번째 사용자 인스턴스~~ ✅ 해결 (2026-04-27)
"아란의 포트폴리오" 인스턴스 추가 완료. 환경변수(`DASHBOARD_PROFILE=personal`)로
같은 코드베이스에서 법인 모드/개인 모드를 분기하도록 리팩토링하고 두 번째 컨테이너
띄움. 실제 적용된 값:
- 폴더: `/volume1/docker/portfolio-dashboard-aran/`
- 컨테이너명: `portfolio-dashboard-aran`
- NAS 내부 포트: `4444 → 8501`
- 외부 URL: `https://aran.kalmath.i234.me:4443` (4443 공유 + DSM 리버스 프록시 호스트네임 분기)
- 인증서: Let's Encrypt (`aran.kalmath.i234.me`, 만료 2026-07-26)
- compose 파일: `docker-compose.aran.yml` (리포에 커밋, 그대로 복사 후 사용)
- ASUS 추가 작업 ❌ (4443/80 기존 포트포워딩 그대로 활용)

### 3) 보안 — 컨테이너 인증 없음
- DSM `admin` 계정에 강력한 비밀번호 + 2FA 적용
- 컨테이너 자체엔 인증 0단계 → URL만 알면 누구나 열람·수정 가능
- 두 도메인 다 노출 상태 (`portfolio.kalmath.i234.me:4443`, `aran.kalmath.i234.me:4443`)
- **다음 세션 후보 옵션 A — 앱 자체 비밀번호 게이트 (10분)**:
  - `DASHBOARD_PASSWORD` 환경변수 + `src/auth.py` 모듈 (st.text_input + session_state)
  - docker-compose 두 인스턴스에 각각 다른 비번 환경변수
  - 강도: 봇/우연한 접속 차단 충분, 본격 해커엔 무리
- 더 강력한 옵션 (장기):
  - Nginx 사이드카 + Basic Auth (사이드카 컨테이너 추가)
  - DSM 로그인 포털 게이트 (DSM 버전별 가능 여부 다름)
  - VPN (WireGuard/Tailscale) — 가장 강력하지만 폰에 VPN 앱 필요

### 4) 폰트 미세조정 — 숫자 자간/베이스라인
- 한글-숫자 fallback 메트릭 차이 + 글로벌 `letter-spacing: -0.01em` 결합으로
  표·메트릭·입력란의 숫자가 한 글자씩 흩어져 보이고 베이스라인이 살짝 어긋남
- 진단 완료: Pretendard 자체는 잘 로드 (CDN 문제 X)
- **해결안**: `font-variant-numeric: tabular-nums lining-nums` +
  `font-feature-settings: 'tnum'` + `letter-spacing: 0` 을 표/메트릭/입력 selector
  에만 적용 (Pretendard tabular figures 지원함)
- 운영 영향 없는 미적 이슈 — 우선순위 낮음

### 5) 모바일 메트릭 라벨 잘림
- 좁은 화면에서 사이드바의 활성 계좌 라벨이나 메트릭 라벨이 "총...", "투..." 처럼 잘림
- 폰트 사이즈 한 단계 더 축소 또는 1줄→2줄 wrap 허용으로 해결 예상

### 6) NAS GitHub SSH 키 셋업
- 현재 wget+tar 방식 (private↔public 토글 필요)
- NAS의 admin 계정에 SSH 키 만들고 GitHub에 등록하면 `git pull` 한 줄로 끝
- 단, admin 홈 디렉토리가 없어 `~/.ssh` 위치를 명시적으로 지정해줘야 함
  (또는 다른 사용자로 키 셋업)

### 7) 향후 Phase
- Phase 2 — IBK/농협 CSV 임포터 + yfinance/pykrx 자동 시세 (과거 시세 백필 포함)
- Phase 3 — 화면 구현 (시세 후 차트/계좌별/요약 강화)
- Phase 4 — 세금 모듈 마무리 + CSV 내보내기 (corp 인스턴스 전용)

### 8) "초기 보유분" 폼에 수수료 필드 추가
- 현재 `📦 초기 보유분` 폼은 평균단가·수량만 받고 수수료 입력란이 없음
  (`src/views/transactions.py` 라인 85의 안내: "수수료 입력란이 없으므로 평균단가에
  반영해 입력하세요")
- 사용자가 IBK 어플의 평균단가를 그대로 입력하면 fee=0 으로 저장 → 우리 투자원금이
  IBK 어플 투자원금 대비 약 0.1% 작게 나옴 (수수료율과 일치)
- **해결**: 초기 보유분 폼에도 수수료 number_input 추가하고
  `db.add_initial_position` 에 `fee` 파라미터 전달.
- 30분 작업. DB 스키마 변경 없음 (`transactions.fee` 컬럼은 이미 존재).
- 기존 데이터는 거래 편집 또는 삭제 후 재입력 또는 그대로 둠 (0.1% 차이는 회계상 무시 가능).

### 9) 차트 가로축 — 과거 시세 백필 기능
- 현재 차트는 `🔄 시세 갱신` 누른 날 이후의 스냅샷만 그림
- 거래 일자(과거)부터 지금까지의 평가금액 추이를 보려면 yfinance/pykrx 에서 과거 일별
  종가를 일괄 가져와 `price_snapshots` 에 채우는 백필 기능 필요
- "📥 과거 시세 가져오기" 버튼 1개 추가 (계좌별 or 종목별)
- Phase 2 작업의 자연스러운 일부

### 10) 회계 메트릭 디자인 — 분배금/예수금 처리
- 현재: 평가금액·미실현손익에 분배금 포함 X (별도 메트릭). 예수금은 추적 X.
- 제안:
  - 분배금: **현재대로 분리** (평가금액에 더하면 이중 카운트 위험). 단 "Total Return =
    미실현 + 누적 분배금(세후) + 실현 손익" 같은 별도 메트릭 추가는 유용.
  - 예수금: **추적 추가** (법인 유보금 운용 본 목적상 현금성 자산도 봐야). DB 스키마
    변경 필요 (`accounts` 에 cash_balance 컬럼 또는 `cash_transactions` 별도 테이블).
- 메트릭 구성 제안:
  `[ 총 자산 ] [ 종목 평가금액 ] [ 예수금 ] [ 미실현 손익 ]`
- 약 1.5시간 작업 (DB 스키마 + 입력 UI + 메트릭 + 마이그레이션 + 테스트)

## 운영 절차

### 코드 업데이트 반영
PC에서 `git push origin main` 한 뒤, NAS SSH:
```bash
cd /volume1/docker/portfolio-dashboard
sudo wget https://github.com/kalmath0421/portfolio-dashboard/archive/refs/heads/main.tar.gz -O /tmp/portfolio.tar.gz
sudo tar -xzf /tmp/portfolio.tar.gz --strip-components=1
sudo docker compose up -d --build
```

### 컨테이너 상태 확인
```bash
sudo docker ps
sudo docker logs portfolio-dashboard --tail 30
```

### 데이터 백업
DSM Hyper Backup 또는 BTRFS 스냅샷으로 `/volume1/docker/portfolio-dashboard/data/` 보호.

## 두 번째 인스턴스 추가 절차 (실제 검증된 절차)

리포지토리에 `docker-compose.aran.yml` 이 미리 포함돼 있어 복사 한 번으로 끝.
새 인스턴스를 추가하려면 컨테이너명·외부 도메인만 바꿔서 같은 패턴을 따르면 된다.

```bash
sudo mkdir -p /volume1/docker/portfolio-dashboard-aran
cd /volume1/docker/portfolio-dashboard-aran
sudo wget https://github.com/kalmath0421/portfolio-dashboard/archive/refs/heads/main.tar.gz -O /tmp/aran.tar.gz
sudo tar -xzf /tmp/aran.tar.gz --strip-components=1
sudo mkdir -p data config
sudo cp docker-compose.aran.yml docker-compose.yml
sudo docker compose up -d --build
```

`docker-compose.aran.yml` 안에서 컨테이너명·포트·환경변수가 미리 셋업돼 있다:
- `container_name: portfolio-dashboard-aran`
- `ports: 4444:8501`
- `DASHBOARD_PROFILE=personal`
- `DASHBOARD_TITLE=아란의 포트폴리오`

다음으로 DSM에서:
1. **제어판 → 로그인 포털 → 고급 → 리버스 프록시 → 생성**
   - 소스: `HTTPS aran.kalmath.i234.me:4443`
   - 대상: `HTTP localhost:4444`
   - 사용자 정의 머리글 → 만들기 → WebSocket
2. **제어판 → 보안 → 인증서 → 추가 → Let's Encrypt**
   - 도메인: `aran.kalmath.i234.me`
3. **인증서 → 설정** 에서 `aran.kalmath.i234.me:4443` ↔ 새 인증서 매핑 (보통 자동).

ASUS 공유기 작업 불필요 — 4443/80 포트포워딩이 이미 첫 인스턴스 셋업 시 추가됐고
새 도메인은 ipTime 와일드카드 DDNS로 같은 공인 IP에 매핑됨.

세 번째 사람을 더 추가하려면 `aran` → 새 이름으로 바꿔 똑같이.

## 트러블슈팅 표

| 증상 | 원인 | 조치 |
|---|---|---|
| "Connecting..." 무한 로딩 | WebSocket 헤더 누락 | 리버스 프록시 → 사용자 정의 머리글에 WebSocket 추가 |
| 502 Bad Gateway | 컨테이너 다운 | `sudo docker logs portfolio-dashboard` 확인 |
| 인증서 경고 | 매핑 누락 | 제어판 → 보안 → 인증서 → 설정에서 도메인↔인증서 매핑 |
| Let's Encrypt 발급 실패 | 외부 80 미포워딩 | ASUS 공유기에 80 → NAS:80 포워드 추가 |
| 모바일 가로 스크롤 | wide 레이아웃 | `style.py`의 모바일 미디어 쿼리 확인 |
| 빌드 OOM | NAS RAM 부족 | swap 확장 또는 lighter 베이스 이미지 |

## 인프라 정보 (참고)

- 라우터: ASUS, 게이트웨이 `192.168.50.1`, 서브넷 `192.168.50.0/24`
- DDNS: ipTime `i234.me` 와일드카드 (모든 서브도메인이 같은 공인 IP로 매핑됨 — `222.111.9.112`)
- DSM 자체는 443 점유 중이라 새 서비스에 비표준 포트(`4443`) 사용
- WordPress가 `:8888 → :80`으로 별도 운영 중

## 멀티유저 확장에 대한 비고

진짜 멀티유저(같은 인스턴스 내 사용자별 데이터 분리)는 큰 리팩토링 필요:
- DB 스키마에 `user_id` 컬럼 전반적 추가
- 로그인 화면, 세션별 필터링
- 마이그레이션 스크립트

2명 정도면 **컨테이너 분리(인스턴스 2개)** 가 비용 대비 압도적으로 효율적. 5명 이상 되면 그때 멀티유저 리팩토링 고려.

## 📝 회계 노트 — 환율 환산 방식 (한국 증권사 어플 vs 우리 시스템)

운영 중 미래에셋·NH·삼성 등 한국 증권사 어플과 **매입원가가 5~10% 차이**나는
경우가 흔하다. 이는 **데이터 오류가 아니라 회계 방식의 의도된 차이**.

### 두 방식 비교

| 항목 | 우리 시스템 | 한국 증권사 어플 |
|---|---|---|
| 매입원가 환산 | **매수 시점 환율** (거래 입력 시 `fx_rate`) | **현재 환율 통일** (모든 USD 매입금액에 동일 환율 적용) |
| 평가금액 환산 | 현재 환율 | 현재 환율 |
| 미실현 손익 의미 | **USD 변동 + 환차익** (진짜 KRW 운영 성과) | **USD 변동만** (종목 자체 수익) |
| 회계 정석 | ✅ cost basis 정확 — 세무·환차손익 추적 가능 | ❌ 단순 표시용 |

### 예시 — TSLA 44주, 매수가 $289.687, 매수 시점 환율 1,345, 현재 환율 1,483

```
우리 시스템
  매입원가 = 44 × $289.687 × 1,345.45  = 17,148,880원  ← 실제 환전 들어간 KRW
  평가금액 = 44 × (현재 USD가) × 1,483
  미실현    = 평가 - 17,148,880        ← USD 가격 변동 + 환차익 포함

미래에셋 어플
  매입원가 = 44 × $289.687 × 1,483    = 18,901,384원  ← 단순 환산 (옛 환율 무시)
  평가금액 = 44 × (현재 USD가) × 1,483
  미실현    = (현재가 - $289.687) × 44 × 1,483  ← USD 변동만
```

매수 시점(1,345)에서 현재(1,483)까지 USD 강세된 만큼이 우리 미실현 손익에
자동 누적되어 있고, 어플은 그 환차익을 매입원가에 흡수시켜 안 보이게 함.

### 미국 주식 보유 한국인 투자자에게 의미

미국 주식 + 환율 변동이 KRW 기준 수익에서 큰 비중을 차지한다. 환차익이
자동으로 미실현 손익에 잡히는 우리 방식이 **실제 통장에 들어올 금액에 더 가깝다**.
어플의 수익률은 "USD 기준 종목 자체"만 보여주므로 KRW 운영자에겐 정보 부족.

### 입력 데이터 검증 — 차이가 진짜 환율 차이인지 확인

수량과 USD 매입가는 항상 어플과 일치해야 정상. KRW 매입원가만 차이나면 환율
방식이 원인. 빠른 검증:

```
어플 KRW 매입원가 ÷ (수량 × USD 매입가) ≈ 통일 환율 (보통 현재 환율)
```

종목별로 이 값이 거의 같으면(예: 모두 ~1,483) 어플이 통일 환율을 쓴다는 증거.
값이 들쭉날쭉하거나 우리 입력 환율과 다르게 일관되면 입력 오류 의심.

### 어플과 100% 일치시키고 싶다면 (비추천)

모든 거래의 `fx_rate`를 현재 환율로 변경하면 우리 매입원가도 어플과 같아진다.
다만:
- 매수 시점 환율 정보 손실
- 환차익이 미실현 손익에서 사라짐 (어플처럼 USD 수익만 표시됨)
- 회계 부정확

**기본 권장: 그대로 둠.** 어플의 매입원가는 표시용 환산값이고, 우리 값이
실제 cost basis 다.
