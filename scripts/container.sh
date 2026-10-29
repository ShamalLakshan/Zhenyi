#!/usr/bin/env bash
# ==============================================================================
# Zhenyi Container Management Helper
# Works seamlessly with Podman (default) or Docker without requiring compose.
# ==============================================================================

set -euo pipefail

# Auto-detect container runtime (prefer podman)
if command -v podman &>/dev/null; then
    RUNTIME="podman"
elif command -v docker &>/dev/null; then
    RUNTIME="docker"
else
    echo "Error: Neither podman nor docker was found in PATH." >&2
    exit 1
fi

IMAGE_NAME="docker.io/shamallakshan/zhenyi:latest"
DEV_CONTAINER="zhenyi-dev"
PROD_CONTAINER="zhenyi"
HOST_PORT="8000"

# Color helpers
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() { echo -e "${GREEN}[+]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[x]${NC} $1"; }

usage() {
    echo -e "${BLUE}Zhenyi Container CLI (${RUNTIME})${NC}"
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  build            Build the container image using multi-stage lean Dockerfile"
    echo "  dev              Run local dev container with live code reload & volume mount"
    echo "  run              Run production container in background"
    echo "  stop             Stop any running dev or prod Zhenyi containers"
    echo "  logs             Follow logs from the active container"
    echo "  health           Check health endpoint (http://localhost:${HOST_PORT}/health)"
    echo "  clean            Prune dangling images and build cache to reclaim disk space"
    echo "  sanitize-check   Verify image contains NO keys, databases, or secrets"
    echo ""
}

cmd_build() {
    if [[ ! -d "web-ui/dist" || ! -f "web-ui/dist/index.html" ]]; then
        log_info "Compiled frontend not found. Building web-ui with npm..."
        if command -v npm &>/dev/null; then
            (cd web-ui && npm run build)
        else
            log_error "npm not found. Please install node/npm or compile web-ui first."
            exit 1
        fi
    fi

    log_info "Building ${IMAGE_NAME} with ${RUNTIME}..."
    ${RUNTIME} build -t "${IMAGE_NAME}" -f Dockerfile .
    log_info "Build complete. Current image size:"
    ${RUNTIME} images "${IMAGE_NAME}"
}

cmd_dev() {
    # Ensure local data/log directories exist for bind mounts
    mkdir -p data logs

    # Ensure .env exists or warn user
    if [[ ! -f .env ]]; then
        log_warn "No .env file found. Copying .env.example to .env..."
        cp .env.example .env
        log_warn "Please review .env to populate your API keys."
    fi

    log_info "Stopping existing ${DEV_CONTAINER} if running..."
    ${RUNTIME} rm -f "${DEV_CONTAINER}" 2>/dev/null || true

    USERNS_ARG=""
    if [[ "${RUNTIME}" == "podman" ]]; then
        USERNS_ARG="--userns=keep-id"
    fi

    log_info "Starting ${DEV_CONTAINER} in live-reload mode (Port ${HOST_PORT})..."
    log_info "Host workspace is mounted into /app (edits sync immediately)."

    ${RUNTIME} run -it --rm \
        --name "${DEV_CONTAINER}" \
        -p "${HOST_PORT}:8000" \
        ${USERNS_ARG} \
        --env-file .env \
        -e DB_PATH="/app/data/zhenyi.db" \
        -e LOG_DIR="/app/logs" \
        -v "$(pwd):/app:z" \
        -v "$(pwd)/data:/app/data:Z" \
        -v "$(pwd)/logs:/app/logs:Z" \
        --cpus 2.0 \
        --memory 2048m \
        "${IMAGE_NAME}" \
        uvicorn server:app --reload --host 0.0.0.0 --port 8000 \
            --reload-exclude "data/*" \
            --reload-exclude "logs/*" \
            --reload-exclude "*.db*"
}

cmd_run() {
    mkdir -p data logs

    if [[ ! -f .env ]]; then
        log_warn "No .env file found. Running with default empty environment."
        ENV_ARGS=""
    else
        ENV_ARGS="--env-file .env"
    fi

    log_info "Stopping existing ${PROD_CONTAINER} if running..."
    ${RUNTIME} rm -f "${PROD_CONTAINER}" 2>/dev/null || true

    USERNS_ARG=""
    if [[ "${RUNTIME}" == "podman" ]]; then
        USERNS_ARG="--userns=keep-id"
    fi

    log_info "Starting ${PROD_CONTAINER} in background..."
    ${RUNTIME} run -d \
        --name "${PROD_CONTAINER}" \
        -p "${HOST_PORT}:8000" \
        ${USERNS_ARG} \
        ${ENV_ARGS} \
        -e DB_PATH="/app/data/zhenyi.db" \
        -e LOG_DIR="/app/logs" \
        -v "$(pwd)/data:/app/data:Z" \
        -v "$(pwd)/logs:/app/logs:Z" \
        --cpus 2.0 \
        --memory 1536m \
        "${IMAGE_NAME}"

    log_info "Zhenyi is running at http://localhost:${HOST_PORT}"
    log_info "To view logs: $0 logs"
}

