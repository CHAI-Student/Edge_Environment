import React from 'react';
import './LoadcellGridStyles.css';

const LoadcellGrid = ({ loadcells }) => {
    const cells = Array.from({ length: 10 }, (_, i) => ({
        id: i,
        value: parseFloat(loadcells[i]) || 0
    }));

    return (
        <div className="glass-panel loadcell-container">
            <div className="lc-header">
                <span className="title">SENSOR ARRAY</span>
                <span className="subtitle">RAW DATA FEED</span>
            </div>
            <div className="loadcells-grid">
                {cells.map((cell) => (
                    <div key={cell.id} className="lc-item glass-card">
                        <div className="lc-channel">CH {cell.id}</div>
                        <div className="lc-value font-mono">{cell.value.toFixed(0)}</div>
                        <div className="lc-bar-container">
                            <div
                                className="lc-bar"
                                style={{ width: `${Math.min(Math.abs(cell.value) / 1000 * 100, 100)}%` }}
                            ></div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default LoadcellGrid;
