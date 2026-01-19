# Edge_Environment
Edge Environment setting for CHAI project - main server(js)

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
[0] Health Check {"HEADER":{"IF_ID":"IF_02","IF_SYSID":"bc091a51-88c1-4d72-90b1-5d81ddb53480","IF_HOST":"MQTTX","IF_DATE":1768313124579},"DATA":{"device_idx":"device_idx","division_idx":"division_idx","camera_status":"09","deadbolt_status":"19","loadcell_status":"29","card_terminal_status":"39"}}
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
        product_idx: 'P17355176364813008',
        product_name: '페리에 330ml',
        category_idx: null,
        supply_price: 2000,
        sale_price: 1985,
        stock_qty: 12,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: null,
        product_width: null,
        product_height: null,
        product_weight: '550',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17355176391055026',
        product_name: '하겐다즈 그린티&아몬드 80ml',
        category_idx: null,
        supply_price: 4300,
        sale_price: 4300,
        stock_qty: 10,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: null,
        product_width: null,
        product_height: null,
        product_weight: '77',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17355176388041427',
        product_name: '하겐다즈 딸기 80ml',
        category_idx: null,
        supply_price: 4300,
        sale_price: 4300,
        stock_qty: 15,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: null,
        product_width: null,
        product_height: null,
        product_weight: '75',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17355176392597310',
        product_name: '하겐다즈 바닐라 카라멜 아몬드 80ml',
        category_idx: null,
        supply_price: 4300,
        sale_price: 4300,
        stock_qty: 10,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: null,
        product_width: null,
        product_height: null,
        product_weight: '75',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17355176389520600',
        product_name: '하겐다즈 쿠키&크림 80ml',
        category_idx: null,
        supply_price: 4300,
        sale_price: 4300,
        stock_qty: 11,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: null,
        product_width: null,
        product_height: null,
        product_weight: '76',
        storage_type: null,
        has_loadcell: null
      },
      {
        division_idx: 'DI17647205538493077',
        device_idx: 'DE17683631997086480',
        product_idx: 'P17355176370426534',
        product_name: '해태) 홈런볼 41g',
        category_idx: null,
        supply_price: 200,
        sale_price: 2000,
        stock_qty: 12,
        expired_date: null,
        reference_id: null,
        provider: null,
        status: null,
        is_new: null,
        product_width: null,
        product_height: null,
        product_weight: '50',
        storage_type: null,
        has_loadcell: null
      }
    ]
  }
}
```

**IF03-Door Manual**
```
[MQTT] topic=chai/device/DE17683631997086480/cmd/door/manual payload={"HEADER":{"IF_ID":"IF_03","IF_SYSID":"41523224-79bb-48a5-b6cc-db10b4dbc45a","IF_HOST":"PNT","IF_DATE":"20260119113540"},"DATA":{"division_idx":"DI17647205538493077","device_idx":"DE17683631997086480","door_state":"OPEN"}}
[DOOR] cmd received. IF_SYSID= 41523224-79bb-48a5-b6cc-db10b4dbc45a doorState= OPEN
[DOOR] ack published: chai/device/DE17683631997086480/ack/door/manual IF_SYSID= 41523224-79bb-48a5-b6cc-db10b4dbc45a

//Response to PNT
{"HEADER":{"IF_ID":"IF_03","IF_SYSID":"c8297fe7-bd9f-46de-9501-de3a27f6d36f","IF_HOST":"CHAI","IF_DATE":"1768386459953"},"DATA":{"division_idx":"DI17647205538493077","device_idx":"DE17560868094789999","door_state":"CLOSE","result_cd":"S","result_msg":"Door is closed"}}
```
