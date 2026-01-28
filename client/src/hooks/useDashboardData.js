import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';

export const useDashboardData = (sseStatus) => {
    const [services, setServices] = useState({});
    const [config, setConfig] = useState({});
    const [modelInfo, setModelInfo] = useState(null);

    // Polling refs to prevent overlapping calls
    const pollingRef = useRef(null);

    const fetchData = useCallback(async () => {
        try {
            const [statusData, modelData] = await Promise.all([
                api.dashboard.getStatus().catch(e => ({ error: e })),
                api.model.getInfo().catch(e => ({ error: e }))
            ]);

            if (!statusData.error) {
                setServices(statusData.services || {});
                setConfig({
                    nvidiaMode: statusData.config?.camera_device_map?.nvidia_mode,
                    ioBoardSSE: statusData.io_board_sse
                });
            }

            if (!modelData.error) {
                setModelInfo(modelData);
            }
        } catch (error) {
            console.error('Dashboard data fetch failed:', error);
        }
    }, []);

    // Polling fallback mechanism
    useEffect(() => {
        fetchData(); // Initial fetch

        const interval = setInterval(fetchData, 5000); // Poll status every 5s
        return () => clearInterval(interval);
    }, [fetchData]);

    return {
        services,
        config,
        modelInfo,
        refresh: fetchData
    };
};
