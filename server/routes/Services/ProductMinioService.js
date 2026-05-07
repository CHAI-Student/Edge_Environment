require("dotenv").config();
const fs = require("fs");
const path = require("path");
const Minio = require("minio");
const config = require("../config/key");

function safe(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]/g, "_");
}

function createMinioClient() {
  return new Minio.Client({
    endPoint: config.minioURL,
    port: Number(config.minioPort || 9000),
    useSSL: Boolean(config.minioUseSSL || false),
    accessKey: config.minioAccessKey,
    secretKey: config.minioSecretKey,
  });
}

function fPutObject(minioClient, bucket, key, localPath, meta = {}) {
  return new Promise((resolve, reject) => {
    minioClient.fPutObject(bucket, key, localPath, meta, (err, etag) => {
      if (err) return reject(err);
      resolve(etag);
    });
  });
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

function collectFiles(dir, extensions) {
  if (!fs.existsSync(dir)) return [];

  return fs
    .readdirSync(dir)
    .filter((fname) => extensions.includes(path.extname(fname).toLowerCase()))
    .map((fname) => ({
      fname,
      localPath: path.join(dir, fname),
    }));
}

async function uploadProductImages({
  productIdx,
  timestamp,
  localRoot,
  bucket = config.minioBucket,
  cameras = ["cam_0", "cam_2"],
  deleteAfterUpload = true,
} = {}) {
  if (!productIdx) throw new Error("productIdx is required");
  if (!timestamp) throw new Error("timestamp is required");
  if (!localRoot) throw new Error("localRoot is required");

  const minioClient = createMinioClient();
  const foldername = `${safe(productIdx)}_${safe(timestamp)}`;
  const basePrefix = `productImg/${foldername}`;

  const uploads = [];

  for (const cam of cameras) {
    const dir = path.join(localRoot, "images", cam);
    const files = collectFiles(dir, [".jpg", ".jpeg", ".png"]);

    for (const f of files) {
      uploads.push({
        cam,
        localPath: f.localPath,
        key: `${basePrefix}/${cam}/${f.fname}`,
        contentType:
          path.extname(f.fname).toLowerCase() === ".png"
            ? "image/png"
            : "image/jpeg",
      });
    }
  }

  if (!uploads.length) {
    return {
      success: false,
      bucket,
      foldername,
      folderpath: `s3://${bucket}/${basePrefix}/`,
      prefix: `${basePrefix}/`,
      filelength: 0,
      objects: [],
      message: "No image files found",
    };
  }

  const uploaded = [];
  for (const u of uploads) {
    const etag = await fPutObject(minioClient, bucket, u.key, u.localPath, {
      "Content-Type": u.contentType,
    });

    uploaded.push({
      key: u.key,
      etag,
      localPath: u.localPath,
      cam: u.cam,
    });
  }

  if (deleteAfterUpload) {
    for (const u of uploaded) {
      try {
        fs.unlinkSync(u.localPath);
      } catch (e) {
        console.warn(`[MinIO] failed to delete image: ${u.localPath} :: ${e?.message || e}`);
      }
    }

    for (const cam of cameras) {
      removeDirIfEmpty(path.join(localRoot, "images", cam));
    }
    removeDirIfEmpty(path.join(localRoot, "images"));
    removeDirIfEmpty(localRoot);
  }

  return {
    success: true,
    bucket,
    foldername,
    folderpath: `s3://${bucket}/${basePrefix}/`,
    prefix: `${basePrefix}/`,
    filelength: uploaded.length,
    objects: uploaded.map(({ key, etag, cam }) => ({ key, etag, cam })),
  };
}

async function uploadProductVideos({
  productIdx,
  timestamp,
  localRoot,
  bucket = config.minioBucket,
  cameras = ["cam_0", "cam_2"],
  deleteAfterUpload = false,
} = {}) {
  if (!productIdx) throw new Error("productIdx is required");
  if (!timestamp) throw new Error("timestamp is required");
  if (!localRoot) throw new Error("localRoot is required");

  const minioClient = createMinioClient();
  const foldername = `${safe(productIdx)}_${safe(timestamp)}`;
  const basePrefix = `productImg/${foldername}`;

  const uploads = [];
  for (const cam of cameras) {
    const localPath = path.join(localRoot, `${cam}.mp4`);
    if (!fs.existsSync(localPath)) continue;

    uploads.push({
      cam,
      localPath,
      key: `${basePrefix}/${cam}.mp4`,
    });
  }

  if (!uploads.length) {
    return {
      success: false,
      bucket,
      foldername,
      folderpath: `s3://${bucket}/${basePrefix}/`,
      prefix: `${basePrefix}/`,
      filelength: 0,
      objects: [],
      message: "No video files found",
    };
  }

  const uploaded = [];
  for (const u of uploads) {
    const etag = await fPutObject(minioClient, bucket, u.key, u.localPath, {
      "Content-Type": "video/mp4",
    });

    uploaded.push({
      key: u.key,
      etag,
      localPath: u.localPath,
      cam: u.cam,
    });
  }

  if (deleteAfterUpload) {
    for (const u of uploaded) {
      try {
        fs.unlinkSync(u.localPath);
      } catch (e) {
        console.warn(`[MinIO] failed to delete video: ${u.localPath} :: ${e?.message || e}`);
      }
    }
    removeDirIfEmpty(localRoot);
  }

  return {
    success: true,
    bucket,
    foldername,
    folderpath: `s3://${bucket}/${basePrefix}/`,
    prefix: `${basePrefix}/`,
    filelength: uploaded.length,
    objects: uploaded.map(({ key, etag, cam }) => ({ key, etag, cam })),
  };
}

module.exports = {
  uploadProductImages,
  uploadProductVideos,
};
