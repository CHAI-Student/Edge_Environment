import React from 'react';
import './HeaderStyles.css'; // We'll create this or inline styles. But let's use global glass classes + inline for now or create a module.
// For simplicity in this flow, I'll use the global classes and inline specific layout styles or create a new CSS file.
// Let's create a local CSS file for the header to keep it clean.

const Header = ({ services }) => {
    const getStatusInfo = (isHealthy) => {
        if (isHealthy === true) return { class: 'status-indicator healthy', label: 'ONLINE' };
        if (isHealthy === false) return { class: 'status-indicator unhealthy', label: 'OFFLINE' };
        return { class: 'status-indicator unknown', label: 'UNKNOWN' };
    };

    const ServiceItem = ({ name, status }) => {
        const info = getStatusInfo(status);
        return (
            <div className={`service-item ${info.class ? info.class.split(' ')[1] : ''}`}>
                <div className="service-name">{name}</div>
                <div className="service-status-row">
                    <div className={info.class}></div>
                    <span className="status-label">{info.label}</span>
                </div>
            </div>
        );
    };

    return (
        <header className="glass-panel header-container">
            <div className="brand-section">
                <div className="logo-glow">
                    <img src={`${process.env.PUBLIC_URL}/logo192.png`} alt="CHAI" className="app-logo" />
                </div>
                <div className="brand-text">
                    <h1>CHAI EDGE</h1>
                    <span className="subtitle">COMMAND CENTER</span>
                </div>
            </div>

            <div className="hud-display">
                <ServiceItem name="IO CONTROLLER" status={services.io_board?.healthy} />
                <ServiceItem name="VISION SYSTEM" status={services.camera_driver?.healthy} />
                <ServiceItem name="AI INFERENCE" status={services.model?.healthy} />
                <ServiceItem name="BACKEND API" status={services.node_server?.healthy} />
                <ServiceItem name="DATABASE" status={services.mongodb?.connected} />
                <ServiceItem name="EVENT STREAM" status={services.sse_connected} />
            </div>

            <div className="system-time">
                {new Date().toLocaleTimeString()}
            </div>
        </header>
    );
};

export default Header;
