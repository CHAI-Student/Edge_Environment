#!/bin/bash
# AI Smart Vending Machine - Jetson Deployment Script
#
# Usage:
#   ./deploy.sh [build|deploy|restart|logs|status|stop]
#
# Configuration:
#   Edit the variables below or set them as environment variables

set -e

# ============================================
# Configuration
# ============================================
REMOTE_HOST="${REMOTE_HOST:-jetson@192.168.1.100}"
REMOTE_PATH="${REMOTE_PATH:-/home/jetson/ai-vending}"
PROJECT_NAME="ai-vending"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# Functions
# ============================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Sync source files to Jetson
sync_files() {
    log_info "Syncing files to ${REMOTE_HOST}:${REMOTE_PATH}..."

    rsync -avz --progress \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='client/node_modules' \
        --exclude='_archive' \
        --exclude='data/' \
        --exclude='logs/' \
        --exclude='*.log' \
        --exclude='.env' \
        . "${REMOTE_HOST}:${REMOTE_PATH}"

    log_info "File sync complete"
}

# Build Docker images on Jetson
build_images() {
    log_info "Building Docker images on Jetson..."

    ssh "${REMOTE_HOST}" << EOF
cd ${REMOTE_PATH}
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build --parallel
EOF

    log_info "Build complete"
}

# Deploy and start services
deploy_services() {
    log_info "Deploying services to Jetson..."

    ssh "${REMOTE_HOST}" << EOF
cd ${REMOTE_PATH}
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml up -d
EOF

    log_info "Deployment complete"
}

# Restart all services
restart_services() {
    log_info "Restarting services..."

    ssh "${REMOTE_HOST}" << EOF
cd ${REMOTE_PATH}
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml restart
EOF

    log_info "Restart complete"
}

# Show logs
show_logs() {
    local service="${1:-}"

    if [ -n "$service" ]; then
        log_info "Showing logs for ${service}..."
        ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && docker compose logs -f ${service}"
    else
        log_info "Showing all logs..."
        ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && docker compose logs -f"
    fi
}

# Show status
show_status() {
    log_info "Checking service status..."

    ssh "${REMOTE_HOST}" << EOF
cd ${REMOTE_PATH}
echo "=== Container Status ==="
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml ps

echo ""
echo "=== Health Check ==="
for port in 8000 8002 8003 8004 8006 8888; do
    status=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:\${port}/health 2>/dev/null || echo "000")
    if [ "\$status" = "200" ]; then
        echo "Port \${port}: ✓ OK"
    else
        echo "Port \${port}: ✗ FAIL (HTTP \$status)"
    fi
done

echo ""
echo "=== GPU Status ==="
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv 2>/dev/null || echo "GPU info not available"
EOF
}

# Stop all services
stop_services() {
    log_info "Stopping services..."

    ssh "${REMOTE_HOST}" << EOF
cd ${REMOTE_PATH}
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml down
EOF

    log_info "Services stopped"
}

# Full deployment (sync + build + deploy)
full_deploy() {
    log_info "Starting full deployment..."
    sync_files
    build_images
    deploy_services
    log_info "Full deployment complete!"
    show_status
}

# Install systemd service
install_systemd() {
    log_info "Installing systemd service..."

    ssh "${REMOTE_HOST}" << EOF
sudo cp ${REMOTE_PATH}/deploy/jetson/systemd/ai-vending.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-vending.service
EOF

    log_info "Systemd service installed. Use 'sudo systemctl start ai-vending' to start."
}

# Print usage
print_usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  sync      - Sync files to Jetson"
    echo "  build     - Build Docker images on Jetson"
    echo "  deploy    - Start services on Jetson"
    echo "  full      - Full deployment (sync + build + deploy)"
    echo "  restart   - Restart all services"
    echo "  logs [svc]- Show logs (optionally for specific service)"
    echo "  status    - Show service status"
    echo "  stop      - Stop all services"
    echo "  systemd   - Install systemd service"
    echo ""
    echo "Environment variables:"
    echo "  REMOTE_HOST - SSH target (default: jetson@192.168.1.100)"
    echo "  REMOTE_PATH - Deployment path (default: /home/jetson/ai-vending)"
}

# ============================================
# Main
# ============================================

case "${1:-}" in
    sync)
        sync_files
        ;;
    build)
        build_images
        ;;
    deploy)
        deploy_services
        ;;
    full)
        full_deploy
        ;;
    restart)
        restart_services
        ;;
    logs)
        show_logs "$2"
        ;;
    status)
        show_status
        ;;
    stop)
        stop_services
        ;;
    systemd)
        install_systemd
        ;;
    *)
        print_usage
        exit 1
        ;;
esac
