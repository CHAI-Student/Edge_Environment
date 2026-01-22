const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const divisionUploadSchema = mongoose.Schema({
    divisionMetaIdx: mongoose.Schema.Types.ObjectId,
    divisionIdx: {
        type: String,
    },
    modelVersion: {
        type: String
    },
    brunchName: {
        type: String
    },
    products: {
        type: Schema.Types.ObjectId,
        ref: "ProductUpload",
    },
    trainingStatus: {
        type: String
    },
    trainingDate: {
        type: Date,
        default: Date.now
    },
    retrainingDate: {
        type: Date,
        default: Date.now
    },
})

const DivisionUpload = mongoose.model('DivisionUpload', divisionUploadSchema, 'DivisionList');

module.exports = { DivisionUpload }
