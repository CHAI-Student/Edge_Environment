import React, { useMemo, useState } from 'react';
import { api } from '../../services/api';

const ZoneGrid = ({ loadcells }) => {
    const [activeZone, setActiveZone] = useState(null);

    const zones = useMemo(() => {
        const zoneData = [];
        for (let i = 0; i < 5; i++) {
            // Zone mapping logic (hardcoded in legacy: Zone i uses loadcells i*2 and i*2+1)
            const val1 = parseFloat(loadcells[i * 2]) || 0;
            const val2 = parseFloat(loadcells[i * 2 + 1]) || 0;
            zoneData.push({
                id: i,
                weight: val1 + val2,
                channels: [i * 2, i * 2 + 1]
            });
        }
        return zoneData;
    }, [loadcells]);

    const handleZoneClick = async (zoneId) => {
        setActiveZone(zoneId);
        setTimeout(() => setActiveZone(null), 2000); // Visual feedback timeout
        try {
            await api.camera.activateZone(zoneId);
            console.log(`Zone ${zoneId} activated`);
        } catch (error) {
            console.error(`Failed to activate zone ${zoneId}`, error);
        }
    };

    const totalWeight = zones.reduce((sum, zone) => sum + zone.weight, 0);

    // Using legacy IDs for styling match if needed, or keeping it clean
    return (
        <div className="card">
            <div className="card-header">
                Zones
                <span style={{ color: 'var(--accent)' }}>{totalWeight.toFixed(0)}g</span>
            </div>
            <div className="card-body">
                <div className="zones-grid">
                    {zones.map((zone) => (
                        <div
                            key={zone.id}
                            className={`zone-card ${activeZone === zone.id ? 'active' : ''}`}
                            onClick={() => handleZoneClick(zone.id)}
                            id={`zone-${zone.id}`}
                        >
                            <div className="zone-id">Zone {zone.id}</div>
                            <div className="weight">{zone.weight.toFixed(0)}</div>
                            <div className="channels">CH {zone.channels.join(', ')}</div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ZoneGrid;
