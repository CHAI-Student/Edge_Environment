import React, { useState } from 'react';
import { api } from '../../services/api';
import './ModelTestStyles.css';

const ModelTest = ({ modelInfo }) => {
    const [zone, setZone] = useState(0);
    const [delta, setDelta] = useState(-520);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [logs, setLogs] = useState([]);

    // For stepper visualization
    const [currentStep, setCurrentStep] = useState(0);
    const steps = ['Unlock', 'Wait Door', 'Weight Chg', 'Judgment', 'Lock', 'Done'];

    const runTest = async () => {
        setLoading(true);
        setResult(null);
        setCurrentStep(0);
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
        const addLog = (msg) => setLogs(prev => [msg, ...prev.slice(0, 4)]);
        setLogs([]);

        try {
            setCurrentStep(1); // Unlock
            addLog('Unlocking deadbolt...');
            await api.door.unlockDeadbolt();

            setCurrentStep(2); // Wait Door
            addLog('Waiting for door...');
            await new Promise(r => setTimeout(r, 2000));

            setCurrentStep(3); // Weight Chg
            addLog('Simulating weight change...');
            await new Promise(r => setTimeout(r, 1000));

            setCurrentStep(4); // Judgment
            addLog('Running judgment...');
            const data = await api.model.test({
                zone_id: parseInt(zone),
                delta_weight: parseFloat(delta)
            });

            setCurrentStep(5); // Lock
            addLog('Locking deadbolt...');
            await api.door.lockDeadbolt();

            setCurrentStep(6); // Done
            addLog('Workflow complete!');
            setResult(data);

        } catch (error) {
            addLog(`Error: ${error.message}`);
            setCurrentStep(0); // Error state could be separate
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel model-container">
            <div className="mt-header">
                <span className="title">INFERENCE ENGINE</span>
                <span className="subtitle font-mono">
                    {modelInfo ? `${modelInfo.product_count} PRODUCTS LOADED` : 'INIT...'}
                </span>
            </div>

            <div className="mt-body">
                <div className="control-row">
                    <div className="input-group">
                        <label>TARGET ZONE</label>
                        <select value={zone} onChange={e => setZone(e.target.value)} className="glass-input">
                            {[0, 1, 2, 3, 4].map(z => (
                                <option key={z} value={z}>ZONE {z}</option>
                            ))}
                        </select>
                    </div>
                    <div className="input-group">
                        <label>WEIGHT DELTA (g)</label>
                        <input
                            type="number"
                            className="glass-input"
                            value={delta}
                            onChange={e => setDelta(e.target.value)}
                        />
                    </div>
                    <div className="action-group">
                        <button onClick={runTest} disabled={loading} className="glass-btn">
                            TEST
                        </button>
                        <button onClick={runWorkflow} disabled={loading} className="glass-btn primary">
                            WORKFLOW
                        </button>
                    </div>
                </div>

                {/* Stepper Visualization */}
                <div className="workflow-stepper">
                    {steps.map((step, i) => (
                        <div key={i} className={`step-item ${currentStep > i ? 'completed' : currentStep === i + 1 ? 'active' : ''}`}>
                            <div className="step-dot"></div>
                            <span className="step-label">{step}</span>
                        </div>
                    ))}
                    <div className="progress-line" style={{ width: `${(Math.max(0, currentStep - 1) / (steps.length - 1)) * 100}%` }}></div>
                </div>

                {/* Logs Overlay */}
                {logs.length > 0 && (
                    <div className="mini-log font-mono">
                        {logs.map((log, i) => <div key={i}>&gt; {log}</div>)}
                    </div>
                )}

                {/* Result Display */}
                {result && (
                    <div className="result-panel glass-card">
                        <div className="res-header">JUDGMENT RESULT</div>
                        {result.error ? (
                            <div className="res-error">ERROR: {result.error}</div>
                        ) : (
                            <div className="res-grid">
                                <div className="res-row">
                                    <span>PRODUCT</span>
                                    <span className="highlight">{result.product_name}</span>
                                </div>
                                <div className="res-row">
                                    <span>CONFIDENCE</span>
                                    <span className={`conf ${result.confidence > 0.8 ? 'high' : 'low'}`}>
                                        {(result.confidence * 100).toFixed(1)}%
                                    </span>
                                </div>
                                <div className="res-row">
                                    <span>PRICE</span>
                                    <span className="highlight font-mono">{result.total_price}</span>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ModelTest;
