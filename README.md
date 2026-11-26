# Edge_Environment.
Edge Environment setting for CHAI project - main server(js)

---

### 요구 사항 (Requirements)
- **Node.js** `>= 24.22.1` (24.x LTS, 2026-10 보안 패치 반영 버전)
  - 2026-10-21 Node.js 보안 릴리스(CVE-2026-105482, CVE-2026-105483, CVE-2026-106069, CVE-2026-111497 등)에 대응하기 위해 최소 버전을 고정했습니다.
  - `nvm` 사용 시: 저장소 루트에서 `nvm use` (`.nvmrc` 참조)

---

### Commit message
**⚙️ Type**

| Type | Describe                                |
| --------- | ------------------------------------ |
| feat      | 새로운 기능에 대한 커밋              |
| fix       | 이슈 수정에 대한 커밋 (+hot-fix)     |
| add       | 기존 기능에 수정하는 것에 대한 커밋       |
| build     | 빌드 관련 파일 수정에 대한 커밋      |
| ci/cd     | 배포 커밋                            |
| docs      | 문서 수정에 대한 커밋                |
| style     | 코드 스타일 혹은 포맷 등에 관한 커밋 |
| refactor  | 코드 리팩토링에 대한 커밋            |
| test      | 테스트 코드 수정에 대한 커밋         |

---

### Response Json Data

**JWT Token Access**
```
[0] {
[0]   "result": "0",
[0]   "msg": "success",
[0]   "accessToken": "",
[0]   "user": {
[0]     "userIdx": "U000001",
[0]     "companyIdx": "CP000000001",
[0]     "companyName": "CRK",
[0]     "divisionIdx": null,
[0]     "fcmToken": "",
[0]     "phoneDevice": null,
[0]     "userId": "admin",
[0]     "name": "총관리자",
[0]     "userType": "INTERNAL",
[0]     "authType": "ADMIN",
[0]     "provider": null,
[0]     "userDetail": null
[0]   }
[0] }
```

**MQTT Connect (Sub/Pub)**
```
[0] [APP] MQTT init done
[0] [MQTT] connected (mqtt://api) clientId=clientId
[0] [MQTT] connected
[0] [MQTT] connected (reboot)
[0] [REBOOT] publishReboot done
[0] [MQTT] subscribing... api/cmd/reboot
[0] [MQTT] subscribed: [ { topic: 'api/cmd/reboot', qos: 1 } ]
```

**IF01-reboot**
```
[TEST] waiting ack: api/ack/reboot
[TEST] stopping server...
[srv] 
[APP] SIGINT received. Shutting down...
[srv] [MQTT] connection closed
[srv] [MQTT] close
[srv] [MQTT] end
[srv] [MQTT] disconnected
[TEST] starting server: /Edge_Environment/server/index.js
[srv] [dotenv@17.2.3] injecting env (0) from .env -- tip: 🔐 prevent committing .env to code: https://dotenvx.com/precommit
[srv] [dotenv@17.2.3] injecting env (0) from .env -- tip: ⚙️  specify custom .env file path with { path: '/custom/path/.env' }
[srv] Server Listening on 8888
[srv] [APP] MQTT init done
[srv] [MQTT] connected (mqtt://api) clientId=clientId
[srv] [MQTT] connected
[srv] [MQTT] connected (reboot)
[srv] [REBOOT] publishReboot done
[srv] [MQTT] subscribing... api/cmd/reboot
[srv] [MQTT] subscribed: [ { topic: 'api/cmd/reboot', qos: 1 } ]
```

**IF02-Monitering**
```
Health Check {"HEADER":{"IF_ID":"IF_02","IF_SYSID":"3d1d0101-0ef2-4bce-b9b5-f69341b2f591","IF_HOST":"MQTTX","IF_DATE":1769666940465},"DATA":{"device_idx":"DE17683631997086480","division_idx":"DI17647205538493077","camera_status":"09","deadbolt_status":"19","loadcell_status":"29","card_terminal_status":"39","edgepc_status":"49"}}
```


