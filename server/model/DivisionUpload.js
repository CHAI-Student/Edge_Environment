// ============================================================
// DivisionUpload.js
// 역할: 매장(division) 단위 메타를 담는 Mongoose 모델. divisionIdx(unique index)와
//       소속 deviceIdx 배열, modelVersion, brunchName, 상품 참조(products),
//       학습 상태(trainingStatus)/학습일(trainingDate)/재학습일(retrainingDate)을 관리.
// 컬렉션명: DivisionList / 사용처: AckCollect.js, ProductMongoSyncService,
//       server/test/mongodbDataUpload.js, mongodbDivisionUpload.js
// ============================================================
const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const divisionUploadSchema = mongoose.Schema({
    //mongoDB 고유 id값
    divisionMetaIdx: mongoose.Schema.Types.ObjectId,
    //PNT에 등록된 매장 고유번호 (FK)
    divisionIdx: {
        type: String,
    },
    //매장에 소속된 장비 코드 목록
    deviceIdx: {
        type: [String]
    },
    //배포 모델 버전 (매장별)
    modelVersion: {
        type: String
    },
    //매장 별 모델 배포 브런치 정보(CI/CD)
    brunchName: {
        type: String
    },
    //PNT에 등록된 매장별 신규 상품 리스트
    products: {
        type: Schema.Types.ObjectId,
        ref: "ProductUpload",
    },
    //모델 학습 상태 정보 (매장별)
    //학습 상태 여부
    /**
        미학습: 0
        배포 완료: 1
        데이터 수집 완료(이미 AI 서버 내에 상품 데이터셋 존재): 2
        어노테이션 프로세스 진행 완료 : 3
        세그먼트 추출 완료 : 4
        매장별 이전 모델 내 학습 완료: 5
        매장별 이전 모델 내 검증/테스트 진행 완료: 6
        모델 학습/검증 완료 후 CI/CD 배포 완료: 7
        모델 검증 실패, 재학습(데이터셋 재수집) 필요: 8
    */
    trainingStatus: {
        type: String
    },
    //학습 시작일
    trainingDate: {
        type: Date,
        default: Date.now
    },
    //재학습 시작일
    retrainingDate: {
        type: Date,
        default: Date.now
    },
}, { versionKey: false }
)

divisionUploadSchema.index({ divisionIdx: 1 }, { unique: true });

const DivisionUpload = mongoose.model('DivisionUpload', divisionUploadSchema, 'DivisionList');

module.exports = { DivisionUpload }
