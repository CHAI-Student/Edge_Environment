import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../../services/api';

const CameraGrid = () => {
    const [cameras, setCameras] = useState(Array(6).fill({ status: 'unknown', preview: null }));
    const cameraNames = ['Top Camera', 'Zone 0 Side', 'Zone 1 Side', 'Zone 2 Side', 'Zone 3 Side', 'Zone 4 Side'];

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
                        const url = `${api.CONSTANTS.API_BASE}/api/logs/camera/${today}/${latest.time}/${file}`;
                        updateCamera(index, { preview: url, status: 'healthy' });
                    }
                });
            }
        } catch (error) {
            console.error('Failed to load camera previews', error);
        }
    }, []);

    const handleCapture = async (index) => {
        updateCamera(index, { preview: null, loading: true }); // Clear/Loading state
        try {
            // Try getting base64 frame first
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
            console.warn(`Base64 capture failed for cam ${index}, trying raw URL fallback`, error);
            // Fallback to raw URL
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
        <div className="card">
            <div className="card-header">Cameras</div>
            <div className="card-body">
                <div className="camera-grid">
                    {cameras.map((cam, i) => (
                        <div key={i} className="camera-item">
                            <div className="camera-header">
                                <span className="camera-name">{cameraNames[i]}</span>
                                <button
                                    onClick={() => handleCapture(i)}
                                    style={{ padding: '2px 6px', fontSize: '10px', flex: 'none', marginRight: '5px' }}
                                >
                                    Shot
                                </button>
                                <span className={`status-dot ${cam.status}`}></span>
                            </div>
                            <div className="camera-preview">
                                {cam.loading ? (
                                    <div style={{ color: 'var(--warning)' }}>Capturing...</div>
                                ) : cam.preview ? (
                                    <img
                                        src={cam.preview}
                                        alt={`Camera ${i}`}
                                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                        onError={(e) => {
                                            e.target.style.display = 'none';
                                            e.target.parentElement.innerText = 'Preview Error';
                                        }}
                                    />
                                ) : (
                                    'No preview'
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default CameraGrid;
