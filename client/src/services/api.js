const API_BASE = window.location.origin; // Or configure via env var if needed
// For development, you might want to point to specific ports if proxy isn't set up
const IO_BOARD_URL = 'http://localhost:8001';
const CAMERA_DRIVER_URL = 'http://localhost:8003';

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
        init: () => fetch(`${CAMERA_DRIVER_URL}/api/init`, { method: 'POST' }).then(handleResponse),
        activateZone: (zoneId) => fetch(`${API_BASE}/api/camera/zone/${zoneId}/activate`, { method: 'POST' }).then(handleResponse),
        getFrame: (cameraId) => fetch(`${CAMERA_DRIVER_URL}/api/camera/${cameraId}/frame`).then(handleResponse),
        // Helper to construct image URLs
        getPreviewUrl: (cameraId) => `${CAMERA_DRIVER_URL}/frame/${cameraId}?t=${Date.now()}`,
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
        saveConfig: (config) => fetch(`${API_BASE}/api/config/save`, { // Hypothetical endpoint based on usage
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        }).then(handleResponse),
    },
    ioBoard: {
        getLoadcells: () => fetch(`${IO_BOARD_URL}/loadcells`).then(handleResponse),
        getStatus: () => fetch(`${IO_BOARD_URL}/status`).then(handleResponse),
    }
};

export const CONSTANTS = {
    API_BASE,
    IO_BOARD_URL,
    CAMERA_DRIVER_URL
};
