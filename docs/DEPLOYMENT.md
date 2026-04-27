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
- Phase 2 — IBK/농협 CSV 임포터 + yfinance/pykrx 자동 시세
- Phase 3 — 화면 구현 (시세 후 차트/계좌별/요약 강화)
- Phase 4 — 세금 모듈 마무리 + CSV 내보내기 (corp 인스턴스 전용)

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