**IF03-Door Manual**
```
[MQTT] topic=chai/device/DE17683631997086480/cmd/door/manual payload={"HEADER":{"IF_ID":"IF_03","IF_SYSID":"41523224-79bb-48a5-b6cc-db10b4dbc45a","IF_HOST":"PNT","IF_DATE":"20260119113540"},"DATA":{"division_idx":"DI17647205538493077","device_idx":"DE17683631997086480","door_state":"OPEN"}}
[DOOR] cmd received. IF_SYSID= 41523224-79bb-48a5-b6cc-db10b4dbc45a doorState= OPEN
[DOOR] ack published: chai/device/DE17683631997086480/ack/door/manual IF_SYSID= 41523224-79bb-48a5-b6cc-db10b4dbc45a

//Response to PNT
{"HEADER":{"IF_ID":"IF_03","IF_SYSID":"c8297fe7-bd9f-46de-9501-de3a27f6d36f","IF_HOST":"CHAI","IF_DATE":"1768386459953"},"DATA":{"division_idx":"DI17647205538493077","device_idx":"DE17560868094789999","door_state":"CLOSE","result_cd":"S","result_msg":"Door is closed"}}
```


**IF11-Product List**
```
[RestAPIClient] standalone start
[RestAPIClient] JWT_TOKEN set
[RestAPIClient] response:
{
  HEADER: {
    IF_ID: 'IF_11',
    IF_SYSID: '514d7c58-2d5c-4c20-bb5a-51666b1feb06',
    IF_HOST: 'CHAI',
    IF_DATE: '1768790290402'
  },
  DATA: {
    result_cd: 'S',
    result_msg: '조회 성공',
    product_list: [
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17431239734403436',
        product_name: '롯데 핫식스더킹러쉬355ml',
        product_eng_name: 'CAN_LOTTE_HOT6_THE_KING_RUSH_355ML',
        category_idx: null,
        supply_price: 1150,
        sale_price: 1300,
        stock_qty: 1,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: '1',
        training_status: '0',
        product_width: null,
        product_height: null,
        product_weight: '355',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17355177560736307',
        product_name: '롯데) 트레비 500ML',
        product_eng_name: 'BOTTLE_LOTTE_TREVI_LEMON_500ML',
        category_idx: null,
        supply_price: 770,
        sale_price: 1600,
        stock_qty: 1,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: '1',
        training_status: '0',
        product_width: null,
        product_height: null,
        product_weight: '532',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17560868094789999',
        product_idx: 'P17412473966477576',
        product_name: '한입피자 콤비네이션',
        product_eng_name: 'BAG_SAJO_PIZZA_COMBINATION_80G',
        category_idx: null,
        supply_price: 1180,
        sale_price: 1700,
        stock_qty: 1,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: '1',
        training_status: '0',
        product_width: null,
        product_height: null,
        product_weight: '80',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17560868094789999',
        product_idx: 'P17399215507038132',
        product_name: '홈런볼',
        product_eng_name: 'BAG_HAITAI_HOME_RUN_BALL_41G',
        category_idx: null,
        supply_price: 1200,
        sale_price: 1200,
        stock_qty: 5,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: '1',
        training_status: '0',
        product_width: null,
        product_height: null,
        product_weight: '41',
        storage_type: null,
        has_loadcell: null
      }, 
      { ... },
    ]
  }
}
```