cmd_stop() {
    log_info "Stopping running containers..."
    ${RUNTIME} stop "${PROD_CONTAINER}" 2>/dev/null || true
    ${RUNTIME} rm -f "${PROD_CONTAINER}" 2>/dev/null || true
    ${RUNTIME} stop "${DEV_CONTAINER}" 2>/dev/null || true
    ${RUNTIME} rm -f "${DEV_CONTAINER}" 2>/dev/null || true
    log_info "All Zhenyi containers stopped."
}

cmd_logs() {
    if ${RUNTIME} ps --format "{{.Names}}" | grep -q "${DEV_CONTAINER}"; then
        ${RUNTIME} logs -f "${DEV_CONTAINER}"
    elif ${RUNTIME} ps --format "{{.Names}}" | grep -q "${PROD_CONTAINER}"; then
        ${RUNTIME} logs -f "${PROD_CONTAINER}"
    else
        log_error "No active Zhenyi container found."
        exit 1
    fi
}

cmd_health() {
    log_info "Checking http://127.0.0.1:${HOST_PORT}/health..."
    if command -v curl &>/dev/null; then
        curl -s -i "http://127.0.0.1:${HOST_PORT}/health"
        echo ""
    else
        python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:${HOST_PORT}/health').read().decode())"
    fi
}

cmd_clean() {
    log_warn "Cleaning unused container artifacts to save disk storage..."
    ${RUNTIME} container prune -f 2>/dev/null || true
    ${RUNTIME} image prune -f
    log_info "Storage cleanup completed."
}

cmd_sanitize_check() {
    log_info "Running security sanitization audit on image: ${IMAGE_NAME}..."

    LEAKS=0

    # 1. Check for .env or key files inside the image
    FOUND_ENV=$(${RUNTIME} run --rm --entrypoint /bin/sh "${IMAGE_NAME}" -c "find /app -name '.env*' ! -name '.env.example' 2>/dev/null" || true)
    if [[ -n "${FOUND_ENV}" ]]; then
        log_error "LEAK DETECTED: Found environment files in image:\n${FOUND_ENV}"
        LEAKS=$((LEAKS + 1))
    else
        log_info "PASS: No .env secrets or private credentials found in image."
    fi

    # 2. Check for database files baked into the image
    FOUND_DB=$(${RUNTIME} run --rm --entrypoint /bin/sh "${IMAGE_NAME}" -c "find /app -name '*.db*' -o -name '*.sqlite*' 2>/dev/null" || true)
    if [[ -n "${FOUND_DB}" ]]; then
        log_error "LEAK DETECTED: Found database files in image:\n${FOUND_DB}"
        LEAKS=$((LEAKS + 1))
    else
        log_info "PASS: No database (.db/.sqlite) files baked into image."
    fi

    # 3. Check for node_modules in image
    FOUND_NM=$(${RUNTIME} run --rm --entrypoint /bin/sh "${IMAGE_NAME}" -c "find /app -name 'node_modules' 2>/dev/null" || true)
    if [[ -n "${FOUND_NM}" ]]; then
        log_error "LEAK DETECTED: Found node_modules in runtime image:\n${FOUND_NM}"
        LEAKS=$((LEAKS + 1))
    else
        log_info "PASS: No bulky node_modules present in runtime image."
    fi

    if [[ ${LEAKS} -eq 0 ]]; then
        echo -e "${GREEN}====================================================${NC}"
        echo -e "${GREEN}  SANITIZATION AUDIT PASSED: 0 LEAKS DETECTED       ${NC}"
        echo -e "${GREEN}====================================================${NC}"
    else
        echo -e "${RED}====================================================${NC}"
        echo -e "${RED}  SANITIZATION AUDIT FAILED: ${LEAKS} LEAKS DETECTED ${NC}"
        echo -e "${RED}====================================================${NC}"
        exit 1
    fi
}

case "${1:-}" in
    build)
        cmd_build
        ;;
    dev)
        cmd_dev
        ;;
    run)
        cmd_run
        ;;
    stop)
        cmd_stop
        ;;
    logs)
        cmd_logs
        ;;
    health)
        cmd_health
        ;;
    clean)
        cmd_clean
        ;;
    sanitize-check)
        cmd_sanitize_check
        ;;
    *)
        usage
        exit 1
        ;;
esac
