import React from 'react';

const Header = ({ services }) => {
    const getStatusClass = (isHealthy) => {
        if (isHealthy === true) return 'status-dot healthy';
        if (isHealthy === false) return 'status-dot unhealthy';
        return 'status-dot unknown';
    };

    return (
        <header className="header">
            <h1>CHAI Edge Dashboard</h1>
            <div className="status-bar" id="status-bar">
                <div className="service-badge">
                    <span className={getStatusClass(services.io_board?.healthy)}></span>
                    <span>IO Board</span>
                </div>
                <div className="service-badge">
                    <span className={getStatusClass(services.camera_driver?.healthy)}></span>
                    <span>Camera</span>
                </div>
                <div className="service-badge">
                    <span className={getStatusClass(services.model?.healthy)}></span>
                    <span>Model</span>
                </div>
                <div className="service-badge">
                    <span className={getStatusClass(services.node_server?.healthy)}></span>
                    <span>Node.js</span>
                </div>
                <div className="service-badge">
                    <span className={getStatusClass(services.mongodb?.connected)}></span>
                    <span>MongoDB</span>
                </div>
                <div className="service-badge">
                    <span className={getStatusClass(services.sse_connected)}></span>
                    <span>SSE</span>
                </div>
            </div>
        </header>
    );
};

export default Header;
