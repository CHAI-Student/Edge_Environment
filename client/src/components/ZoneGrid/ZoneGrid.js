import React, { useMemo, useState } from 'react';
import { api } from '../../services/api';
import './ZoneGridStyles.css';

const ZoneGrid = ({ loadcells, zoneConfig }) => {
    const [activeZone, setActiveZone] = useState(null);

    const zones = useMemo(() => {
        const zoneData = [];

        // zone_mapping.json 설정 사용
        const zonesConfig = zoneConfig?.zones || {};

        // 설정된 zone들을 순회 (enabled된 것만)
        const zoneIds = Object.keys(zonesConfig)
            .map(id => parseInt(id))
            .filter(id => zonesConfig[id.toString()]?.enabled !== false)
            .sort((a, b) => a - b);

        for (const zoneId of zoneIds) {
            const zone = zonesConfig[zoneId.toString()];
            const channels = zone?.loadcell_channels || [zoneId * 2, zoneId * 2 + 1];

            // 해당 채널들의 무게 합산
            const weight = channels.reduce((sum, ch) => {
                return sum + (parseFloat(loadcells[ch]) || 0);
            }, 0);

            zoneData.push({
                id: zoneId,
                name: zone?.name || `Zone ${zoneId}`,
                weight: weight,
                channels: channels,
                intensity: Math.min(Math.abs(weight) / 1000, 1)
            });
        }

        return zoneData;
    }, [loadcells, zoneConfig]);

    const handleZoneClick = async (zoneId) => {
        setActiveZone(zoneId);
        setTimeout(() => setActiveZone(null), 2000);
        try {
            await api.camera.activateZone(zoneId);
        } catch (error) {
            console.error(`Failed to activate zone ${zoneId}`, error);
        }
    };

    const totalWeight = zones.reduce((sum, zone) => sum + zone.weight, 0);

    return (
        <div className="glass-panel zone-container">
            <div className="zone-header">
                <span className="title">ZONE STATUS MAP</span>
                <div className="total-weight-box">
                    <span className="label">TOTAL LOAD</span>
                    <span className="value font-mono">{totalWeight.toFixed(0)} <small>g</small></span>
                </div>
            </div>

            <div className="zone-map-grid">
                {zones.map((zone) => (
                    <div
                        key={zone.id}
                        className={`zone-sector ${activeZone === zone.id ? 'active' : ''}`}
                        onClick={() => handleZoneClick(zone.id)}
                        style={{
                            '--zone-intensity': zone.intensity
                        }}
                    >
                        <div className="sector-header">
                            <span className="sector-id">Z{zone.id}</span>
                            <div className={`status-led ${Math.abs(zone.weight) > 50 ? 'occupied' : 'vacant'}`}></div>
                        </div>

                        <div className="sector-body">
                            <div className="weight-readout font-mono">
                                {zone.weight.toFixed(0)}
                            </div>
                            <div className="unit">g</div>
                        </div>

                        <div className="sector-footer">
                            CH {zone.channels.join('+')}
                        </div>

                        {/* Background glow based on weight */}
                        <div className="sector-bg-glow" style={{ opacity: zone.intensity * 0.5 }}></div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ZoneGrid;
