// ============================================================
// ProductMinioService.js
// 역할: collect(데이터 수집) 시 로컬에 저장된 상품 snapshot 이미지
//       (images/cam_0, cam_2)와 영상(cam_0.mp4 등)을 MinIO 버킷의
//       productImg/{productIdx}_{timestamp}/ prefix로 업로드하는 서비스.
//       업로드 성공 후 옵션에 따라 로컬 파일 삭제 및 빈 폴더 정리를 수행한다.
// 사용처: 현재 어디에서도 require되지 않음(미사용). 동일한 업로드 로직의
//       테스트 스크립트가 server/test/minioUpload.js, uploadMP4.js에 존재한다.
// ============================================================
require("dotenv").config();
const fs = require("fs");
const path = require("path");
const Minio = require("minio");
const config = require("../../config/key");

// MinIO object key에 안전하도록 영숫자/._- 외의 문자를 "_"로 치환한다.
function safe(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]/g, "_");
}

// config/key의 minio 설정(endPoint/port/SSL/access key)으로 MinIO Client 생성.
function createMinioClient() {
  return new Minio.Client({
    endPoint: config.minioURL,
    port: Number(config.minioPort || 9000),
    useSSL: Boolean(config.minioUseSSL || false),
    accessKey: config.minioAccessKey,
    secretKey: config.minioSecretKey,
  });
}

// callback 기반 minioClient.fPutObject를 Promise로 감싼 헬퍼. etag를 resolve한다.
function fPutObject(minioClient, bucket, key, localPath, meta = {}) {
  return new Promise((resolve, reject) => {
    minioClient.fPutObject(bucket, key, localPath, meta, (err, etag) => {
      if (err) return reject(err);
      resolve(etag);
    });
  });
}

// 디렉토리가 존재하면서 비어있는지 확인한다(에러 시 false).
function isEmptyDir(dir) {
  try {
    return fs.existsSync(dir) && fs.readdirSync(dir).length === 0;
  } catch {
    return false;
  }
}

// 비어있는 디렉토리만 삭제한다(업로드 후 로컬 폴더 정리용, 에러 무시).
function removeDirIfEmpty(dir) {
  try {
    if (isEmptyDir(dir)) fs.rmdirSync(dir);
  } catch {}
}

// 디렉토리 내에서 지정 확장자의 파일만 골라 { fname, localPath } 배열로 반환한다.
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

// localRoot/images/{cam}/ 아래 snapshot 이미지(.jpg/.jpeg/.png)를 순차 업로드한다.
// key 구조: productImg/{productIdx}_{timestamp}/{cam}/{파일명}.
// deleteAfterUpload=true(기본)면 성공 파일 삭제 후 빈 폴더까지 정리하며,
// { success, bucket, foldername, folderpath, prefix, filelength, objects }를 반환한다.
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

// localRoot 바로 아래 {cam}.mp4 영상을 동일 prefix로 업로드한다.
// 이미지와 달리 deleteAfterUpload 기본값이 false라 로컬 영상은 기본 보존된다.
// 반환 형태는 uploadProductImages와 동일하다.
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
