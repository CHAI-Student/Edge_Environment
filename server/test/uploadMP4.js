// ============================================================
// uploadMP4.js — 수동 실행용 테스트 스크립트 (node server/test/uploadMP4.js)
// 역할: 로컬 폴더의 camera 영상(cam_0.mp4, cam_2.mp4)을 MinIO의
//       productImg/{productIdx}_{폴더명}/ prefix로 업로드하고 소요 시간을 측정한다.
// ============================================================
require("dotenv").config();
const fs = require("fs");
const path = require("path");
const Minio = require("minio");
const config = require("../config/key");

function safe(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]/g, "_");
}

async function fPutObject(minioClient, bucket, key, localPath, meta = {}) {
  return new Promise((resolve, reject) => {
    minioClient.fPutObject(bucket, key, localPath, meta, (err, etag) => {
      if (err) return reject(err);
      resolve(etag);
    });
  });
}

async function main() {
  const productIdx = "test01000121";
  const originalname = "20251106_141029"; // ✅ 폴더명(날짜_시간)

  // 로컬: server/test/20251106_141029/cam_0.mp4, cam_2.mp4
  const LOCAL_ROOT = path.resolve(process.cwd(), "server", "test", originalname);

  const BUCKET = config.minioBucket;

  const minioClient = new Minio.Client({
    endPoint: config.minioURL,
    port: 9000,
    useSSL: false,
    accessKey: config.minioAccessKey,
    secretKey: config.minioSecretKey,
  });

  // ✅ MinIO prefix: productImg/{productIdx}_{originalname}/
  const basePrefix = `productImg/${safe(productIdx)}_${safe(originalname)}`;

  const videos = [
    { name: "cam_0.mp4", localPath: path.join(LOCAL_ROOT, "cam_0.mp4") },
    { name: "cam_2.mp4", localPath: path.join(LOCAL_ROOT, "cam_2.mp4") },
  ];

  // 존재 확인
  for (const v of videos) {
    if (!fs.existsSync(v.localPath)) {
      throw new Error(`Video not found: ${v.localPath}`);
    }
  }

  console.log(`[LOCAL] root: ${LOCAL_ROOT}`);
  console.log(`[UPLOAD] bucket: ${BUCKET}`);
  console.log(`[UPLOAD] prefix: ${basePrefix}/`);

  const start = Date.now();

  for (const v of videos) {
    const key = `${basePrefix}/${v.name}`; // ✅ 요청한 경로 그대로
    console.log(`[UPLOAD] ${v.name} -> s3://${BUCKET}/${key}`);

    await fPutObject(minioClient, BUCKET, key, v.localPath, {
      "Content-Type": "video/mp4",
    });
  }

  const totalMs = Date.now() - start;
  console.log(`✅ DONE (2 videos)`);
  console.log(`⏱️ Total time: ${(totalMs / 1000).toFixed(2)} sec`);
}

main().catch((e) => {
  console.error("❌ ERROR:", e?.message || e);
  process.exit(1);
});
