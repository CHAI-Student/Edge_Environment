// ============================================================
// LoadcellZeroset.js
// 역할: 로드셀 영점(zeroset) 자동화 — IO board의 POST /calibrate 관리.
//  - 로드셀 측정 보증 시간(30분)을 넘기지 않도록, 마지막 영점 후
//    경과 시간이 임계값을 넘으면 유휴 상태에서 1회 실행 (경과 기준)
//  - 결제 세션 종료(문 닫힘 → CLOSE → 카메라 OFF 직후)마다 1회 실행 → 같은 타이머 리셋
//  - 서버 기동 직후 1회 실행 (재시작 후 영점 보증 공백 방지)
//  - calibrate는 IO board 시리얼 버스를 3~4초 점유하므로(그동안 모든
//    시리얼 명령 대기), 세션 시작·health 발행은 waitForIdle()로 진행 중
//    영점(확인·재영점 포함) 완료를 기다린 뒤 진입한다
// 영점 확인 (2026-11-26): /calibrate 응답이 성공이어도 채널에 이전 무게가
//    남는 경우가 있다(4층 오른쪽 트레이 −600g이 남아 다음 세션 왼쪽 −500g 취출이
//    −1100g으로 보임). 영점(약 4초)이 끝나면 바로 GET /loadcells로 다시 읽어 모든
//    채널이 ±15g 안이면 성공으로 본다. 아니면 1번만 다시 영점·확인하고(최대 약 8초),
//    그래도 실패면 다음 1분 점검에서 다시 시도한다(25분 경과를 기다리지 않는다).
// 장비 이상: 영점·확인 요청에 IO board가 아예 응답하지 않으면(timeout·연결 거부)
//    재영점하지 않고 바로 멈춘 뒤 로드셀 상태를 '20'(장비 이상)으로 보고한다
//    (hasDeviceError → HealthMqtt.LoadcellStatusAPI). 다음 점검에서 IO board가
//    다시 응답하면 풀린다.
// 실행 가드: 결제 세션 중 / 상품 수집 세션 중 / 문 열림·불명 상태에서는
//    실행하지 않고 다음 점검(1분)으로 미룬다
// ============================================================
require("dotenv").config();
const axios = require("axios");
const config = require("../../config/key");
const { getProcessing } = require("./PaymentProcessing");

// 측정 보증 30분보다 여유를 둔 임계값 — 세션 중 skip이 몇 번 이어져도
// 상한 전에 재시도할 시간이 남도록 한다
const ELAPSED_THRESHOLD_MS = 25 * 60 * 1000;
const CHECK_INTERVAL_MS = 60 * 1000;
// calibrate 자체 3~4초 + IO board 시리얼 재시도 여유
const CALIBRATE_TIMEOUT_MS = 10 * 1000;
// 기동 직후 IO board 서비스가 뜰 때까지 대기
const BOOT_DELAY_MS = 20 * 1000;
// 모든 채널이 이 범위 안이면 영점 성공 (냉동 노이즈 5~15g)
// 확인은 영점 응답 직후 바로 읽는다 — 영점 자체가 약 4초 걸리고, IO board가 영점
// 후 로드셀 cache·sanitizer를 비우므로 다음 조회는 새 판독값이다.
const ZERO_TOLERANCE_G = 15;
// 최초 영점 1회 + 확인 실패 시 재영점 1회
const MAX_ATTEMPTS = 2;
const READ_TIMEOUT_MS = 5 * 1000;
// 에러("EEEEEE")·무효("VVVVVV") 채널은 영점 여부를 판단할 수 없어 확인에서 뺀다
// (센서 오류 자체는 health check의 loadcells 판정이 따로 보고한다)
const UNREADABLE = new Set(["EEEEEE", "VVVVVV"]);

let lastCalibratedAt = 0; // epoch ms. 0 = 기동 후 확인된 영점 없음
let lastFailed = false; // 마지막 영점이 확인에 실패했거나 실행하지 못함 → 다음 점검에서 즉시 재시도
let inFlight = null; // 진행 중 영점 promise (중복 발사 방지 + waitForIdle)
let lastSkipReason = null;
let deviceError = false; // 영점 중 IO board 무응답 → 로드셀 상태 '20'

// AckCollect는 HealthMqtt를 거쳐 순환 참조가 생길 수 있어 호출 시점에 lazy require
function collectSessionActive() {
  try {
    const { hasActiveCollectSession } = require("../Mqtt/AckCollect");
    return hasActiveCollectSession();
  } catch {
    return false;
  }
}

