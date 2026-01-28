import React, { useState } from 'react';
import { api } from '../../services/api';

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
            alert('Door action failed');
        } finally {
            setLoading(false);
        }
    };

    const getStatusClass = (status) => {
        if (!status) return 'state';
        return `state ${status.toUpperCase().includes('OPEN') ? 'open' : 'closed'}`;
    };

    return (
        <div className="card">
            <div className="card-header">Door Control</div>
            <div className="card-body">
                <div className="door-status">
                    <div className="door-indicator">
                        <div className="label">Door</div>
                        <div className={getStatusClass(doorStatus.door)}>
                            {doorStatus.door || '--'}
                        </div>
                    </div>
                    <div className="door-indicator">
                        <div className="label">Deadbolt</div>
                        <div className={getStatusClass(doorStatus.deadbolt)}>
                            {doorStatus.deadbolt || '--'}
                        </div>
                    </div>
                </div>
                <div className="door-controls">
                    <button onClick={() => handleAction('unlock')} disabled={loading}>Unlock</button>
                    <button onClick={() => handleAction('lock')} className="secondary" disabled={loading}>Lock</button>
                    <button onClick={() => handleAction('toggle')} className="secondary" disabled={loading}>Toggle</button>
                </div>
            </div>
        </div>
    );
};

export default DoorControl;
