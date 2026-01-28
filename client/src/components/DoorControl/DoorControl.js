import React, { useState } from 'react';
import { api } from '../../services/api';
import './DoorControlStyles.css';

const DoorControl = ({ doorStatus }) => {
    const [loading, setLoading] = useState(false);

    const handleAction = async (action) => {
        setLoading(true);
        try {
            if (action === 'unlock') await api.door.unlockDeadbolt();
            if (action === 'lock') await api.door.lockDeadbolt();
            if (action === 'toggle') await api.door.toggleDeadbolt();
        } catch (error) {
            console.error('Door action failed:', error);
        } finally {
            setLoading(false);
        }
    };

    const isLocked = doorStatus.deadbolt?.toUpperCase().includes('CLOSED');
    const isDoorOpen = doorStatus.door?.toUpperCase().includes('OPEN');

    return (
        <div className="glass-panel door-container">
            <div className="dc-header">
                <span className="title">ACCESS CONTROL</span>
            </div>

            <div className="dc-content">
                <div className="status-modules">
                    {/* Door Sensor */}
                    <div className={`status-module glass-card ${isDoorOpen ? 'warning' : 'secure'}`}>
                        <span className="module-label">MAIN ENTRY</span>
                        <span className="module-value font-mono">{isDoorOpen ? 'OPEN' : 'CLOSED'}</span>
                        <div className={`status-light ${isDoorOpen ? 'red' : 'green'}`}></div>
                    </div>

                    {/* Deadbolt Status */}
                    <div className={`status-module glass-card ${isLocked ? 'secure' : 'warning'}`}>
                        <span className="module-label">DEADBOLT</span>
                        <span className="module-value font-mono">{isLocked ? 'LOCKED' : 'UNLOCKED'}</span>
                        <div className={`status-light ${isLocked ? 'green' : 'red'}`}></div>
                    </div>
                </div>

                <div className="control-actions">
                    <button
                        className={`action-btn ${isLocked ? 'unlock-btn' : 'lock-btn'}`}
                        onClick={() => handleAction(isLocked ? 'unlock' : 'lock')}
                        disabled={loading}
                    >
                        {loading ? '...' : (isLocked ? 'UNLOCK' : 'LOCK')}
                    </button>
                    <button
                        className="action-btn toggle-btn"
                        onClick={() => handleAction('toggle')}
                        disabled={loading}
                    >
                        TOGGLE
                    </button>
                </div>
            </div>
        </div>
    );
};

export default DoorControl;
