const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const productUploadSchema = mongoose.Schema({
    //mongoDB 고유 id값
    productMetaIdx: mongoose.Schema.Types.ObjectId,
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
    //PNT에 등록된 상품 고유번호 (FK)
    productIdx: {
        type: String,
    },
    //PNT에 등록된 상품 이름(한글)
    productName: {
        type: String,
    },
    //PNT에 등록된 상품 카테고리
    categoryIdx: {
        type: String,
    },
    //해당 상품이 신규인지 기존에 갖던 정보(이미 학습 완료된)인지 여부
    isNew: {
        type: String,
    },
    //상품 학습 상태 정보 (매장별)
    trainingStatus: {
        type: String
    },
    //상품 영문명
    productEngName: {
        type: String
    },
    //상품 로드셀 무게 정보
    productLoadcellWeight: {
        type: String
    },
    //어노테이션 정보
    productAnnotation: {
        type: Schema.Types.ObjectId,
        ref: "ProductAnnotation",
    },
    //이미지 스냅샷 폴더명
    foldername: {
        type: String
    },
    //이미지 스냅샷 폴더 경로 (MinIO)
    folderpath: {
        type: String
    },
    //이미지 스냅샷 전체 장 수
    filelength: {
        type: Number
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
    //상품 등록일(이미지가 DB에 저장된 날)
    createDate: {
        type: Date,
        default: Date.now
    },
    //상품은 동일하나 이벤트(예: 크리스마스, 뺴빼로데이)로 인해 포장지가 달라져 재학습이 필요한 경우
    eventPromotion: {
        type: Array,
        default: []
    }
})

// const ProductUpload = mongoose.model('ProductUpload', productUploadSchema);
const ProductUpload = mongoose.model('ProductUpload', productUploadSchema, 'ProductsList');


module.exports = { ProductUpload }