**IF13-ModelBrunchCheck**
```
HEADER: {
  IF_ID: 'IF_13',
  IF_SYSID: '5c4383eb-114b-4118-b87c-a0b695a1d3c0',
  IF_HOST: 'CHAI',
  IF_DATE: '1769667197269'
},
DATA: {
  result_cd: 'S',
  result_msg: '조회 성공',
  device_list: [
    {
      provider: 'chai',
      division_idx: 'DI17647205538493077',
      device_idx: 'DE17560868094789999',
      storage_type: 'C',
      has_loadcell: 'Y',
      payment_type: 'CARD',
      requires_adult_auth: 'N',
      brunch_name: 'CHAI-BR-01',
      brunch_update_date: '2025-12-30T12:00:00',
      model_version: 'v1.0.4',
      model_update_date: '2025-12-30T12:00:00'
    }, 
    {
      provider: 'chai',
      division_idx: 'DI17647205538493077',
      device_idx: 'DE17683631997086480',
      storage_type: 'C',
      has_loadcell: 'Y',
      payment_type: 'CARD',
      requires_adult_auth: 'N',
      brunch_name: null,
      brunch_update_date: null,
      model_version: null,
      model_update_date: null
    }]
}
```


---

### 상품 결제 기능 로직

```
1. 카드 * 삼페 태그 or 삽입
2. 단말기 카드 유효성 체크 + 토큰 생성(sensor)
3. 토큰 생성 확인 전달 (sensor → node)
    1. 냉장고 상태 체크(IF02) + 상품정보(IF11)
4. 상단 카메라 request (node → sensor) + 폴더경로 지정
5. 데드볼트 request (node → sensor)
    1. 상품 정보(상품명, 무게, 재고) + 스냅샷 경로 (node → model)
6. 데드볼트 open + 상단 카메라 on (하위폴더) (sensor)
7. 로드셀 무게 정보 실시간 전달	(sensor → model)
8. 로드셀 무게 변화 감지
→ 폴더 생성 + 측면 카메라 on (sensor python → node → camera python)
→ 카메라 on event 요청 시 dir을 python에서
loadcell event Y → N으로 바뀌면 cam python server
req X → 10초 뒤에 카메라 off
9. 데드볼트 상태 (close) (sensor → node) + (상단 카메라 off + folder snapshot) 저장 (sensor)
→ 로드셀 영점 + 확인 (node → IO board, 아래 "로드셀 영점(zeroset)" 참고)
10. 추론 후 결제 정보(총 가격, 상품명, 개수) 전달 (model → node)
→ 판단시 완전/불완전 상태 파악 필요
11. 단말기 → 가격 + 토큰 전달(node → sensor) → 결제 승인(sensor → node)
12. 결제정보 → PNT
```

### 로드셀 영점(zeroset)

`server/routes/RestAPI/LoadcellZeroset.js`가 IO board `POST /calibrate`로 모든 로드셀을
현재 하중 기준 0으로 맞춘다. 영점은 IO board 시리얼을 약 4초 점유하므로 결제 시작과
health 발행은 진행 중인 영점이 끝날 때까지 기다린다.

**실행 시점**

| 언제 | 조건 |
|---|---|
| 결제 세션 종료 후 | 문 닫힘 → CLOSE → IO board 기록 중지 → 카메라 종료 직후. 남은 트리거가 모두 모델로 전송된 뒤라 그 세션 정산에 영향이 없고, 영점 시간은 추론·결제 승인 대기에 흡수된다. 기록 중지나 카메라 종료가 실패하면 생략 |
| 서버 기동 20초 후 | 1회 |
| 1분 주기 점검 | 마지막으로 확인된 영점 후 25분 경과(측정 보증 30분 전 여유) 또는 직전 영점 실패. 결제·상품 수집 중이 아니고 문이 닫혀 있을 때만 |

손님이 계속 오면 세션마다, 손님이 없으면 25분마다 영점한다.

**영점 확인 (2026-11-26)**

- 영점(약 4초)이 끝나면 바로 `GET /loadcells`로 10채널을 다시 읽어 모두 ±15g 안이면 성공.
  성공 여부는 `/calibrate` 응답이 아니라 다시 읽은 값으로 판단한다.
