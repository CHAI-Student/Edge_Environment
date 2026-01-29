/**
 * ConfigManager - 설정 파일 관리
 *
 * Zone 매핑, 카메라 디바이스 매핑 등의 설정 파일을 관리합니다.
 * 설정 파일 경로: /config/zone_mapping.json, /config/camera_device_map.json
 */

const fs = require('fs');
const path = require('path');

class ConfigManager {
    constructor() {
        this.configDir = path.resolve(__dirname, '../../config');
        this.zoneMapping = null;
        this.cameraDeviceMap = null;

        // 설정 파일 로드
        this._loadConfigs();
    }

    /**
     * 설정 파일 로드
     */
    _loadConfigs() {
        this._loadZoneMapping();
        this._loadCameraDeviceMap();
    }

    /**
     * Zone 매핑 설정 로드
     */
    _loadZoneMapping() {
        const filePath = path.join(this.configDir, 'zone_mapping.json');

        try {
            if (fs.existsSync(filePath)) {
                const content = fs.readFileSync(filePath, 'utf-8');
                this.zoneMapping = JSON.parse(content);
                console.log('[ConfigManager] Zone mapping loaded');
            } else {
                // 기본값 사용
                this.zoneMapping = this._getDefaultZoneMapping();
                console.log('[ConfigManager] Using default zone mapping');
            }
        } catch (error) {
            console.error('[ConfigManager] Failed to load zone mapping:', error.message);
            this.zoneMapping = this._getDefaultZoneMapping();
        }
    }

    /**
     * 카메라 디바이스 매핑 설정 로드
     */
    _loadCameraDeviceMap() {
        const filePath = path.join(this.configDir, 'camera_device_map.json');

        try {
            if (fs.existsSync(filePath)) {
                const content = fs.readFileSync(filePath, 'utf-8');
                this.cameraDeviceMap = JSON.parse(content);
                console.log('[ConfigManager] Camera device map loaded');
            } else {
                // 기본값 사용
                this.cameraDeviceMap = this._getDefaultCameraDeviceMap();
                console.log('[ConfigManager] Using default camera device map');
            }
        } catch (error) {
            console.error('[ConfigManager] Failed to load camera device map:', error.message);
            this.cameraDeviceMap = this._getDefaultCameraDeviceMap();
        }
    }

    /**
     * 기본 Zone 매핑 반환
     */
    _getDefaultZoneMapping() {
        return {
            version: '1.0',
            zones: {
                '0': { name: 'Zone 0', loadcell_channels: [0, 1], side_camera_id: 1, enabled: true },
                '1': { name: 'Zone 1', loadcell_channels: [2, 3], side_camera_id: 2, enabled: true },
                '2': { name: 'Zone 2', loadcell_channels: [4, 5], side_camera_id: 3, enabled: true },
                '3': { name: 'Zone 3', loadcell_channels: [6, 7], side_camera_id: 4, enabled: true },
                '4': { name: 'Zone 4', loadcell_channels: [8, 9], side_camera_id: 5, enabled: true }
            },
            top_camera_id: 0,
            total_loadcell_channels: 10
        };
    }

    /**
     * 기본 카메라 디바이스 매핑 반환 (6대 카메라: Top + 5 Zone)
     */
    _getDefaultCameraDeviceMap() {
        return {
            version: '1.0',
            nvidia_mode: true,
            device_map: {
                '0': { name: 'Top Camera', physical_index: 0 },
                '1': { name: 'Zone 0 Side', physical_index: 2 },
                '2': { name: 'Zone 1 Side', physical_index: 4 },
                '3': { name: 'Zone 2 Side', physical_index: 6 },
                '4': { name: 'Zone 3 Side', physical_index: 8 },
                '5': { name: 'Zone 4 Side', physical_index: 10 }
            }
        };
    }

    /**
     * Zone 매핑 조회
     * @returns {Object}
     */
    getZoneMapping() {
        return this.zoneMapping;
    }

