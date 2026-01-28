import React, { useState } from 'react';
import Header from './components/Header/Header';
import DashboardLayout from './components/Layout/DashboardLayout';
import ZoneGrid from './components/ZoneGrid/ZoneGrid';
import LoadcellGrid from './components/LoadcellGrid/LoadcellGrid';
import DoorControl from './components/DoorControl/DoorControl';
import CameraGrid from './components/CameraGrid/CameraGrid';
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
    if (window.confirm('Reset weight baseline?')) {
      await api.weight.resetBaseline();
    }
  };

  const handleInitCameras = async () => {
    await api.camera.init();
  };

  const leftPanel = (
    <>
      <ZoneGrid loadcells={sse.loadcellData} />
      <LoadcellGrid loadcells={sse.loadcellData} />
      <DoorControl doorStatus={sse.doorStatus} />

      <div className="card">
        <div className="card-header">Controls</div>
        <div className="card-body">
          <div className="controls-row">
            <button onClick={handleResetBaseline}>Reset Baseline</button>
            <button onClick={() => dashboard.refresh()} className="secondary">Refresh</button>
            <button onClick={handleInitCameras} className="secondary">Init Cameras</button>
          </div>
          <div className="controls-row" style={{ marginTop: '8px' }}>
            <button onClick={() => setIsConfigOpen(true)} className="secondary">Config</button>
          </div>
          <div className="config-list" style={{ marginTop: '15px' }}>
            <div className="config-item">
              <span className="key">Nvidia Mode</span>
              <span className="value">{dashboard.config.nvidiaMode ? 'Enabled' : '-'}</span>
            </div>
            <div className="config-item">
              <span className="key">SSE Status</span>
              <span className="value">{sse.status.connected ? 'Connected' : 'Disconnected'}</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );

  const rightPanel = (
    <>
      <CameraGrid />
      <ModelTest modelInfo={dashboard.modelInfo} />
      <EventLog realTimeLogs={sse.logs} />
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
