/**
 * Custom proxy configuration for Create React App
 *
 * This is needed because the simple "proxy" field in package.json
 * buffers responses, which breaks Server-Sent Events (SSE).
 */

const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
    // Proxy API requests
    app.use(
        '/api',
        createProxyMiddleware({
            target: 'http://localhost:8889',
            changeOrigin: true,
        })
    );

    // Proxy SSE requests with special handling
    app.use(
        '/sse',
        createProxyMiddleware({
            target: 'http://localhost:8889',
            changeOrigin: true,
            // Disable response buffering for SSE
            onProxyRes: (proxyRes, req, res) => {
                // Set headers to prevent buffering
                proxyRes.headers['X-Accel-Buffering'] = 'no';
                proxyRes.headers['Cache-Control'] = 'no-cache';
            },
        })
    );

    // Proxy health check
    app.use(
        '/health',
        createProxyMiddleware({
            target: 'http://localhost:8889',
            changeOrigin: true,
        })
    );
};