    /**
     * 카메라 디바이스 매핑 조회
     * @returns {Object}
     */
    getCameraDeviceMap() {
        return this.cameraDeviceMap;
    }

    /**
     * 특정 Zone의 로드셀 채널 조회
     * @param {number} zoneId - Zone ID (0-4)
     * @returns {number[]} 로드셀 채널 배열
     */
    getLoadcellChannelsForZone(zoneId) {
        const zone = this.zoneMapping.zones[zoneId.toString()];
        return zone ? zone.loadcell_channels : [zoneId * 2, zoneId * 2 + 1];
    }

    /**
     * 특정 Zone의 카메라 ID 조회
     * @param {number} zoneId - Zone ID (0-4)
     * @returns {number} Side 카메라 ID
     */
    getCameraIdForZone(zoneId) {
        const zone = this.zoneMapping.zones[zoneId.toString()];
        return zone ? zone.side_camera_id : zoneId + 1;
    }

    /**
     * Top 카메라 ID 조회
     * @returns {number}
     */
    getTopCameraId() {
        return this.zoneMapping.top_camera_id || 0;
    }

    /**
     * 논리적 카메라 ID를 물리적 디바이스 인덱스로 변환
     * @param {number} logicalId - 논리적 카메라 ID (0-5)
     * @returns {number} 물리적 디바이스 인덱스
     */
    getPhysicalDeviceIndex(logicalId) {
        const deviceInfo = this.cameraDeviceMap.device_map[logicalId.toString()];

        if (deviceInfo) {
            return deviceInfo.physical_index;
        }

        // Nvidia 모드인 경우 짝수 인덱스 사용
        if (this.cameraDeviceMap.nvidia_mode) {
            return logicalId * 2;
        }

        return logicalId;
    }

    /**
     * Nvidia 모드 여부 조회
     * @returns {boolean}
     */
    isNvidiaMode() {
        return this.cameraDeviceMap.nvidia_mode || false;
    }

    /**
     * 로드셀 채널로 Zone ID 찾기
     * @param {number} channel - 로드셀 채널 (0-9)
     * @returns {number|null} Zone ID 또는 null
     */
    getZoneIdByLoadcellChannel(channel) {
        for (const [zoneId, zone] of Object.entries(this.zoneMapping.zones)) {
            if (zone.loadcell_channels.includes(channel)) {
                return parseInt(zoneId);
            }
        }
        return null;
    }

    /**
     * 로드셀 채널 배열로 Zone ID 찾기
     * 여러 채널이 변경된 경우, 첫 번째 매칭되는 Zone 반환
     * @param {number[]} channels - 로드셀 채널 배열
     * @returns {number|null} Zone ID 또는 null
     */
    getZoneFromChannels(channels) {
        if (!Array.isArray(channels) || channels.length === 0) {
            return null;
        }

        // 첫 번째 채널로 zone 찾기
        for (const channel of channels) {
            const zoneId = this.getZoneIdByLoadcellChannel(channel);
            if (zoneId !== null) {
                return zoneId;
            }
        }

        return null;
    }

    /**
     * 활성화된 Zone ID 목록 조회
     * @returns {number[]} 활성화된 zone ID 배열
     */
    getEnabledZones() {
        // ENABLED_ZONE_COUNT 환경변수 확인
        const envZoneCount = process.env.ENABLED_ZONE_COUNT;
        let maxZones = null;

        if (envZoneCount) {
            maxZones = parseInt(envZoneCount);
            if (isNaN(maxZones)) maxZones = null;
        }

        const enabledZones = [];
        for (const [zoneId, zone] of Object.entries(this.zoneMapping.zones)) {
            const id = parseInt(zoneId);
            // 환경변수로 override되면 해당 개수만, 아니면 enabled 플래그 확인
            const isEnabled = maxZones !== null
                ? id < maxZones
                : zone.enabled !== false;  // enabled가 명시적으로 false가 아니면 활성화

            if (isEnabled) {
                enabledZones.push(id);
            }
        }

        return enabledZones.sort((a, b) => a - b);
    }