- 아니면 1번만 다시 영점·확인한다(최대 약 8초). 그래도 실패면 다음 1분 점검에서 다시 시도한다.
- 에러(`EEEEEE`)·무효(`VVVVVV`) 채널은 영점 여부를 판단할 수 없어 확인에서 뺀다(센서 오류는 health가 따로 보고).
- IO board가 아예 응답하지 않으면(timeout·연결 끊김) 재영점 없이 멈추고 로드셀 상태를
  **`20`(장비 이상)**으로 보고한다. Health 보고(IF_02), 결제 시작·상품 수집 시작 점검에 모두
  반영되어 결제가 시작되지 않는다. 1분 점검에서 IO board가 다시 응답하면 풀린다.
  응답은 오는데 값이 남는 실패는 장비 이상으로 보지 않는다.

**왜 확인하나**

모델은 트리거 안의 시작·끝 무게 차이만 쓰므로, 영점이 안 돼 남은 값이 그대로 머물기만 하면
청구에 영향이 없다. 그러나 채널이 음수 영역에 남으면 펌웨어가 값을 양수 쪽으로 되돌리려 해
값이 움직일 수 있고(CRK-IO-BOARD `docs/FIRMWARE_ZERO_TRACKING_REQUEST.md`), 600g이 움직여
머무르면 실제 600g 취출과 구분할 수 없다(4층 오른쪽 −600g이 남은 채 왼쪽 500g 취출 → −1100g).

**문 흔들림**

카메라는 채널 변화가 5g만 넘어도 트리거를 보내므로 문 흔들림도 트리거가 되고, 모델이 거른다.
트리거마다 시작·끝 안정 구간 차이만 쓰고(흔들렸다 돌아오면 0), 냉동은 순변화 50g 미만이면
영상 추론 없이 건너뛰며, 트레이별 50g 미만 채널은 상품으로 판정하지 않는다. 정산에서도 50g 미만
변화는 무시한다. 2026-11-25까지 저장 27세션에서 이렇게 건너뛴 트리거 44건은 모두 35g 이하였다.
흔들림 보정은 50g 미만이거나 왔다 돌아오는 변화만 거르므로 영점 확인을 대신하지 않는다.

**로그**

```
[ZEROSET] calibrate start (reason=post-session, elapsed=3.2min, before=[...])
[ZEROSET] calibrate not verified (reason=post-session, attempt=1/2, result=residual over_15g=ch7=-600g)
[ZEROSET] calibrate verified (reason=post-session, attempt=2, result=ok over_15g=-)
[ZEROSET] IO board no response (reason=..., step=calibrate attempt=1, ...) — loadcell status 20 until IO board responds again
```

### ⚠️ 운영 배포 전 필수 수정 — 결제 금액 하드코딩

현재 카드 승인/취소 요청의 `amount`가 **테스트 값 `'5'`(5원)로 하드코딩**되어
있다. 운영 단에서 실금액으로 수정 예정이며, 수정 전까지 실기기에서 결제 시
실제 상품 금액이 아닌 5원이 승인된다.

- `server/routes/RestAPI/Payments.js`: 승인 요청의 `amount: '5'`
  (실금액은 모델 추론 결과 `total_price` — 주석 처리 상태)
- `server/routes/Mqtt/Repayment.js`: CANCEL/REPAY의 approve·cancel 요청 4곳
  `amount: '5'` (실금액 `reqData.approve_price`는 주석 처리 상태)

운영 전환 시 위 4+1곳의 `'5'`를 실금액 변수로 교체하고 결제 e2e 테스트를
수행할 것.

### 신규 상품 등록 및 학습 모델 임베딩 기능 로직

