import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';

const EventLog = ({ realTimeLogs }) => {
    const [tab, setTab] = useState('weight');
    const [historyLogs, setHistoryLogs] = useState([]);
    const [loading, setLoading] = useState(false);

    // Fetch history based on tab
    useEffect(() => {
        const fetchHistory = async () => {
            setLoading(true);
            try {
                let data = {};
                if (tab === 'weight') data = await api.logs.getWeightLogs();
                else if (tab === 'system') data = await api.logs.getSystemLogs();
                else if (tab === 'judgment') data = await api.logs.getJudgmentLogs();
                else if (tab === 'camera') data = await api.logs.getCameraLogs(new Date().toISOString().split('T')[0]);

                // Unify format if needed
                let logs = data.logs || data.snapshots || [];
                setHistoryLogs(logs);
            } catch (error) {
                console.error('Failed to fetch logs', error);
            } finally {
                setLoading(false);
            }
        };

        fetchHistory();
        const interval = setInterval(fetchHistory, 30000); // refresh every 30s
        return () => clearInterval(interval);
    }, [tab]);

    // Real-time log display (top section)
    const renderRealTimeLog = () => (
        <div className="event-log" id="event-log">
            {realTimeLogs.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '20px' }}>
                    Waiting for events...
                </div>
            ) : (
                realTimeLogs.map((log, i) => (
                    <div key={i} className="event-item">
                        <span className="time">{new Date(log.timestamp).toLocaleTimeString()}</span>
                        <span className={`type ${log.type}`}>{log.type}</span>
                        {log.type === 'weight' && (
                            <>
                                <span>Zone {log.data.zone_id}</span>
                                <span className={`delta ${log.data.delta < 0 ? 'negative' : 'positive'}`}>
                                    {log.data.delta > 0 ? '+' : ''}{log.data.delta?.toFixed(0)}g
                                </span>
                            </>
                        )}
                        {log.type === 'door' && <span>{log.data.event}</span>}
                        {log.type === 'judgment' && (
                            <span>{log.data.product_name} - {(log.data.confidence * 100).toFixed(1)}%</span>
                        )}
                    </div>
                ))
            )}
        </div>
    );

    // History log display (bottom footer like section)
    const renderHistoryTable = () => {
        if (loading) return <div style={{ padding: '10px', color: 'var(--text-secondary)' }}>Loading...</div>;
        if (historyLogs.length === 0) return <div style={{ padding: '10px', color: 'var(--text-secondary)' }}>No logs available</div>;

        return (
            <table className="log-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        {tab === 'weight' && <><th>Zone</th><th>Delta</th><th>Current</th></>}
                        {tab === 'system' && <><th>IO</th><th>Cam</th><th>Model</th><th>Mem</th></>}
                        {tab === 'judgment' && <><th>Zone</th><th>Product</th><th>Conf</th><th>Price</th></>}
                        {tab === 'camera' && <><th>Events</th><th>Path</th></>}
                    </tr>
                </thead>
                <tbody>
                    {historyLogs.map((log, i) => (
                        <tr key={i}>
                            <td>{new Date(log.timestamp || log.time?.replace(/-/g, ':') || Date.now()).toLocaleTimeString()}</td>
                            {tab === 'weight' && (
                                <>
                                    <td>Zone {log.zone_id}</td>
                                    <td style={{ color: log.delta < 0 ? 'var(--error)' : 'var(--success)' }}>
                                        {log.delta?.toFixed(0)}g
                                    </td>
                                    <td>{log.current?.join(', ')}</td>
                                </>
                            )}
                            {tab === 'judgment' && (
                                <>
                                    <td>{log.zone_id}</td>
                                    <td>{log.product_name}</td>
                                    <td>{(log.confidence * 100).toFixed(1)}%</td>
                                    <td>{log.total_price}</td>
                                </>
                            )}
                            {/* Simplified for brevity */}
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    };

    return (
        <>
            <div className="card" style={{ marginBottom: '15px' }}>
                <div className="card-header">Real-time Events</div>
                <div className="card-body">
                    {renderRealTimeLog()}
                </div>
            </div>

            <footer className="log-viewer">
                <nav className="log-tabs">
                    {['weight', 'camera', 'system', 'judgment'].map(t => (
                        <div
                            key={t}
                            className={`log-tab ${tab === t ? 'active' : ''}`}
                            onClick={() => setTab(t)}
                        >
                            {t.charAt(0).toUpperCase() + t.slice(1)} Log
                        </div>
                    ))}
                </nav>
                <div className="log-content">
                    {renderHistoryTable()}
                </div>
            </footer>
        </>
    );
};

export default EventLog;
