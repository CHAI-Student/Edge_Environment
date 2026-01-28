import { useState, useEffect, useCallback } from 'react';
import { CONSTANTS } from '../services/api';

export const useSSE = () => {
    const [status, setStatus] = useState({
        connected: false,
        ioBoard: false
    });

    // Using a ref or just state to broader scope might be needed if we want to expose raw data streams
    // For now, we'll expose the latest data for key entities
    const [loadcellData, setLoadcellData] = useState([]);
    const [latestWeightEvent, setLatestWeightEvent] = useState(null);
    const [doorStatus, setDoorStatus] = useState({ door: null, deadbolt: null });
    const [logs, setLogs] = useState([]); // Buffer for recent events

    const connect = useCallback(() => {
        const eventSource = new EventSource(`${CONSTANTS.API_BASE}/sse/events`);

        eventSource.onopen = () => {
            setStatus(prev => ({ ...prev, connected: true }));
        };

        eventSource.onerror = () => {
            setStatus(prev => ({ ...prev, connected: false }));
            eventSource.close();
            // Simple exponential backoff or retry logic could be added here
            setTimeout(connect, 5000);
        };

        eventSource.addEventListener('connected', () => {
            setStatus(prev => ({ ...prev, connected: true }));
        });

        eventSource.addEventListener('io_board_connected', () => {
            setStatus(prev => ({ ...prev, ioBoard: true }));
        });

        eventSource.addEventListener('io_board_disconnected', () => {
            setStatus(prev => ({ ...prev, ioBoard: false }));
        });

        // Data Events
        eventSource.addEventListener('loadcell_update', (e) => {
            try {
                const data = JSON.parse(e.data);
                const values = data.weights || data.filtered_values || data.raw_values || data.loadcells;
                if (values && values.length > 0) {
                    setLoadcellData(values);
                }
            } catch (err) {
                console.error('SSE Parse Error (loadcell_update):', err);
            }
        });

        eventSource.addEventListener('weight_change', (e) => {
            try {
                const data = JSON.parse(e.data);
                setLatestWeightEvent(data);
                addLog('weight', data);
            } catch (err) {
                console.error('SSE Parse Error (weight_change):', err);
            }
        });

        eventSource.addEventListener('door_update', (e) => {
            try {
                const data = JSON.parse(e.data);
                setDoorStatus({ door: data.door, deadbolt: data.deadbolt });
            } catch (err) {
                console.error('SSE Parse Error (door_update):', err);
            }
        });

        eventSource.addEventListener('door_opened', (e) => {
            const data = JSON.parse(e.data);
            addLog('door', { event: 'Door Opened', ...data });
        });

        eventSource.addEventListener('door_closed', (e) => {
            const data = JSON.parse(e.data);
            addLog('door', { event: 'Door Closed', ...data });
        });

        eventSource.addEventListener('deadbolt_changed', (e) => {
            const data = JSON.parse(e.data);
            addLog('door', { event: `Deadbolt: ${data.previous} -> ${data.current}`, ...data });
        });

        return eventSource;
    }, []);

    const addLog = (type, data) => {
        setLogs(prev => {
            const newLog = { type, data, timestamp: new Date() };
            const updated = [newLog, ...prev];
            return updated.slice(0, 100); // Keep last 100
        });
    };

    useEffect(() => {
        const es = connect();
        return () => {
            if (es) es.close();
        };
    }, [connect]);

    return {
        status,
        loadcellData,
        latestWeightEvent,
        doorStatus,
        logs,
        setDoorStatus // Allow manual updates (e.g., from polling)
    };
};
