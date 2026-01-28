import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';

const ConfigModal = ({ onClose, isOpen }) => {
    const [config, setConfig] = useState(null);

    useEffect(() => {
        if (isOpen) {
            // Mock fetch config or implement real one
            api.config.getZoneMapping().then(data => {
                // handle data
            }).catch(console.error);
        }
    }, [isOpen]);

    if (!isOpen) return null;

    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
            background: 'rgba(0,0,0,0.7)', zIndex: 1000,
            display: 'flex', justifyContent: 'center', alignItems: 'center'
        }}>
            <div style={{
                background: 'var(--bg-secondary)', borderRadius: '8px',
                width: '600px', maxHeight: '80vh', overflowY: 'auto',
                border: '1px solid var(--border)'
            }}>
                <div style={{
                    padding: '15px 20px', borderBottom: '1px solid var(--border)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                }}>
                    <h3 style={{ margin: 0, color: 'var(--accent)' }}>Configuration</h3>
                    <button onClick={onClose} style={{ background: 'none', padding: '5px 10px' }}>X</button>
                </div>
                <div style={{ padding: '20px' }}>
                    <p style={{ color: 'var(--text-secondary)' }}>
                        Configuration options to be implemented. (Zone Mapping, Camera Devices, etc.)
                    </p>
                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '20px' }}>
                        <button onClick={onClose} className="secondary">Close</button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ConfigModal;
