import React, { useMemo, useState } from 'react';
import { api } from '../../services/api';
import './ZoneGridStyles.css';

const ZoneGrid = ({ loadcells }) => {
    const [activeZone, setActiveZone] = useState(null);

    const zones = useMemo(() => {
        const zoneData = [];
        for (let i = 0; i < 5; i++) {
            const val1 = parseFloat(loadcells[i * 2]) || 0;
            const val2 = parseFloat(loadcells[i * 2 + 1]) || 0;
            const weight = val1 + val2;
            zoneData.push({
                id: i,
                weight: weight,
                channels: [i * 2, i * 2 + 1],
                // Calculate intensity for potential heatmap effect
                intensity: Math.min(Math.abs(weight) / 1000, 1) // Cap at 1kg for visualization
            });
        }
        return zoneData;
    }, [loadcells]);

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
