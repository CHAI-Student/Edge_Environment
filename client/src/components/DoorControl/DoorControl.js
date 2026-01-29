import React, { useState } from 'react';
import { api } from '../../services/api';
import './DoorControlStyles.css';

const DoorControl = ({ doorStatus }) => {
    const [loading, setLoading] = useState(false);

    const handleAction = async (action) => {
        if (loading) return;
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

    const isLocked = doorStatus.deadbolt?.toUpperCase().includes('CLOSED') ||
        doorStatus.deadbolt?.toUpperCase().includes('LOCK');
    const isDoorOpen = doorStatus.door?.toUpperCase().includes('OPEN');

    // Status text logic
    const doorText = isDoorOpen ? 'OPEN' : 'CLOSED';
    const deadboltText = isLocked ? 'LOCKED' : 'UNLOCKED';

    return (
        <div className="glass-panel door-container">
            <div className="dc-header">
                <span className="title">ACCESS CONTROL</span>
                <div className="live-indicator">
                    <div className="status-dot blink"></div>
                    <span>LIVE</span>
                </div>
            </div>

            <div className="dc-content">
                <div className="status-modules">
                    {/* Door Sensor */}
                    <div className={`status-module glass-card ${isDoorOpen ? 'warning' : 'secure'}`}>
                        <div className="module-icon">
                            {isDoorOpen ? (
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12h-6m6 0-3-3m3 3-3 3M3 21V3h18v18z" /></svg>
                            ) : (
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" /></svg>
                            )}
                        </div>
                        <div className="module-info">
                            <span className="module-label">ENTRY SENSOR</span>
                            <span className="module-value font-mono">{doorText}</span>
                        </div>
                    </div>

                    {/* Deadbolt Status */}
                    <div className={`status-module glass-card ${isLocked ? 'secure' : 'active'}`}>
                        <div className="module-icon">
                            {isLocked ? (
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                            ) : (
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 9.9-1" /></svg>
                            )}
                        </div>
                        <div className="module-info">
                            <span className="module-label">DEADBOLT</span>
                            <span className="module-value font-mono">{deadboltText}</span>
                        </div>
                    </div>
                </div>

                <div className="control-actions">
                    <button
                        className={`action-btn ${isLocked ? 'unlock-btn' : 'lock-btn'} ${loading ? 'loading' : ''}`}
                        onClick={() => handleAction(isLocked ? 'unlock' : 'lock')}
                        disabled={loading}
                    >
                        {loading ? 'PROCESSING...' : (isLocked ? 'UNLOCK ENTRY' : 'LOCK ENTRY')}
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
