const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const divisionUploadSchema = mongoose.Schema({
    //mongoDB 고유 id값
    divisionMetaIdx: mongoose.Schema.Types.ObjectId,
    //PNT에 등록된 매장 고유번호 (FK)
    divisionIdx: {
        type: String,
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
})

// const ProductUpload = mongoose.model('ProductUpload', productUploadSchema);
const DivisionUpload = mongoose.model('DivisionUpload', divisionUploadSchema, 'DivisionList');


module.exports = { DivisionUpload }