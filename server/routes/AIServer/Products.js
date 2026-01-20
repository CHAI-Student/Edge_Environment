const express = require("express");
const router = express.Router();
const multer = require("multer");
const { ProductUpload } = require("../model/ProductUpload");
const crypto = require("crypto");
const path = require("path");
const Minio = require("minio");
const config = require("../../config/key");

//=================================
//           ProductUpload
//=================================

const minioClient = req.app.locals.minioClient;
const BUCKET = req.app.locals.minioBucket || "chaiimage";

// multer: 메모리로 받아서 MinIO로 바로 업로드
// const upload = multer({ storage: multer.memoryStorage() }).array("files", 2000);
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    files: 2000,                 // 상한선
    fileSize: 10 * 1024 * 1024, // 10MB
  },
}).array("files", 2000);

function safe(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]/g, "_");
}
function ts() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}${hh}${mi}${ss}`;
}
function sha1(buf) {
  return crypto.createHash("sha1").update(buf).digest("hex").slice(0, 10);
}

function putObjectAsync(minioClient, bucket, key, buffer, meta) {
  return new Promise((resolve, reject) => {
    minioClient.putObject(bucket, key, buffer, meta, (err, etag) => {
      if (err) return reject(err);
      resolve(etag);
    });
  });
}
// MinIO Upload
router.post("/uploads/images", (req, res) => {
    upload(req, res, async (err) => {
        try {
            if (err) return res.status(400).json({ success: false, err: String(err) });
            if (!req.files || req.files.length === 0) {
            return res.status(400).json({ success: false, err: "No files uploaded" });
            }

            const productIdx = req.body.productIdx;
            const divisionIdx = req.body.divisionIdx;
            if (!productIdx || !divisionIdx) {
            return res.status(400).json({ success: false, err: "productIdx and divisionIdx are required" });
            }

            const foldername = `${safe(divisionIdx)}_${safe(productIdx)}_${ts()}`;
            const folderpath = `s3://${BUCKET}/${foldername}/`;

            const uploaded = await Promise.all(
            req.files.map(async (f, i) => {
                const ext = path.extname(f.originalname || "").toLowerCase() || ".jpg";
                const base = path.basename(f.originalname || `img_${i}${ext}`, ext);
                const key = `${foldername}/${safe(base)}_${sha1(f.buffer)}${ext}`;

                const meta = { "Content-Type": f.mimetype || "application/octet-stream" };
                const etag = await putObjectAsync(minioClient, BUCKET, key, f.buffer, meta);

                return { key, etag, size: f.size, mimeType: f.mimetype };
            })
            );

            return res.json({
                success: true,
                bucket: BUCKET,
                foldername,
                folderpath,
                filelength: uploaded.length,
                objects: uploaded.map((x) => ({ key: x.key, etag: x.etag, size: x.size })),
            });
        } catch (e) {
            return res.status(500).json({ success: false, err: e?.message || String(e) });
        }
    });
});

// MongoDB Meta Save
router.post("/products", async (req, res) => {
    try {
        const { productIdx, divisionIdx, foldername, folderpath } = req.body;

        if (!productIdx || !divisionIdx) {
            return res.status(400).json({ success: false, err: "productIdx and divisionIdx are required" });
        }
        if (!foldername || !folderpath) {
            return res.status(400).json({ success: false, err: "foldername and folderpath are required" });
        }

        const doc = await ProductUpload.create({
            productIdx,
            divisionIdx,
            modelVersion: req.body.modelVersion,
            brunchName: req.body.brunchName,
            productName: req.body.productName,
            categoryIdx: req.body.categoryIdx,
            isNew: req.body.isNew,
            trainingStatus: req.body.trainingStatus,
            productEngName: req.body.productEngName,
            productLoadcellWeight: req.body.productLoadcellWeight,
            productAnnotation: req.body.productAnnotation,

            foldername,
            folderpath,
            filelength: Number(req.body.filelength || 0),

            eventPromotion: Array.isArray(req.body.eventPromotion) ? req.body.eventPromotion : [],
        });

        return res.json({ success: true, id: doc._id });
    } catch (e) {
        return res.status(500).json({ success: false, err: e?.message || String(e) });
    }
});


module.exports = router;