async function doorClosed() {
  try {
    const { fetchCurrentDoorState } = require("../Mqtt/AckCollect");
    return (await fetchCurrentDoorState()) === "CLOSE";
  } catch {
    return false; // 확인 불가면 보수적으로 skip
  }
}

// HTTP 응답 자체가 없음 (timeout·연결 거부 등) — 4xx/5xx 응답은 해당하지 않는다
function noResponse(e) {
  return !e?.response;
}

// 현재 로드셀 판독값(10채널 문자열) 조회. { values, noResponse } — 실패하면 values=null.
async function readLoadcells() {
  try {
    const res = await axios.get(`${config.ioboardApi}/loadcells`, { timeout: READ_TIMEOUT_MS });
    const values = res?.data?.loadcells;
    return { values: Array.isArray(values) ? values : null, noResponse: false };
  } catch (e) {
    console.error("[ZEROSET] loadcell read failed:", e?.message || e);
    return { values: null, noResponse: noResponse(e) };
  }
}

// IO board 무응답 → 장비 이상('20')으로 보고하고 이번 영점을 멈춘다
function markDeviceError(reason, step, e) {
  lastFailed = true;
  if (!deviceError) {
    console.error(
      `[ZEROSET] IO board no response (reason=${reason}, step=${step}${e ? `, ${e.message || e}` : ""}) — loadcell status 20 until IO board responds again`
    );
  }
  deviceError = true;
  return false;
}

// 영점 확인: 읽을 수 있는 모든 채널이 ±ZERO_TOLERANCE_G 안이어야 성공.
function checkZero(values) {
  if (!values) return { ok: false, offenders: [], unreadable: [], reason: "read-failed" };
  const offenders = [];
  const unreadable = [];
  values.forEach((raw, ch) => {
    const value = UNREADABLE.has(raw) ? NaN : parseFloat(raw);
    if (!Number.isFinite(value)) unreadable.push(ch);
    else if (Math.abs(value) > ZERO_TOLERANCE_G) offenders.push({ ch, value });
  });
  if (unreadable.length === values.length) {
    return { ok: false, offenders, unreadable, reason: "no-readable-channel" };
  }
  return { ok: offenders.length === 0, offenders, unreadable, reason: offenders.length ? "residual" : "ok" };
}

function describe(check) {
  const over = check.offenders.map((o) => `ch${o.ch}=${o.value}g`).join(",") || "-";
  const unreadable = check.unreadable.length ? ` unreadable=ch${check.unreadable.join(",ch")}` : "";
  return `result=${check.reason} over_${ZERO_TOLERANCE_G}g=${over}${unreadable}`;
}

