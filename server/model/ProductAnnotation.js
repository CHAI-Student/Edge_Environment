const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const productAnnotationSchema = mongoose.Schema({
    //mongoDB 고유 id값
    annotationIdx: mongoose.Schema.Types.ObjectId,
    //PNT에 등록된 상품 고유번호
    productIdx: {
        type: String,
    },
    //상품 영문명
    productEngName: {
        type: String
    },
    //스냅샷 파일명
    imgFileName: {
        type: String
    },
    //바운딩 박스 좌표
    bboxCoordinate: {
        type: String
    },
    confidence: {
        type: String
    }
})

const ProductAnnotation = mongoose.model('ProductAnnotation', productAnnotationSchema, 'ProductsAnnotation');

module.exports = { ProductAnnotation }