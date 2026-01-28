import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import './EventLogStyles.css';

const EventLog = ({ realTimeLogs }) => {
    const [tab, setTab] = useState('weight');
    const [historyLogs, setHistoryLogs] = useState([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const fetchHistory = async () => {
            setLoading(true);
            try {
                let data = {};
                if (tab === 'weight') data = await api.logs.getWeightLogs();
                else if (tab === 'system') data = await api.logs.getSystemLogs();
                else if (tab === 'judgment') data = await api.logs.getJudgmentLogs();
                else if (tab === 'camera') data = await api.logs.getCameraLogs(new Date().toISOString().split('T')[0]);

                let logs = data.logs || data.snapshots || [];
                setHistoryLogs(logs);
            } catch (error) {
                console.error('Failed to fetch logs', error);
            } finally {
                setLoading(false);
            }
        };

        fetchHistory();
        const interval = setInterval(fetchHistory, 30000);
        return () => clearInterval(interval);
    }, [tab]);

    const renderRealTimeLog = () => (
        <div className="rt-log-viewer font-mono custom-scrollbar">
            {realTimeLogs.length === 0 ? (
                <div className="empty-state">WAITING FOR EVENTS...</div>
            ) : (
                realTimeLogs.map((log, i) => (
                    <div key={i} className="rt-item">
                        <span className="rt-time">{new Date(log.timestamp).toLocaleTimeString()}</span>
                        <div className={`rt-type-badge ${log.type}`}>{log.type}</div>
                        <div className="rt-content">
                            {log.type === 'weight' && (
                                <>Z{log.data.zone_id} <span className={log.data.delta < 0 ? 'neg' : 'pos'}>{log.data.delta > 0 ? '+' : ''}{log.data.delta?.toFixed(0)}</span></>
                            )}
                            {log.type === 'door' && log.data.event}
                            {log.type === 'judgment' && `${log.data.product_name} (${(log.data.confidence * 100).toFixed(0)}%)`}
                        </div>
                    </div>
                ))
            )}
        </div>
    );

    const renderHistoryTable = () => {
        if (loading) return <div className="loading-state">SYNCING...</div>;
        if (historyLogs.length === 0) return <div className="empty-state">NO DATA</div>;

        return (
            <div className="history-table-container custom-scrollbar">
                <table className="glass-table">
                    <thead>
                        <tr>
                            <th>TIME</th>
                            {tab === 'weight' && <><th>ZONE</th><th>DELTA</th><th>VAL</th></>}
                            {tab === 'system' && <><th>IO</th><th>CAM</th><th>AI</th><th>MEM</th></>}
                            {tab === 'judgment' && <><th>ZONE</th><th>ITEM</th><th>CONF</th><th>$$</th></>}
                            {tab === 'camera' && <><th>CAMS</th><th>PATH</th></>}
                        </tr>
                    </thead>
                    <tbody>
                        {historyLogs.map((log, i) => (
                            <tr key={i}>
                                <td>{new Date(log.timestamp || log.time?.replace(/-/g, ':') || Date.now()).toLocaleTimeString()}</td>
                                {tab === 'weight' && (
                                    <>
                                        <td>Z{log.zone_id}</td>
                                        <td className={log.delta < 0 ? 'neg' : 'pos'}>{log.delta?.toFixed(0)}</td>
                                        <td>{log.current?.[0]}...</td>
                                    </>
                                )}
                                {tab === 'judgment' && (
                                    <>
                                        <td>{log.zone_id}</td>
                                        <td>{log.product_name}</td>
                                        <td>{(log.confidence * 100).toFixed(0)}%</td>
                                        <td>{log.total_price}</td>
                                    </>
                                )}
                                {/* Other tabs omitted for brevity */}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    return (
        <div className="glass-panel event-container">
            <div className="section-title">LIVE FEED</div>
            {renderRealTimeLog()}

            <div className="history-section">
                <div className="tabs-row">
                    {['weight', 'camera', 'system', 'judgment'].map(t => (
                        <div
                            key={t}
                            className={`tab-btn ${tab === t ? 'active' : ''}`}
                            onClick={() => setTab(t)}
                        >
                            {t.toUpperCase()}
                        </div>
                    ))}
                </div>
                {renderHistoryTable()}
            </div>
        </div>
    );
};

export default EventLog;
