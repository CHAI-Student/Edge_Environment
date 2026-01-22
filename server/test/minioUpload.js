require("dotenv").config();
const fs = require("fs");
const path = require("path");
const Minio = require("minio");
const config = require("../config/key");

function safe(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]/g, "_");
}

function isEmptyDir(dir) {
  try {
    return fs.existsSync(dir) && fs.readdirSync(dir).length === 0;
  } catch {
    return false;
  }
}

function removeDirIfEmpty(dir) {
  try {
    if (isEmptyDir(dir)) fs.rmdirSync(dir);
  } catch {}
}

async function main() {
  const PRODUCT_IDX = "test01000121";
  const TS = "20251106_141029";
  const LOCAL_ROOT = path.resolve(process.cwd(), "server", "test", TS);
  const BUCKET = config.minioBucket;

  const minioClient = new Minio.Client({
    endPoint: config.minioURL,
    port: 9000,
    useSSL: false,
    accessKey: config.minioAccessKey,
    secretKey: config.minioSecretKey,
  });

  const basePrefix = `productImg/${safe(PRODUCT_IDX)}_${TS}`;

  const targets = [
    { cam: "cam_0", dir: path.join(LOCAL_ROOT, "images", "cam_0") },
    { cam: "cam_2", dir: path.join(LOCAL_ROOT, "images", "cam_2") },
  ];

  for (const t of targets) {
    if (!fs.existsSync(t.dir)) throw new Error(`Local dir not found: ${t.dir}`);
  }

  const uploads = [];
  for (const t of targets) {
    const files = fs.readdirSync(t.dir).filter((f) => path.extname(f).toLowerCase() === ".jpg");
    console.log(`[LOCAL] ${t.cam} images: ${files.length} files`);

    for (const fname of files) {
      uploads.push({
        localPath: path.join(t.dir, fname),
        key: `${basePrefix}/${t.cam}/${fname}`,
      });
    }
  }

  console.log(`[UPLOAD] total files: ${uploads.length}`);
  if (uploads.length === 0) {
    console.log("No images found. Nothing to upload.");
    return;
  }

  const startTime = Date.now();

  // ✅ 1) 업로드 먼저 전체 수행 (삭제 X)
  let ok = 0;
  for (const u of uploads) {
    const fileStart = Date.now();

    await new Promise((resolve, reject) => {
      minioClient.fPutObject(BUCKET, u.key, u.localPath, {}, (err, etag) => {
        if (err) return reject(err);
        resolve(etag);
      });
    });

    const fileEnd = Date.now();
    ok += 1;

    if (ok % 50 === 0 || ok === uploads.length) {
      console.log(`[UPLOAD] ${ok}/${uploads.length} | last file ${(fileEnd - fileStart)} ms`);
    }
  }

  const endTime = Date.now();
  const totalMs = endTime - startTime;

  console.log("================================");
  console.log(`✅ Upload finished (ALL SUCCESS)`);
  console.log(`Files       : ${uploads.length}`);
  console.log(`Total time  : ${(totalMs / 1000).toFixed(2)} sec`);
  console.log(`Avg / file  : ${(totalMs / uploads.length).toFixed(2)} ms`);
  console.log("================================");

  // ✅ 2) 여기까지 왔다는 건 "전부 성공"했다는 뜻 → 이제 삭제
  let deleted = 0;
  for (const u of uploads) {
    try {
      fs.unlinkSync(u.localPath);
      deleted += 1;
    } catch (e) {
      console.warn(`[CLEANUP] failed to delete: ${u.localPath} :: ${e?.message || e}`);
    }
  }
  console.log(`🧹 Local images deleted: ${deleted}/${uploads.length}`);

  // ✅ 3) 빈 폴더 정리 (cam -> images -> TS 루트)
  for (const t of targets) removeDirIfEmpty(t.dir);

  const imagesDir = path.join(LOCAL_ROOT);
  removeDirIfEmpty(imagesDir);

  // TS 루트 폴더 (mp4가 남아있으면 삭제 안 됨)
  removeDirIfEmpty(LOCAL_ROOT);

  console.log("Bucket:", BUCKET);
  console.log("Prefix:", `productImg/${safe(PRODUCT_IDX)}_${TS}/`);
  console.log("Expected:");
  console.log(`  productImg/${safe(PRODUCT_IDX)}_${TS}/cam_0/`);
  console.log(`  productImg/${safe(PRODUCT_IDX)}_${TS}/cam_2/`);
}

main().catch((e) => {
  console.error("❌ ERROR:", e?.message || e);
  process.exit(1);
});
