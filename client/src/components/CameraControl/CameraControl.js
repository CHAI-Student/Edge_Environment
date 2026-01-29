import React, { useState } from 'react';
import { api } from '../../services/api';
import './CameraControlStyles.css';

const CameraControl = () => {
    const [zone, setZone] = useState(0);
    const [loading, setLoading] = useState(false);
    const [lastSnapshot, setLastSnapshot] = useState(null);

    const handleAction = async (action) => {
        setLoading(true);
        try {
            let res;
            if (action === 'activate') {
                res = await api.camera.activateZone(zone);
            } else if (action === 'deactivate') {
                res = await api.camera.deactivateZone(zone);
            } else if (action === 'snapshot') {
                res = await api.camera.capture(zone, true); // Include top
                // Assuming result has top_frame or zone_frame in base64
                if (res.top_frame) setLastSnapshot(`data:image/jpeg;base64,${res.top_frame}`);
                else if (res.zone_frame) setLastSnapshot(`data:image/jpeg;base64,${res.zone_frame}`);
            }
            console.log('Camera Action Result:', res);
        } catch (error) {
            console.error('Camera action failed:', error);
            alert(`Error: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel camera-control-container">
            <div className="cc-header">
                <span className="title">CAMERA CONTROL</span>
            </div>

            <div className="cc-body">
                <div className="control-row">
                    <div className="input-group">
                        <label>TARGET ZONE</label>
                        <select value={zone} onChange={e => setZone(parseInt(e.target.value))} className="glass-input">
                            {[0, 1, 2, 3, 4].map(z => (
                                <option key={z} value={z}>ZONE {z}</option>
                            ))}
                        </select>
                    </div>
                </div>

                <div className="action-buttons">
                    <button
                        className="glass-btn"
                        onClick={() => handleAction('activate')}
                        disabled={loading}
                    >
                        ACTIVATE
                    </button>
                    <button
                        className="glass-btn warning"
                        onClick={() => handleAction('deactivate')}
                        disabled={loading}
                    >
                        DEACTIVATE
                    </button>
                    <button
                        className="glass-btn primary"
                        onClick={() => handleAction('snapshot')}
                        disabled={loading}
                    >
                        SNAPSHOT
                    </button>
                </div>

                {lastSnapshot && (
                    <div className="snapshot-preview">
                        <div className="preview-label">LAST SNAPSHOT</div>
                        <img src={lastSnapshot} alt="Snapshot" />
                    </div>
                )}
            </div>
        </div>
    );
};

export default CameraControl;
