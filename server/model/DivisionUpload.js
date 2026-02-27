const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const divisionUploadSchema = mongoose.Schema({
    //mongoDB 고유 id값
    divisionMetaIdx: mongoose.Schema.Types.ObjectId,
    //PNT에 등록된 매장 고유번호 (FK)
    divisionIdx: {
        type: String,
    },
    deviceIdx: {
        type: [String]
    },
    }, { versionKey: false }
)

divisionUploadSchema.index({ divisionIdx: 1 }, { unique: true });

// const ProductUpload = mongoose.model('ProductUpload', productUploadSchema);
const DivisionUpload = mongoose.model('DivisionUpload', divisionUploadSchema, 'DivisionList');

module.exports = { DivisionUpload }