const mongoose = require('mongoose');
const Schema = mongoose.Schema;

const annotationLabelSchema = mongoose.Schema({
    name: {
        type: String,
    },
    id: {
        type: Number
    },
    color: {
        type: String
    },
    type: {
        type: String,
        default: "any"
    },
    attributes: {
        type: Object,
        default: {}
    }
    }, { versionKey: false }
)

annotationLabelSchema.index({ name: 1, id: 1 }, { unique: true });

// const ProductUpload = mongoose.model('ProductUpload', productUploadSchema);
const AnnotationLabel = mongoose.model('AnnotationLabel', annotationLabelSchema, 'AnnotationLabel');

module.exports = { AnnotationLabel }