// 영점 1회 실행 + 확인. 이미 진행 중이면 그 promise를 반환(중복 발사 방지).
// 반환 promise는 절대 reject하지 않는다 — 실패는 로그만 남기고 lastFailed를
// 세워 다음 점검(1분)에서 재시도한다. 성공은 /calibrate 응답이 아니라
// 영점 후 다시 읽은 값으로 판단한다(응답이 실패·timeout이어도 실제로 영점이
// 잡혔을 수 있다).
function calibrateOnce(reason) {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    const elapsedMin = lastCalibratedAt
      ? ((Date.now() - lastCalibratedAt) / 60000).toFixed(1)
      : "n/a";
    try {
      const before = await readLoadcells();
      if (before.noResponse) return markDeviceError(reason, "read-before");
      console.log(`[ZEROSET] calibrate start (reason=${reason}, elapsed=${elapsedMin}min, before=${JSON.stringify(before.values)})`);
      for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        try {
          await axios.post(`${config.ioboardApi}/calibrate`, {}, { timeout: CALIBRATE_TIMEOUT_MS });
        } catch (e) {
          if (noResponse(e)) return markDeviceError(reason, `calibrate attempt=${attempt}`, e);
          console.error(`[ZEROSET] calibrate request failed (reason=${reason}, attempt=${attempt}):`, e?.message || e);
        }
        const after = await readLoadcells();
        if (after.noResponse) return markDeviceError(reason, `verify attempt=${attempt}`);
        if (deviceError) {
          deviceError = false; // IO board가 다시 응답한다 — 잔여값 실패는 장비 이상이 아님
          console.log("[ZEROSET] IO board responding again — loadcell device error cleared");
        }
        const check = checkZero(after.values);
        if (check.ok) {
          lastCalibratedAt = Date.now();
          lastFailed = false;
          console.log(`[ZEROSET] calibrate verified (reason=${reason}, attempt=${attempt}, ${describe(check)})`);
          return true;
        }
        console.warn(`[ZEROSET] calibrate not verified (reason=${reason}, attempt=${attempt}/${MAX_ATTEMPTS}, ${describe(check)})`);
      }
      lastFailed = true;
      console.error(`[ZEROSET] calibrate failed after ${MAX_ATTEMPTS} attempts (reason=${reason}) — will retry at next check`);
      return false;
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

function sessionBusy() {
  if (getProcessing()) return "payment-session";
  if (collectSessionActive()) return "collect-session";
  return null;
}

// 주기 점검: 경과 시간이 임계값을 넘었거나 직전 영점이 실패했고, 가드를 통과하면 발사
async function fireIfDue() {
  if (inFlight) return;
  const due = lastFailed || !lastCalibratedAt
    || Date.now() - lastCalibratedAt >= ELAPSED_THRESHOLD_MS;
  if (!due) return;

  let skip = sessionBusy();
  if (!skip && !(await doorClosed())) skip = "door-open-or-unknown";
  // 문 상태를 조회하는 동안 결제·수집 세션이 시작됐을 수 있다 — 발사 직전 다시 확인
  if (!skip) skip = sessionBusy();

  if (skip) {
    // 세션이 길어지면 매분 반복되므로 같은 사유는 한 번만 로그
    if (skip !== lastSkipReason) {
      console.log(`[ZEROSET] due but skipped (${skip}) — will retry`);
      lastSkipReason = skip;
    }
    return;
  }
  lastSkipReason = null;
  await calibrateOnce(lastFailed ? "retry-after-failure" : "periodic");
}

// 결제 세션 종료 시 호출 (Payments.js — 문 닫힘·CLOSE 후 카메라 OFF 직후).
// 문 닫힘·녹화/카메라 종료가 보장된 지점이라 결제 세션 가드는 건너뛴다.
// 기록 중지나 카메라 종료가 실패했으면 로드셀을 읽는 쪽(트리거 전송)이 남아
// 있을 수 있어 영점하지 않고, 세션이 끝난 뒤 주기 점검에서 다시 시도한다.
// fire-and-forget: 실패해도 결제 흐름과 무관하고, 주기 점검이 백스톱.
function fireAfterSession({ recordingStopped = true, cameraStopped = true } = {}) {
  if (!recordingStopped || !cameraStopped) {
    console.warn(
      `[ZEROSET] post-session skipped (recording_stopped=${recordingStopped}, camera_stopped=${cameraStopped}) — will retry at next check`
    );
    lastFailed = true;
    return;
  }
  if (collectSessionActive()) {
    console.log("[ZEROSET] post-session skipped (collect-session)");
    return;
  }
  calibrateOnce("post-session");
}

// 진행 중 영점이 있으면 완료(확인·재영점 포함)까지 대기 (없으면 즉시 반환).
// calibrate가 시리얼을 점유한 채 health check(GET /health, timeout 5s)에
// 들어가면 타임아웃으로 오판될 수 있고, 영점·확인 중 세션이 시작되면 재영점이
// 세션 도중에 걸리므로 세션 시작·health 발행 전에 호출한다.
async function waitForIdle() {
  if (inFlight) await inFlight; // calibrateOnce의 promise는 reject하지 않음
}

function init() {
  console.log(
    `[ZEROSET] init (threshold=${ELAPSED_THRESHOLD_MS / 60000}min, check=${CHECK_INTERVAL_MS / 1000}s, `
    + `verify=±${ZERO_TOLERANCE_G}g, attempts=${MAX_ATTEMPTS})`
  );
  // 기동 직후 1회 — 재시작 후 마지막 영점 시각을 알 수 없으므로 즉시 보증 확보
  setTimeout(fireIfDue, BOOT_DELAY_MS);
  setInterval(fireIfDue, CHECK_INTERVAL_MS);
}

// 영점 중 IO board가 응답하지 않아 장비 이상으로 보고해야 하는가
function hasDeviceError() {
  return deviceError;
}

module.exports = { init, fireAfterSession, waitForIdle, hasDeviceError };
