#!/usr/bin/env bash
# Ollama Setup for Azazel-Pi using Docker Compose
# Integrates with existing PostgreSQL/Mattermost setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
MODELS_DIR="/opt/models/qwen"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# Check Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
    error "Docker Compose is not installed."
    exit 1
fi

# Setup models directory
log "Setting up models directory..."
sudo mkdir -p "$MODELS_DIR"
sudo chown "$USER:$USER" "$MODELS_DIR"

# Check if model file exists
MODEL_FILE="$MODELS_DIR/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf"
if [ ! -f "$MODEL_FILE" ]; then
    error "Model file not found: $MODEL_FILE"
    echo ""
    echo "📥 Please download the model manually:"
    echo "   1. Visit: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF"
    echo "   2. Download: Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf"
    echo "   3. Place in: $MODELS_DIR/"
    echo "   4. Run this script again"
    echo ""
    exit 1
fi

log "Model file verified: $(du -h "$MODEL_FILE" | cut -f1)"

# Create Modelfile if not exists
MODELFILE_PATH="$MODELS_DIR/Modelfile"
if [ ! -f "$MODELFILE_PATH" ]; then
    log "Creating Modelfile..."
    cat <<'EOF' | sudo tee "$MODELFILE_PATH" > /dev/null
FROM /models/qwen/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

TEMPLATE """{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
"""

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"
PARAMETER num_ctx 1024
PARAMETER num_predict 128
PARAMETER temperature 0.2

SYSTEM """ネットワークセキュリティアラートの脅威度を正確に評価し、JSON形式で回答します。"""
EOF
fi

# Start Ollama service with Docker Compose
log "Starting Ollama service via Docker Compose..."
cd "$DEPLOY_DIR"

# Check if .env file exists
if [ ! -f .env ]; then
    warn ".env file not found in $DEPLOY_DIR"
    log "Creating minimal .env file..."
    cat > .env << EOF
# Mattermost configuration (optional)
MATTERMOST_DB_NAME=mattermost
MATTERMOST_DB_USER=mmuser
MATTERMOST_DB_PASSWORD=$(openssl rand -base64 32)
EOF
fi

# Start only Ollama service (don't affect PostgreSQL)
docker compose up -d ollama

# Wait for Ollama to be ready
log "Waiting for Ollama service..."
for i in {1..60}; do
    if docker exec azazel_ollama ollama ps &>/dev/null; then
        log "Ollama service ready"
        break
    fi
    if [ $i -eq 60 ]; then
        error "Ollama service failed to start"
        docker logs azazel_ollama --tail 20
        exit 1
    fi
    sleep 1
done

# Check if model already exists
MODEL_EXISTS=$(docker exec azazel_ollama ollama list 2>/dev/null | grep -c "^threatjudge" || true)

if [ "$MODEL_EXISTS" -eq 0 ]; then
    log "Creating threatjudge model in Ollama..."
    docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile
    log "Threatjudge model created successfully"
else
    log "Threatjudge model already exists"
fi

# Test the model
log "Testing threatjudge model..."
TEST_RESPONSE=$(curl -s -X POST http://127.0.0.1:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model": "threatjudge", "prompt": "Test", "stream": false}' \
    --max-time 10)

if echo "$TEST_RESPONSE" | grep -q '"response"'; then
    log "Model test successful"
else
    error "Model test failed"
    echo "$TEST_RESPONSE"
    exit 1
fi

log ""
log "✅ Ollama setup completed successfully!"
log ""
log "📊 Status:"
docker exec azazel_ollama ollama list
log ""
log "🐳 Docker Services:"
docker compose ps
log ""
log "🔧 Configuration:"
echo "  - API URL: http://127.0.0.1:11434/api/generate"
echo "  - Model: threatjudge"
echo "  - Config: configs/ai_config.json"
log ""
log "🧪 Test command:"
echo "  curl -X POST http://127.0.0.1:11434/api/generate -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\": \"threatjudge\", \"prompt\": \"Analyze SSH brute force\", \"stream\": false}'"
log ""
log "📝 Management commands:"
echo "  - Start:   cd $DEPLOY_DIR && docker compose up -d ollama"
echo "  - Stop:    cd $DEPLOY_DIR && docker compose stop ollama"
echo "  - Restart: cd $DEPLOY_DIR && docker compose restart ollama"
echo "  - Logs:    docker logs -f azazel_ollama"
echo "  - All:     cd $DEPLOY_DIR && docker compose up -d  # Start all services"
