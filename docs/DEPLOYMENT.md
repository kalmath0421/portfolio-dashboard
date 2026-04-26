# NAS 배포 가이드 & 진행 기록

> 2026-04-26 1차 배포 완료. 이 문서는 배포 절차 + 현재 상태 + 미완료 항목 정리.

## 한눈에 보는 현재 배포

| 항목 | 값 |
|---|---|
| 호스트 | 시놀로지 NAS (`synol918`, `192.168.50.20`) |
| 컨테이너 경로 | `/volume1/docker/portfolio-dashboard/` |
| 컨테이너 이름 | `portfolio-dashboard` |
| 내부 포트 | `8501` (Streamlit) |
| 외부 포트 | `4443` |
| 외부 URL | `https://portfolio.kalmath.i234.me:4443` |
| 인증서 | Let's Encrypt (`portfolio.kalmath.i234.me`) |
| DB 위치 | NAS의 `data/portfolio.db` (호스트 볼륨 마운트) |

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

### 2) 두 번째 사용자 인스턴스
같은 NAS에 컨테이너 하나 더 띄워서 두 번째 사람용 분리 운영.
- 경로: `/volume1/docker/portfolio-dashboard-2/`
- 외부 포트: `4444` (예시)
- 서브도메인: `portfolio2.kalmath.i234.me` (예시)
- 코드 변경 0, `docker-compose.yml`만 수정 (포트·컨테이너명)

### 3) 보안
- DSM `admin` 계정에 강력한 비밀번호 + 2FA 적용
- 컨테이너 자체엔 인증 없음 → DSM 로그인 포털 게이트 추가 검토

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

## 두 번째 인스턴스 추가 절차

```bash
cd /volume1/docker
sudo wget https://github.com/kalmath0421/portfolio-dashboard/archive/refs/heads/main.tar.gz -O /tmp/p2.tar.gz
sudo mkdir -p portfolio-dashboard-2 && cd portfolio-dashboard-2
sudo tar -xzf /tmp/p2.tar.gz --strip-components=1
sudo mkdir -p data
```

`docker-compose.yml` 수정 (컨테이너명·포트 변경):
```yaml
services:
  portfolio:
    container_name: portfolio-dashboard-2
    ports:
      - "4444:8501"
```

빌드 & 실행:
```bash
sudo docker compose up -d --build
```

DSM 리버스 프록시에 항목 추가 (`portfolio2.kalmath.i234.me:4443` → `localhost:4444`), 인증서 별도 발급, ASUS에 4444 포트포워딩.

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
