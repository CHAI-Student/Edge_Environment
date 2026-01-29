const API_BASE = window.location.origin; // Or configure via env var if needed

// Helper for handling responses
const handleResponse = async (response) => {
    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || response.statusText);
    }
    return response.json();
};

export const api = {
    dashboard: {
        getStatus: () => fetch(`${API_BASE}/api/dashboard/status`).then(handleResponse),
    },
    model: {
        getInfo: () => fetch(`${API_BASE}/api/model/info`).then(handleResponse),
        test: (data) => fetch(`${API_BASE}/api/model/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(handleResponse),
    },
    door: {
        unlockDeadbolt: () => fetch(`${API_BASE}/api/door/deadbolt/unlock`, { method: 'POST' }).then(handleResponse),
        lockDeadbolt: () => fetch(`${API_BASE}/api/door/deadbolt/lock`, { method: 'POST' }).then(handleResponse),
        toggleDeadbolt: () => fetch(`${API_BASE}/api/door/deadbolt/toggle`, { method: 'POST' }).then(handleResponse),
    },
    camera: {
        init: () => fetch(`${API_BASE}/api/camera/init`, { method: 'POST' }).then(handleResponse),
        activateZone: (zoneId) => fetch(`${API_BASE}/api/camera/zone/${zoneId}/activate`, { method: 'POST' }).then(handleResponse),
        deactivateZone: (zoneId) => fetch(`${API_BASE}/api/camera/zone/${zoneId}/deactivate`, { method: 'POST' }).then(handleResponse),
        capture: (zoneId, includeTop = true) => fetch(`${API_BASE}/api/camera/zone/${zoneId}/capture?include_top=${includeTop}`).then(handleResponse),
        snapshotAndJudge: (data) => fetch(`${API_BASE}/api/camera/test/snapshot-and-judge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(handleResponse),
        recordAndJudge: (data) => fetch(`${API_BASE}/api/camera/test/record-and-judge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(handleResponse),
        getFrame: (cameraId) => fetch(`${API_BASE}/api/camera/${cameraId}/frame`).then(handleResponse),
        getPreviewUrl: (cameraId) => `${API_BASE}/api/camera/stream/${cameraId}?t=${Date.now()}`,
    },
    weight: {
        resetBaseline: () => fetch(`${API_BASE}/api/weight/baseline/reset`, { method: 'POST' }).then(handleResponse),
    },
    logs: {
        getWeightLogs: (limit = 50) => fetch(`${API_BASE}/api/logs/weight?limit=${limit}`).then(handleResponse),
        getSystemLogs: (limit = 20) => fetch(`${API_BASE}/api/logs/system?limit=${limit}`).then(handleResponse),
        getJudgmentLogs: (limit = 50) => fetch(`${API_BASE}/api/logs/judgment?limit=${limit}`).then(handleResponse),
        getCameraLogs: (date) => fetch(`${API_BASE}/api/logs/camera/${date}`).then(handleResponse),
    },
    config: {
        getZoneMapping: () => fetch(`${API_BASE}/api/config/zone-mapping`).then(handleResponse),
        getCameraDeviceMap: () => fetch(`${API_BASE}/api/config/camera-device-map`).then(handleResponse),
        updateZoneMapping: (mapping) => fetch(`${API_BASE}/api/config/zone-mapping`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(mapping)
        }).then(handleResponse),
        updateCameraDeviceMap: (mapping) => fetch(`${API_BASE}/api/config/camera-device-map`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(mapping)
        }).then(handleResponse),
        reload: () => fetch(`${API_BASE}/api/config/reload`, { method: 'POST' }).then(handleResponse),
    },
    ioBoard: {
        getLoadcells: () => fetch(`${API_BASE}/api/io-board/loadcells`).then(handleResponse),
        getStatus: () => fetch(`${API_BASE}/api/io-board/status`).then(handleResponse),
    }
};

export const CONSTANTS = {
    API_BASE
};
