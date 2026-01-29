import React, { useEffect, useState, useCallback } from 'react';
import { api, CONSTANTS } from '../../services/api';
import './CameraGridStyles.css';

const CameraGrid = () => {
    const [cameras, setCameras] = useState(Array(6).fill({ status: 'unknown', preview: null }));
    const cameraNames = ['TOP VIEW', 'ZONE 0', 'ZONE 1', 'ZONE 2', 'ZONE 3', 'ZONE 4'];

    const updateCamera = (index, updates) => {
        setCameras(prev => {
            const newCameras = [...prev];
            newCameras[index] = { ...newCameras[index], ...updates };
            return newCameras;
        });
    };

    const loadPreviews = useCallback(async () => {
        try {
            const today = new Date().toISOString().split('T')[0];
            const data = await api.logs.getCameraLogs(today);
            const snapshots = data.snapshots || [];

            if (snapshots.length > 0) {
                const latest = snapshots[0];
                latest.files.forEach(file => {
                    const match = file.match(/cam_(\d+)\.jpg/);
                    if (match) {
                        const index = parseInt(match[1]);
                        const url = `${CONSTANTS.API_BASE}/api/logs/camera/${today}/${latest.time}/${file}`;
                        updateCamera(index, { preview: url, status: 'healthy' });
                    }
                });
            }
        } catch (error) {
            console.error('Failed to load camera previews', error);
        }
    }, []);

    const handleCapture = async (index) => {
        updateCamera(index, { preview: null, loading: true });
        try {
            const data = await api.camera.getFrame(index);
            if (data.frame) {
                updateCamera(index, {
                    preview: `data:image/jpeg;base64,${data.frame}`,
                    status: 'healthy',
                    loading: false
                });
            } else {
                throw new Error("No frame data");
            }
        } catch (error) {
            const url = api.camera.getPreviewUrl(index);
            updateCamera(index, {
                preview: url,
                status: 'healthy', // Optimistic
                loading: false
            });
        }
    };

    useEffect(() => {
        loadPreviews();
        const interval = setInterval(loadPreviews, 60000); // Refresh every minute
        return () => clearInterval(interval);
    }, [loadPreviews]);


    return (
        <div className="glass-panel camera-container">
            <div className="cam-header">
                <span className="title">VISION FEEDS</span>
                <span className="subtitle">{cameras.filter(c => c.status === 'healthy').length}/6 ONLINE</span>
            </div>
            <div className="cam-grid">
                {cameras.map((cam, i) => (
                    <div key={i} className="cam-feed glass-card">
                        <div className="cam-overlay-header">
                            <span className="cam-id">CAM.{i}</span>
                            <span className={`cam-status ${cam.status}`}></span>
                        </div>

                        <div className="cam-viewport">
                            {cam.loading ? (
                                <div className="cam-loading">
                                    <div className="loading-spinner"></div>
                                    <span>CONNECTING...</span>
                                </div>
                            ) : cam.preview ? (
                                <img
                                    src={cam.preview}
                                    alt={`Camera ${i}`}
                                    className="cam-image"
                                    onError={(e) => {
                                        e.target.style.display = 'none';
                                        e.target.parentElement.classList.add('error');
                                    }}
                                />
                            ) : (
                                <div className="cam-offline">NO SIGNAL</div>
                            )}
                        </div>

                        <div className="cam-controls">
                            <span className="cam-label">{cameraNames[i]}</span>
                            <button className="snap-btn" onClick={() => handleCapture(i)}>
                                SNAP
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default CameraGrid;
