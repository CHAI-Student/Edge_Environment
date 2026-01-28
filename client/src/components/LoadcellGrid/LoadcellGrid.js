import React from 'react';

const LoadcellGrid = ({ loadcells }) => {
    // Ensure we always have 10 loadcells to display
    const cells = Array.from({ length: 10 }, (_, i) => ({
        id: i,
        value: parseFloat(loadcells[i]) || 0
    }));

    return (
        <div className="card">
            <div className="card-header">Raw Loadcells</div>
            <div className="card-body">
                <div className="loadcells-grid">
                    {cells.map((cell) => (
                        <div key={cell.id} className="loadcell-item">
                            <div className="channel">CH {cell.id}</div>
                            <div className="value">{cell.value.toFixed(0)}</div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default LoadcellGrid;
