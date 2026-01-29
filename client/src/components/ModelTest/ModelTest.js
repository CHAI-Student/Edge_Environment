import React, { useState } from 'react';
import { api } from '../../services/api';
import './ModelTestStyles.css';

const ModelTest = ({ modelInfo }) => {
    // Mode: 'simple' (weight only), 'vision' (snapshot), 'full' (simulation)
    const [mode, setMode] = useState('full');

    // Common State
    const [zone, setZone] = useState(0);
    const [loading, setLoading] = useState(false);
    const [logs, setLogs] = useState([]);
    const [result, setResult] = useState(null);

    // Simple Test State
    const [delta, setDelta] = useState(-520);

    // Full Simulation State
    const [simState, setSimState] = useState('IDLE'); // IDLE, STANDBY, RECORDING, ANALYZING, DONE
    const [simProgress, setSimProgress] = useState(0);

    const addLog = (msg) => {
        const time = new Date().toLocaleTimeString().split(' ')[0];
        setLogs(prev => [`[${time}] ${msg}`, ...prev.slice(0, 10)]);
    };

    // --- HANDLERS ---

    // 1. Simple Weight Test (Legacy)
    const runWeightTest = async () => {
        setLoading(true);
        setResult(null);
        addLog(`Running Weight Test: Zone ${zone}, Delta ${delta}g`);
        try {
            const data = await api.model.test({
                zone_id: parseInt(zone),
                delta_weight: parseFloat(delta)
            });
            setResult({ type: 'weight', ...data });
            addLog('Weight Test Complete');
        } catch (error) {
            setResult({ error: error.message });
            addLog(`Error: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    // 2. Vision Only Test (Snapshot)
    const runVisionTest = async () => {
        setLoading(true);
        setResult(null);
        addLog(`Running Vision Test (Snapshot): Zone ${zone}`);
        try {
            const data = await api.camera.snapshotAndJudge({
                zone_id: parseInt(zone),
                include_top: true
            });
            setResult({ type: 'vision', ...data });
            addLog('Vision Test Complete');
        } catch (error) {
            setResult({ error: error.message });
            addLog(`Error: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    // 3. Full Cycle Simulation (The requested feature)
    // "Standby" -> User triggers "Weight Change" -> Camera Records (3s) -> Judge

    const enterStandby = async () => {
        setLoading(true);
        setSimState('PREPARING');
        addLog('Preparing Standby State...');
        try {
            // 1. Ensure Door is Unlocked (as per request: "after deadbolt open")
            addLog('> Unlocking Deadbolt...');
            await api.door.unlockDeadbolt();

            // 2. Wait a moment
            await new Promise(r => setTimeout(r, 1000));

            setSimState('STANDBY');
            addLog('SYSTEM STANDBY. Waiting for weight event...');
        } catch (error) {
            addLog(`Standby Error: ${error.message}`);
            setSimState('IDLE');
        } finally {
            setLoading(false);
        }
    };

    const triggerWeightEvent = async () => {
        if (loading) return;
        setLoading(true);
        setSimState('RECORDING');
        setSimProgress(0);
        setResult(null);

        addLog(`Weight Change Detected (${delta}g). Triggering Camera...`);

        // Fake progress bar for 3s recording
        const progressInterval = setInterval(() => {
            setSimProgress(prev => Math.min(prev + 5, 95));
        }, 150);

        try {
            // Call the record-and-judge endpoint
            // This endpoint records for 3s, saves to disk, and runs judgment
            const data = await api.camera.recordAndJudge({
                zone_id: parseInt(zone),
                duration_ms: 3000,
                fps: 30
            });

            clearInterval(progressInterval);
            setSimProgress(100);
            setSimState('ANALYZING'); // Although API returns everything, we show state transition

            await new Promise(r => setTimeout(r, 500)); // UI delay for effect

            setResult({ type: 'full', ...data });
            setSimState('DONE');
            addLog(`Analysis Complete. Found ${data.top_candidates?.length || 0} candidates.`);

        } catch (error) {
            clearInterval(progressInterval);
            setSimState('STANDBY'); // Revert to standby on error?
            setResult({ error: error.message });
            addLog(`Simulation Error: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    const resetSimulation = () => {
        setSimState('IDLE');
        setResult(null);
        setSimProgress(0);
    };


    // --- RENDER HELPERS ---

    const renderResult = () => {
        if (!result) return null;
        if (result.error) return <div className="res-error">ERROR: {result.error}</div>;

        // Unified Result Display
        const isVision = result.type === 'vision' || result.type === 'full';
        const candidates = result.top_candidates || (result.judgment?.products) || [];
        // Note: 'vision' type returns judgment.products (array)
        // 'full' types returns top_candidates (array with scores)

        // If weight test only
        if (result.type === 'weight') {
            return (
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
            );
        }

        // Vision / Full Results
        return (
            <div className="candidates-list">
                <div className="res-header-sm">TOP CANDIDATES</div>
                {candidates.length === 0 ? (
                    <div className="no-result">NO PRODUCTS DETECTED</div>
                ) : (
                    candidates.map((c, i) => (
                        <div key={i} className="candidate-row">
                            <span className="rank">#{i + 1}</span>
                            <div className="c-info">
                                <span className="c-name">{c.name || c.productName}</span>
                                <span className="c-id">{c.productId}</span>
                            </div>
                            <div className="c-score">
                                <span className="score-val">
                                    {c.score ? c.score.toFixed(2) : ((c.confidence || 0) * 100).toFixed(0) + '%'}
                                </span>
                                <span className="score-label">{c.score ? 'SCORE' : 'CONF'}</span>
                            </div>
                        </div>
                    ))
                )}
                {result.recording && (
                    <div className="rec-stats">
                        <span>{result.recording.total_frames} FRAMES</span>
                        <span>{result.recording.inference_time_ms}ms INFERENCE</span>
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="glass-panel model-container">
            <div className="mt-header">
                <div className="header-top">
                    <span className="title">LOGIC SIMULATOR</span>
                    <span className="subtitle font-mono">
                        {modelInfo ? `${modelInfo.product_count} SKUs` : '...'}
                    </span>
                </div>
                <div className="mode-tabs">
                    <button className={mode === 'full' ? 'active' : ''} onClick={() => setMode('full')}>SIMULATION</button>
                    <button className={mode === 'vision' ? 'active' : ''} onClick={() => setMode('vision')}>VISION TEST</button>
                    <button className={mode === 'simple' ? 'active' : ''} onClick={() => setMode('simple')}>WEIGHT TEST</button>
                </div>
            </div>

            <div className="mt-body">
                {/* GLOBAL SETTINGS */}
                <div className="control-row compact">
                    <div className="input-group">
                        <label>TARGET ZONE</label>
                        <select value={zone} onChange={e => setZone(e.target.value)} className="glass-input">
                            {[0, 1, 2, 3, 4].map(z => <option key={z} value={z}>ZONE {z}</option>)}
                        </select>
                    </div>
                    <div className="input-group">
                        <label>DELTA WEIGHT (g)</label>
                        <input type="number" className="glass-input" value={delta} onChange={e => setDelta(e.target.value)} />
                    </div>
                </div>

                {/* MODE CONTENT */}

                {mode === 'full' && (
                    <div className="sim-panel">
                        <div className={`sim-status-display state-${simState.toLowerCase()}`}>
                            <div className="status-indicator">
                                <div className={`status-dot ${simState === 'RECORDING' ? 'blink-fast' : simState === 'STANDBY' ? 'pulse' : ''}`}></div>
                                <span className="status-text">{simState}</span>
                            </div>
                            {simState === 'RECORDING' && (
                                <div className="sim-progress">
                                    <div className="bar" style={{ width: `${simProgress}%` }}></div>
                                </div>
                            )}
                        </div>

                        <div className="sim-controls">
                            {simState === 'IDLE' || simState === 'DONE' ? (
                                <button className="glass-btn primary" onClick={enterStandby} disabled={loading}>
                                    INITIALIZE STANDBY
                                </button>
                            ) : (
                                <button className="glass-btn warning" onClick={resetSimulation} disabled={loading}>
                                    STOP / RESET
                                </button>
                            )}

                            <button
                                className={`glass-btn action-trigger ${simState === 'STANDBY' ? 'pulse-border' : ''}`}
                                onClick={triggerWeightEvent}
                                disabled={simState !== 'STANDBY' || loading}
                            >
                                SIMULATE EVENT
                            </button>
                        </div>
                        <div className="sim-desc">
                            {simState === 'IDLE' && "Initialize to open door and wait for events."}
                            {simState === 'STANDBY' && "Ready. Simulating weight change will trigger recording."}
                            {simState === 'RECORDING' && "Recording 3 seconds of video..."}
                            {simState === 'ANALYZING' && "Processing images with AI model..."}
                            {simState === 'DONE' && "Simulation complete. check results below."}
                        </div>
                    </div>
                )}

                {mode === 'vision' && (
                    <div className="action-group solo">
                        <button onClick={runVisionTest} disabled={loading} className="glass-btn">
                            SNAPSHOT & JUDGE
                        </button>
                    </div>
                )}

                {mode === 'simple' && (
                    <div className="action-group solo">
                        <button onClick={runWeightTest} disabled={loading} className="glass-btn">
                            TEST WEIGHT JUDGMENT
                        </button>
                    </div>
                )}

                {/* LOGS */}
                <div className="mini-log font-mono">
                    {logs.length === 0 ? <div className="placeholder">System Logs...</div> : logs.map((log, i) => <div key={i}>{log}</div>)}
                </div>

                {/* RESULTS */}
                {result && (
                    <div className="result-panel glass-card fade-in">
                        {renderResult()}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ModelTest;