    /**
     * 특정 Zone이 활성화되어 있는지 확인
     * @param {number} zoneId - Zone ID
     * @returns {boolean}
     */
    isZoneEnabled(zoneId) {
        return this.getEnabledZones().includes(zoneId);
    }

    /**
     * 활성화된 Zone 개수 조회
     * @returns {number}
     */
    getEnabledZoneCount() {
        return this.getEnabledZones().length;
    }

    /**
     * 활성화된 카메라 ID 목록 조회 (Top + 활성화된 Zone 카메라)
     * @returns {number[]}
     */
    getEnabledCameraIds() {
        const cameraIds = [this.getTopCameraId()];
        for (const zoneId of this.getEnabledZones()) {
            const cameraId = this.getCameraIdForZone(zoneId);
            if (!cameraIds.includes(cameraId)) {
                cameraIds.push(cameraId);
            }
        }
        return cameraIds.sort((a, b) => a - b);
    }

    /**
     * 활성화된 최대 Zone ID 조회
     * @returns {number}
     */
    getMaxEnabledZoneId() {
        const enabledZones = this.getEnabledZones();
        return enabledZones.length > 0 ? Math.max(...enabledZones) : -1;
    }

    /**
     * Zone 매핑 업데이트
     * @param {Object} newMapping - 새 매핑 설정
     * @returns {boolean} 성공 여부
     */
    updateZoneMapping(newMapping) {
        try {
            // 유효성 검사
            if (!newMapping.zones) {
                throw new Error('Invalid mapping: missing zones');
            }

            this.zoneMapping = {
                ...this.zoneMapping,
                ...newMapping
            };

            // 파일 저장
            const filePath = path.join(this.configDir, 'zone_mapping.json');
            fs.writeFileSync(filePath, JSON.stringify(this.zoneMapping, null, 2));

            console.log('[ConfigManager] Zone mapping updated');
            return true;
        } catch (error) {
            console.error('[ConfigManager] Failed to update zone mapping:', error.message);
            return false;
        }
    }

    /**
     * 카메라 디바이스 매핑 업데이트
     * @param {Object} newMapping - 새 매핑 설정
     * @returns {boolean} 성공 여부
     */
    updateCameraDeviceMap(newMapping) {
        try {
            this.cameraDeviceMap = {
                ...this.cameraDeviceMap,
                ...newMapping
            };

            // 파일 저장
            const filePath = path.join(this.configDir, 'camera_device_map.json');
            fs.writeFileSync(filePath, JSON.stringify(this.cameraDeviceMap, null, 2));

            console.log('[ConfigManager] Camera device map updated');
            return true;
        } catch (error) {
            console.error('[ConfigManager] Failed to update camera device map:', error.message);
            return false;
        }
    }

    /**
     * 특정 카메라의 물리적 인덱스 업데이트
     * @param {number} logicalId - 논리적 카메라 ID
     * @param {number} physicalIndex - 새 물리적 인덱스
     * @returns {boolean} 성공 여부
     */
    setCameraPhysicalIndex(logicalId, physicalIndex) {
        const deviceInfo = this.cameraDeviceMap.device_map[logicalId.toString()];

        if (deviceInfo) {
            deviceInfo.physical_index = physicalIndex;
        } else {
            this.cameraDeviceMap.device_map[logicalId.toString()] = {
                name: `Camera ${logicalId}`,
                physical_index: physicalIndex
            };
        }

        return this.updateCameraDeviceMap(this.cameraDeviceMap);
    }

    /**
     * 설정 재로드
     */
    reload() {
        this._loadConfigs();
        console.log('[ConfigManager] Configuration reloaded');
    }

    /**
     * 모든 설정 조회
     * @returns {Object}
     */
    getAllConfigs() {
        return {
            zone_mapping: this.zoneMapping,
            camera_device_map: this.cameraDeviceMap
        };
    }
}

module.exports = new ConfigManager();
