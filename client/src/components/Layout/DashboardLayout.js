import React from 'react';

const DashboardLayout = ({ leftPanel, rightPanel }) => {
    return (
        <main className="main-content" style={{ display: 'flex', height: 'calc(100vh - var(--header-height) - 16px)', gap: '16px', padding: '0 16px 16px' }}>
            <aside className="left-panel" style={{
                width: 'var(--sidebar-width)',
                minWidth: '320px',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
                overflowY: 'auto'
            }}>
                {leftPanel}
            </aside>
            <section className="right-panel" style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
                overflowY: 'auto',
                minWidth: '0' /* Prevent flex overflow */
            }}>
                {rightPanel}
            </section>
        </main>
    );
};

export default DashboardLayout;
