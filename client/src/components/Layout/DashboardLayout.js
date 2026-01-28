import React from 'react';

const DashboardLayout = ({ leftPanel, rightPanel }) => {
    return (
        <main className="main-content">
            <aside className="left-panel">
                {leftPanel}
            </aside>
            <section className="right-panel">
                {rightPanel}
            </section>
        </main>
    );
};

export default DashboardLayout;