```
**AI 서버 기능 흐름**

**<픽앤탁-엣지>**

1. 신규 상품 등록 요청 → 픽앤탁 내 신규 상품 등록
2. 수집 문열기 요청(IF04) (문을 열고(데드볼트 열기), 스냅샷 폴더 경로 지정)
    1. 해당 장비(또는 매장)의 모델 버전 파악(IF13) 후 문 열기 제어
3. 수집 제어 req(IF06) (상품별 1번씩 반복 — 상품 정보 1개씩 받아옴)
    1. 상단 카메라 1개, 측면 카메라 1개 + 측면에 위치한 로드셀(1개) 1회씩 지속 제어 필요(수집 제어 될때마다 상품 정보 + 로드셀 무게값 + 스냅샷 저장) (수집 시작 event)
    2. 수집 종료(event) 시 카메라 + 로드셀 종료 + DB 데이터 업로드(mongoDB + MinIO) → **상품별**
        1. training_status 값을 0 → 2로 바꿔주기
        2. 스냅샷 경로 및 관련 정보 + 로드셀 무게값 업로드
        3. +) mongoDB 상품별 클러스터에 annotation array 필요
4. 수집 문닫기 요청(IF04) (문이 이미 닫힌 상태, 즉 데드볼트가 자동으로 내려갔으므로 데드볼트 {door: ‘CLOSE’, deadbolt: ‘LOCKED’} 상태 체크하기)
    1. 이 과정이 끝나면 DB 내에 매장별 모델 버전 정보 + 신규 등록 상품 정보(array)가 1:1로 매핑이 되어있어야 함
    2. 이후 AI 서버 쪽으로 신규 상품이 전달되었음을 api로 전달해야할 듯(event)
        1. 데이터가 업로드 되는 시점에 엣지가 training_status(매장별) 정보 전달(IF07, 데이터 수집 완료(이미 AI 서버 내에 상품 데이터셋 존재): 2)

**<AI서버-픽앤탁>**

1. AI 서버 쪽으로 엣지에서 req한 api가 들어오면 매장별 신규 등록 상품(product_idx)에 대한 상품 스냅샷 데이터셋이 있는지 확인(isNew: 1이거나 training_status: 0 제외하고 나머지)
2. 상품 데이터셋 경로(MinIO)에 대해 어노테이션 자동화 모델 프로세스 진행
3. 어노테이션 끝나고 SAM 모델에 세그먼트 추출 진행
    1. IF07: 어노테이션 프로세스 진행 완료 : 3
4. 세그먼트 추출 이후 이전 모델 버전에 신규 상품 학습 진행
    1. IF07: 세그먼트 추출 완료 : 4
5. 학습 이후 모델 검증/테스트 진행
    1. IF07: 매장별 이전 모델 내 학습 완료: 5
    2. 만약에 검증/테스트 시 임계값 이하의 성능이 나오면 IF07 : 모델 검증 실패, 재학습(재수집) 필요: 8
6. 다 완료되면 신규 모델 버전 및 CI/CD 배포할 브런치 정보(docker 브런치) 업데이트(IF14)
    1. IF07: 매장별 이전 모델 내 검증/테스트 진행 완료: 6
7.  모델 CI/CD 배포 → github 배포 후 Docker Hub 레포지토리로 빌드 완료
    1. IF07: 모델 학습/검증 완료 후 CI/CD 배포 완료: 7

**<엣지-픽앤탁>**

1. 재부팅 요청이 들어오면(IF01, IF07 training_status가 7일때 요청이 들어옴) IF14로 해당 매장+장비에 모델 버전을 체크
    1. 모델 버전이 기존 환경변수에 저장된 버전과 상이하면 장비 상태 체크(IF02)
    2. 모델 버전이 기존 환경변수 저장 버전과 같으면 임베딩 할 정보가 없는 것이므로 pass
2. 1번 과정을 통해 장비가 현재 사용중이 아니라면 DockerHub로 엣지 내 임베딩
    1. IF14의 모델 임베딩 브런치 정보 불러오기
    2. docker pull <username>/<image-name>:<tag>로 배포
3. 임베딩(배포) 완료 후 재부팅(IF01)
    1. 재부팅 이후 docker run 등으로 컨테이너 실행
    2. 엣지 서버 start
    3. jwt token + mqtt 상태 체크
        1. access token 정보 잘 받아오는지
        2. mqtt connect + publish + subscribe 잘 되는지
4. 학습 완료 api 전달
    1. IF07: 배포 완료: 1
```
