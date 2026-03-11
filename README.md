# Incident Log Service — MSA 전환 가이드

## 아키텍처 구조

```
외부 트래픽
     │
     ▼
┌─────────────────────────────────────┐
│          Ingress (Nginx)            │  incident.yourdomain.com
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│           API Gateway               │  :8000
│  - JWT 검증                         │
│  - X-User-* 헤더 주입               │
│  - 서비스 라우팅                     │
└──┬──────┬──────┬──────┬─────────────┘
   │      │      │      │
   ▼      ▼      ▼      ▼
┌──────┐ ┌────────────┐ ┌───────┐ ┌──────────┐
│Auth  │ │ Incident   │ │ Board │ │Frontend  │
│:8001 │ │ :8002      │ │ :8003 │ │ :8004    │
│      │ │            │ │       │ │          │
│users │ │incidents   │ │posts  │ │Jinja2 UI │
│  DB  │ │  logs DB   │ │  DB   │ │(세션쿠키)│
└──────┘ └────────────┘ └───────┘ └──────────┘
```

## 서비스별 역할

| 서비스 | Port | DB | 역할 |
|--------|------|----|------|
| `api-gateway` | 8000 | 없음 | JWT 검증 + 라우팅 |
| `auth-service` | 8001 | auth_db (users) | 회원가입/로그인/토큰발급 |
| `incident-service` | 8002 | incident_db (incidents, incident_logs) | Incident CRUD + Log |
| `board-service` | 8003 | board_db (posts) | 게시판 CRUD |
| `frontend-service` | 8004 | 없음 | Jinja2 UI 렌더링 |

## 모놀리스 → MSA 주요 변경사항

### 인증 방식
- 변경 전: Flask `session` (서버 세션 공유)
- 변경 후: JWT 토큰 (stateless, 서비스 간 공유 불필요)
  - 브라우저: 세션 쿠키에 JWT 저장 (frontend-service)
  - API 호출: `Authorization: Bearer <token>` 헤더

### DB 분리
- 변경 전: 단일 DB (users, incidents, incident_logs, posts 전부)
- 변경 후: 서비스별 독립 DB
  - `auth_db`: users
  - `incident_db`: incidents, incident_logs
  - `board_db`: posts (user FK 제거 → username 비정규화)

### 서비스 간 통신
- API Gateway가 JWT 검증 후 `X-User-Id`, `X-User-Name`, `X-User-Role` 헤더 주입
- 각 서비스는 헤더만 읽으면 됨 (auth-service 직접 호출 불필요)

---

## 배포 순서

### 1. 사전 준비
```bash
# Nginx Ingress Controller 설치
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/baremetal/deploy.yaml

# Namespace 생성
kubectl apply -f k8s/namespace.yaml
```

### 2. Secret / ConfigMap 적용
```bash
# Secret 수정 후 적용
vi k8s/configmap-secret.yaml   # DB URL, JWT_SECRET 등 실제값으로 변경
kubectl apply -f k8s/configmap-secret.yaml
```

### 3. 서비스 배포 (순서 중요)
```bash
# auth → incident → board → frontend → gateway 순서
kubectl apply -f k8s/auth/deployment.yaml
kubectl apply -f k8s/incident/deployment.yaml
kubectl apply -f k8s/board/deployment.yaml
kubectl apply -f k8s/frontend/deployment.yaml
kubectl apply -f k8s/gateway/deployment.yaml
```

### 4. 배포 확인
```bash
kubectl get pods -n incident
kubectl get svc  -n incident
kubectl get ingress -n incident
```

---

## GitHub Actions 설정

Repository Settings > Secrets and variables > Actions 에 아래 추가:

| Secret 이름 | 값 |
|-------------|-----|
| `REGISTRY_URL` | Docker Registry URL (예: `ghcr.io/yourorg`) |
| `REGISTRY_USERNAME` | Registry 로그인 ID |
| `REGISTRY_PASSWORD` | Registry Token / PW |
| `KUBECONFIG_DATA` | `cat ~/.kube/config \| base64` 결과값 |

### 배포 흐름
```
git push → main
     │
     ▼
detect-changes (변경된 서비스 감지)
     │
     ├─ auth 변경?     → build-auth     → kubectl set image
     ├─ incident 변경? → build-incident → kubectl set image
     ├─ board 변경?    → build-board    → kubectl set image
     ├─ frontend 변경? → build-frontend → kubectl set image
     └─ gateway 변경?  → build-gateway  → kubectl set image
```

**변경된 서비스만 빌드/배포** → 불필요한 재시작 없음

---

## 로컬 개발 (docker-compose)

```yaml
# docker-compose.yml (참고용)
version: "3.9"
services:
  auth-service:
    build: ./auth-service
    ports: ["8001:8001"]
    environment:
      DATABASE_URL: sqlite:///auth.db
      JWT_SECRET: local_dev_secret

  incident-service:
    build: ./incident-service
    ports: ["8002:8002"]

  board-service:
    build: ./board-service
    ports: ["8003:8003"]

  frontend-service:
    build: ./frontend-service
    ports: ["8004:8004"]
    environment:
      AUTH_SERVICE_URL:     http://auth-service:8001
      INCIDENT_SERVICE_URL: http://incident-service:8002
      BOARD_SERVICE_URL:    http://board-service:8003

  api-gateway:
    build: ./api-gateway
    ports: ["8000:8000"]
    environment:
      JWT_SECRET: local_dev_secret
      AUTH_SERVICE_URL:     http://auth-service:8001
      INCIDENT_SERVICE_URL: http://incident-service:8002
      BOARD_SERVICE_URL:    http://board-service:8003
      FRONTEND_SERVICE_URL: http://frontend-service:8004
```

---

## API 엔드포인트 요약

### Auth Service (직접 or Gateway 경유)
| Method | Path | 인증 | 설명 |
|--------|------|------|------|
| POST | `/auth/register` | 불필요 | 회원가입 |
| POST | `/auth/login` | 불필요 | 로그인 → JWT 반환 |
| POST | `/auth/verify` | Bearer | 토큰 검증 |
| GET  | `/auth/users/:id` | Bearer | 사용자 정보 |

### Incident Service (Gateway 경유)
| Method | Path | 권한 | 설명 |
|--------|------|------|------|
| GET  | `/incidents` | 로그인 | 목록 |
| POST | `/incidents` | admin | 생성 |
| GET  | `/incidents/:id` | 로그인 | 상세 |
| PATCH | `/incidents/:id` | admin | 수정 |
| DELETE | `/incidents/:id` | admin | 삭제 |
| GET  | `/incidents/:id/logs` | 로그인 | 로그 목록 |
| POST | `/incidents/:id/logs` | admin | 로그 추가 |

### Board Service (Gateway 경유)
| Method | Path | 권한 | 설명 |
|--------|------|------|------|
| GET  | `/posts` | 로그인 | 목록 |
| POST | `/posts` | 로그인 | 작성 |
| GET  | `/posts/:id` | 로그인 | 상세 |
| PATCH | `/posts/:id` | 작성자/admin | 수정 |
| DELETE | `/posts/:id` | 작성자/admin | 삭제 |
