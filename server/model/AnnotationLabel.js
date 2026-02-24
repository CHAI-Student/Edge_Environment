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

// ✅ API 응답에서 _id 제거 (doc.toJSON(), res.json(doc) 등에 적용)
function stripMongoId(doc, ret) {
  delete ret._id;
  return ret;
}

annotationLabelSchema.set("toJSON", { transform: stripMongoId });
annotationLabelSchema.set("toObject", { transform: stripMongoId });

// const ProductUpload = mongoose.model('ProductUpload', productUploadSchema);
const AnnotationLabel = mongoose.model('AnnotationLabel', annotationLabelSchema, 'AnnotationLabel');

module.exports = { AnnotationLabel }