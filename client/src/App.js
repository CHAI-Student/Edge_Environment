import React, { useState } from 'react';
import Header from './components/Header/Header';
import DashboardLayout from './components/Layout/DashboardLayout';
import ZoneGrid from './components/ZoneGrid/ZoneGrid';
import LoadcellGrid from './components/LoadcellGrid/LoadcellGrid';
import DoorControl from './components/DoorControl/DoorControl';
import CameraGrid from './components/CameraGrid/CameraGrid';
import CameraControl from './components/CameraControl/CameraControl';
import ModelTest from './components/ModelTest/ModelTest';
import EventLog from './components/EventLog/EventLog';
import ConfigModal from './components/ConfigModal/ConfigModal';
import { useSSE } from './hooks/useSSE';
import { useDashboardData } from './hooks/useDashboardData';
import { api } from './services/api';

function App() {
  const sse = useSSE();
  const dashboard = useDashboardData(sse.status);
  const [isConfigOpen, setIsConfigOpen] = useState(false);

  const handleResetBaseline = async () => {
    if (window.confirm('RESET BASELINE CALIBRATION?')) {
      await api.weight.resetBaseline();
    }
  };

  const handleInitCameras = async () => {
    await api.camera.init();
  };

  const leftPanel = (
    <>
      <ZoneGrid loadcells={sse.loadcellData} zoneConfig={dashboard.config.zoneMapping} />
      <LoadcellGrid loadcells={sse.loadcellData} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '16px' }}>
        <DoorControl doorStatus={sse.doorStatus} />
        <CameraControl />
      </div>

      <div className="glass-panel" style={{ padding: '16px', borderRadius: '12px', marginTop: 'auto' }}>
        <div style={{
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          paddingBottom: '8px',
          marginBottom: '12px',
          fontSize: '12px',
          fontWeight: '700',
          color: 'var(--text-secondary)',
          letterSpacing: '2px'
        }}>
          SYSTEM CONTROLS
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button onClick={handleResetBaseline} className="glass-btn" style={{ flex: 1 }}>
            RESET CALIB
          </button>
          <button onClick={() => dashboard.refresh()} className="glass-btn" style={{ flex: 1 }}>
            REFRESH
          </button>
          <button onClick={handleInitCameras} className="glass-btn" style={{ flex: 1 }}>
            INIT CAMS
          </button>
        </div>

        <div style={{ marginTop: '8px' }}>
          <button onClick={() => setIsConfigOpen(true)} className="glass-btn" style={{ width: '100%' }}>
            CONFIGURATION
          </button>
        </div>

        <div style={{ marginTop: '16px', fontSize: '9px', color: 'var(--text-secondary)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span>NVIDIA MODE</span>
            <span className="font-mono text-primary">{dashboard.config.nvidiaMode ? 'ACTIVE' : 'DISABLED'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>EVENT STREAM</span>
            <span className={`font-mono ${sse.status.connected ? 'text-success' : 'text-error'}`}>
              {sse.status.connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
        </div>
      </div>
    </>
  );

  const rightPanel = (
    <>
      <div style={{ flex: '0 0 auto' }}>
        <CameraGrid />
      </div>
      <div style={{ flex: '0 0 auto' }}>
        <ModelTest modelInfo={dashboard.modelInfo} />
      </div>
      <div style={{ flex: '1 1 auto', minHeight: 0 }}>
        <EventLog realTimeLogs={sse.logs} />
      </div>
    </>
  );

  return (
    <div className="App">
      <Header services={{ ...dashboard.services, sse_connected: sse.status.connected }} />
      <DashboardLayout
        leftPanel={leftPanel}
        rightPanel={rightPanel}
      />
      <ConfigModal isOpen={isConfigOpen} onClose={() => setIsConfigOpen(false)} />
    </div>
  );
}

export default App;
