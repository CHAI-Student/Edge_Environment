import React, { useState } from 'react';
import { api } from '../../services/api';

const ModelTest = ({ modelInfo }) => {
    const [zone, setZone] = useState(0);
    const [delta, setDelta] = useState(-520);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [logs, setLogs] = useState([]); // Local logs for the test steps

    const runTest = async () => {
        setLoading(true);
        setResult(null);
        try {
            const data = await api.model.test({
                zone_id: parseInt(zone),
                delta_weight: parseFloat(delta)
            });
            setResult(data);
        } catch (error) {
            setResult({ error: error.message });
        } finally {
            setLoading(false);
        }
    };

    const runWorkflow = async () => {
        setLoading(true);
        setResult(null);
        const addLog = (msg) => setLogs(prev => [...prev, msg]);
        setLogs(['Starting workflow...']);

        try {
            addLog('1. Unlocking deadbolt...');
            await api.door.unlockDeadbolt();

            addLog('2. Waiting for door (mock wait 2s)...');
            // Ideally we wait for actual door status change here, but for now using timeout
            await new Promise(r => setTimeout(r, 2000));

            addLog('3. Simulating weight change...');
            await new Promise(r => setTimeout(r, 1000));

            addLog('4. Running judgment...');
            const data = await api.model.test({
                zone_id: parseInt(zone),
                delta_weight: parseFloat(delta)
            });

            addLog('5. Locking deadbolt...');
            await api.door.lockDeadbolt();

            addLog('Workflow complete!');
            setResult(data);

        } catch (error) {
            addLog(`Error: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="card">
            <div className="card-header">
                Model Test
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    {modelInfo ? `${modelInfo.product_count || 0} products` : 'Loading...'}
                </span>
            </div>
            <div className="card-body">
                <div className="model-test-form">
                    <div className="form-row">
                        <label>Zone</label>
                        <select value={zone} onChange={e => setZone(e.target.value)}>
                            {[0, 1, 2, 3, 4].map(z => (
                                <option key={z} value={z}>Zone {z}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-row">
                        <label>Delta Weight</label>
                        <input
                            type="number"
                            value={delta}
                            onChange={e => setDelta(e.target.value)}
                        />
                        <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>g</span>
                    </div>
                    <div className="form-row">
                        <label></label>
                        <button onClick={runTest} disabled={loading} style={{ flex: 'none', width: '120px' }}>
                            Run Test
                        </button>
                        <button onClick={runWorkflow} disabled={loading} className="success" style={{ flex: 'none', width: '150px' }}>
                            Full Workflow
                        </button>
                    </div>
                </div>

                {/* Workflow Logs */}
                {logs.length > 0 && (
                    <div style={{ marginTop: '10px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {logs.map((log, i) => <div key={i}>{log}</div>)}
                    </div>
                )}

                {/* Result Display */}
                {result && (
                    <div className="test-result show">
                        <div className="result-header">Judgment Result</div>
                        {result.error ? (
                            <div style={{ color: 'var(--error)' }}>Error: {result.error}</div>
                        ) : (
                            <>
                                <div className="result-item"><span>Product</span><span>{result.product_name}</span></div>
                                <div className="result-item">
                                    <span>Confidence</span>
                                    <span>{(result.confidence * 100).toFixed(1)}%</span>
                                </div>
                                <div className="result-item"><span>Price</span><span>{result.total_price}</span></div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ModelTest;
