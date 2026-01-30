# CHAI Smart Vending Dashboard

AI 스마트 자판기 시스템 웹 대시보드 (React)

## 개요

이 대시보드는 다른 레포의 **Node.js Orchestrator (8888)**와 연동됩니다.
`setupProxy.js`가 API 요청을 Node.js로 프록시합니다.

## 실행

```bash
# 개발 서버
npm start

# 빌드
npm run build
```

## 프록시 설정

`src/setupProxy.js`:
- `/api/*` → `http://localhost:8888`
- `/sse/*` → `http://localhost:8888`
- `/health` → `http://localhost:8888`

## 연동 서비스

| 서비스 | 포트 | 관리 레포 |
|--------|------|-----------|
| Node.js | 8888 | Edge_Environment (다른 폴더) |
| Camera | 8003 | 이 레포 |
| Model | 8002 | 이 레포 |

## 주의사항

- Node.js 서비스(8888)가 실행 중이어야 대시보드가 정상 동작합니다.
- Node.js는 다른 레포에서 관리됩니다.

---

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).
