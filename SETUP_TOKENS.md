# GitHub Secrets 등록 가이드
# wo969776-cloud/incident-log-service 기준

## 등록해야 할 Secrets: 2개

| Secret 이름      | 값                          | 용도                  |
|-----------------|-----------------------------|-----------------------|
| DOCKERHUB_TOKEN | Docker Hub Access Token     | 이미지 빌드 & 푸시     |
| KUBECONFIG_DATA | kubeconfig base64 인코딩    | K8s Pod 배포          |

---

## STEP 1: Docker Hub Access Token 발급

1. https://hub.docker.com 로그인 (wo9697)
2. 우측 상단 프로필 → [Account Settings]
3. 왼쪽 메뉴 → [Personal access tokens]
4. [Generate new token] 클릭
5. 설정:
   - Token description: github-actions-incident
   - Access permissions: Read & Write (Read, Write 체크)
6. [Generate] 클릭
7. 토큰 복사 (창 닫으면 다시 못 봄!)
   예시: dckr_pat_xxxxxxxxxxxxxxxxxxxxxx

---

## STEP 2: KUBECONFIG_DATA 생성

K8s 클러스터가 설치된 서버에서 실행:

  cat ~/.kube/config | base64 -w 0

→ 출력된 긴 문자열을 복사

※ -w 0 옵션: 줄바꿈 없이 한 줄로 출력 (macOS는 base64 -b 0)

---

## STEP 3: GitHub Secrets 등록

1. https://github.com/wo969776-cloud/incident-log-service 접속
2. 상단 탭 [Settings] 클릭
3. 왼쪽 메뉴 [Secrets and variables] → [Actions]
4. [New repository secret] 클릭

   ┌─────────────────────────────────────────┐
   │ Name  : DOCKERHUB_TOKEN                 │
   │ Secret: dckr_pat_xxxx... (복사한 토큰)  │
   └─────────────────────────────────────────┘
   → [Add secret]

   ┌─────────────────────────────────────────┐
   │ Name  : KUBECONFIG_DATA                 │
   │ Secret: (base64 인코딩된 kubeconfig)    │
   └─────────────────────────────────────────┘
   → [Add secret]

---

## STEP 4: 동작 확인

등록 후 main 브랜치에 아무 파일이나 수정해서 push:

  git add .
  git commit -m "test: ci/cd 연결 확인"
  git push origin main

GitHub → Actions 탭에서 파이프라인 실행 확인
Docker Hub → wo9697 계정에서 이미지 생성 확인

---

## 생성되는 Docker Hub 이미지 목록

  wo9697/auth-service:latest
  wo9697/auth-service:<commit-sha>

  wo9697/incident-service:latest
  wo9697/incident-service:<commit-sha>

  wo9697/board-service:latest
  wo9697/board-service:<commit-sha>

  wo9697/frontend-service:latest
  wo9697/frontend-service:<commit-sha>

  wo9697/api-gateway:latest
  wo9697/api-gateway:<commit-sha>

---

## 참고: PR에서는 빌드만, push에서는 배포까지

  pull_request → 빌드 O, Docker 푸시 X, K8s 배포 X  (테스트용)
  push(main)   → 빌드 O, Docker 푸시 O, K8s 배포 O  (실제 배포)
