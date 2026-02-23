#!/usr/bin/env bash
# Unified Ollama Setup for Azazel-Edge
# Handles Docker deployment, model download, and configuration
set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
MODELS_DIR="/opt/models"
MODEL_URL="https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf"
MODEL_FILE="Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf"
MODEL_PATH="$MODELS_DIR/$MODEL_FILE"
OLLAMA_MODEL_NAME="qwen2.5-threat-v3"

# Color output functions
log() {
  printf '\033[1;34m[ollama-unified]\033[0m %s\n' "$1"
}

error() {
  printf '\033[1;31m[ollama-unified]\033[0m %s\n' "$1" >&2
  exit 1
}

success() {
  printf '\033[1;32m[ollama-unified]\033[0m %s\n' "$1"
}

warn() {
  printf '\033[1;33m[ollama-unified]\033[0m %s\n' "$1"
}

usage() {
  cat <<USAGE
Usage: $0 [OPTIONS]

Unified Ollama setup for Azazel-Edge:
- Docker service deployment
- Model download and configuration
- Integration with Azazel-Edge AI system

Options:
  --deploy-only      Deploy Ollama Docker service only (skip model setup)
  --model-only       Setup model only (assume Docker service exists)
  --force           Overwrite existing model files
  --verify-only     Only verify existing setup, don't make changes
  --skip-download   Skip model download (use existing file)
  --skip-restart    Skip service restart after setup
  -h, --help        Show this help message

Setup Phases:
  1. Docker Service Deployment (ollama container)
  2. Model Download (~1.1GB)
  3. Modelfile Creation and Registration
  4. AI Configuration Update
  5. Service Integration and Testing

Model: Qwen2.5-1.5B-Instruct-uncensored (Q4_K_M)
Size:  ~1.1GB
API:   http://127.0.0.1:11434/api/generate

USAGE
}

# Parse arguments
DEPLOY_ONLY=0
MODEL_ONLY=0
FORCE=0
VERIFY_ONLY=0
SKIP_DOWNLOAD=0
SKIP_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-only)
      DEPLOY_ONLY=1
      shift
      ;;
    --model-only)
      MODEL_ONLY=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --verify-only)
      VERIFY_ONLY=1
      shift
      ;;
    --skip-download)
      SKIP_DOWNLOAD=1
      shift
      ;;
    --skip-restart)
      SKIP_RESTART=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "Unknown option: $1. Use --help for usage."
      ;;
  esac
done

# Check for root privileges when needed
check_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    error "This operation requires root privileges. Please run with sudo."
  fi
}

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" || ! -d "scripts" ]]; then
  error "Please run this script from the Azazel-Edge project root directory"
fi

log "Unified Ollama Setup for Azazel-Edge"
echo

# Display setup summary
echo "Setup Configuration:"
echo "  Docker Service: $([ $MODEL_ONLY -eq 0 ] && echo "✓ Deploy" || echo "✗ Skip")"
echo "  Model Download: $([ $DEPLOY_ONLY -eq 0 ] && [ $SKIP_DOWNLOAD -eq 0 ] && echo "✓ Download" || echo "✗ Skip")"
echo "  Model Setup:    $([ $DEPLOY_ONLY -eq 0 ] && echo "✓ Configure" || echo "✗ Skip")"
echo "  Service Restart: $([ $SKIP_RESTART -eq 0 ] && echo "✓ Yes" || echo "✗ Skip")"
echo "  Model Name:     $OLLAMA_MODEL_NAME"
echo "  Model Size:     ~1.1GB"
echo

# Function: Deploy Docker Service
deploy_docker_service() {
  log "Phase 1/5: Docker Service Deployment"
  
  # Check Docker and Docker Compose
  if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
  fi
  
  if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
    error "Docker Compose is not installed."
  fi
  
  # Check if deploy directory exists
  if [[ ! -d "$DEPLOY_DIR" ]]; then
    error "Deploy directory not found: $DEPLOY_DIR"
  fi
  
  cd "$DEPLOY_DIR"
  
  # Create .env file if missing
  if [[ ! -f .env && $VERIFY_ONLY -eq 0 ]]; then
    warn ".env file not found, creating minimal configuration..."
    cat > .env << EOF
# Mattermost configuration (optional)
MATTERMOST_DB_NAME=mattermost
MATTERMOST_DB_USER=mmuser
MATTERMOST_DB_PASSWORD=$(openssl rand -base64 32)
EOF
  fi
  
  # Deploy Ollama service
  if [[ $VERIFY_ONLY -eq 0 ]]; then
    log "Starting Ollama Docker service..."
    docker compose up -d ollama || error "Failed to start Ollama service"
  fi
  
  # Wait for service to be ready
  log "Waiting for Ollama service to initialize..."
  for i in {1..60}; do
    if docker ps | grep -q "azazel_ollama.*Up" && \
       curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      success "Ollama service ready"
      break
    fi
    if [ $i -eq 60 ]; then
      error "Ollama service failed to start properly"
    fi
    sleep 2
  done
  
  cd "$PROJECT_ROOT"
  success "Docker service deployment completed"
}

# Function: Download and Setup Model
setup_model() {
  log "Phase 2/5: Model Download and Setup"
  
  check_root
  
  # Create models directory
  mkdir -p "$MODELS_DIR"
  
  # Step 2a: Download model if needed
  if [[ $SKIP_DOWNLOAD -eq 0 ]]; then
    if [[ -f "$MODEL_PATH" && $FORCE -eq 0 ]]; then
      MODEL_SIZE=$(stat -f%z "$MODEL_PATH" 2>/dev/null || stat -c%s "$MODEL_PATH" 2>/dev/null)
      if [[ $MODEL_SIZE -gt 1000000000 ]]; then  # > 1GB
        success "Model file already exists: $(($MODEL_SIZE / 1024 / 1024))MB"
      else
        warn "Model file seems corrupted, re-downloading..."
        FORCE=1
      fi
    fi
    
    if [[ ! -f "$MODEL_PATH" || $FORCE -eq 1 ]]; then
      log "Downloading model file (~1.1GB, this may take several minutes)..."
      
      # Download with progress
      if command -v wget >/dev/null 2>&1; then
        wget --progress=bar:force -O "$MODEL_PATH.tmp" "$MODEL_URL" || error "Download failed"
      elif command -v curl >/dev/null 2>&1; then
        curl -L --progress-bar -o "$MODEL_PATH.tmp" "$MODEL_URL" || error "Download failed"
      else
        error "Neither wget nor curl found. Please install one of them."
      fi
      
      # Verify download
      if [[ -f "$MODEL_PATH.tmp" ]]; then
        MODEL_SIZE=$(stat -f%z "$MODEL_PATH.tmp" 2>/dev/null || stat -c%s "$MODEL_PATH.tmp" 2>/dev/null)
        if [[ $MODEL_SIZE -gt 1000000000 ]]; then  # > 1GB
          mv "$MODEL_PATH.tmp" "$MODEL_PATH"
          chmod 644 "$MODEL_PATH"
          success "Model downloaded: $(($MODEL_SIZE / 1024 / 1024))MB"
        else
          rm -f "$MODEL_PATH.tmp"
          error "Downloaded file is too small. Download may have failed."
        fi
      else
        error "Download failed - temporary file not found"
      fi
    fi
  fi
  
  # Verify model file exists
  if [[ ! -f "$MODEL_PATH" ]]; then
    error "Model file not found: $MODEL_PATH. Use --skip-download if file exists elsewhere."
  fi
  
  success "Model file verified: $MODEL_PATH"
}

# Function: Create and Register Modelfile
create_modelfile() {
  log "Phase 3/5: Modelfile Creation and Registration"
  
  check_root
  
  MODELFILE_PATH="$MODELS_DIR/Qwen2.5-threat-v3.Modelfile"
  
  # Create enhanced Modelfile
  cat > "$MODELFILE_PATH" << 'EOF'
FROM /models/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

PARAMETER temperature 0.01
PARAMETER top_p 0.5
PARAMETER top_k 5
PARAMETER num_ctx 1024
PARAMETER num_predict 30

SYSTEM """You are a threat analysis API that responds ONLY with valid JSON.

RULES:
1. Always respond with exactly this JSON structure: {"score": NUMBER, "explanation": "TEXT", "action": "TEXT"}
2. Score: 0-100 (0=safe, 100=critical)
3. Action: "allow", "monitor", "delay", or "block"
4. Never respond with anything other than valid JSON

THREAT ANALYSIS:
- malware, c2, c&c, botnet, ransomware = score 85-95, action "block"
- exploit, attack, brute, injection = score 70-85, action "block" 
- suspicious, anomaly, scan = score 40-60, action "delay"
- normal, benign, legitimate = score 0-30, action "allow"

EXAMPLES:
Input: "HTTP POST to malware-c2.example.com"
Output: {"score": 95, "explanation": "C&C communication detected", "action": "block"}

Input: "SQL injection attempt"
Output: {"score": 80, "explanation": "Database attack detected", "action": "block"}

Input: "Port scan from 192.168.1.100"
Output: {"score": 50, "explanation": "Reconnaissance activity", "action": "delay"}"""
EOF
  
  success "Enhanced Modelfile created: $MODELFILE_PATH"
  
  # Register model with Ollama
  if [[ $VERIFY_ONLY -eq 0 ]]; then
    log "Registering model '$OLLAMA_MODEL_NAME' with Ollama..."
    
    if docker exec azazel_ollama ollama create "$OLLAMA_MODEL_NAME" -f "/models/Qwen2.5-threat-v3.Modelfile"; then
      success "Model '$OLLAMA_MODEL_NAME' registered successfully"
    else
      error "Failed to register Ollama model"
    fi
  fi
  
  # Verify model registration
  if docker exec azazel_ollama ollama list | grep -q "$OLLAMA_MODEL_NAME"; then
    success "Model '$OLLAMA_MODEL_NAME' is available in Ollama"
  else
    error "Model '$OLLAMA_MODEL_NAME' not found in Ollama registry"
  fi
}

# Function: Update AI Configuration
update_ai_config() {
  log "Phase 4/5: AI Configuration Update"
  
  if [[ $VERIFY_ONLY -eq 0 ]]; then
    check_root
    
    # Update ai_config.json
    if [[ -f "configs/ai_config.json" ]]; then
      # Backup original
      cp "configs/ai_config.json" "configs/ai_config.json.bak"
      
      # Update model name
      sed -i 's/"model": "[^"]*"/"model": "'$OLLAMA_MODEL_NAME'"/' configs/ai_config.json
      
      # Copy to system location
      mkdir -p /etc/azazel
      cp configs/ai_config.json /etc/azazel/ai_config.json
      
      success "AI configuration updated with model: $OLLAMA_MODEL_NAME"
    else
      warn "configs/ai_config.json not found, skipping configuration update"
    fi
  fi
}

# Function: Test and Integrate Services
test_and_integrate() {
  log "Phase 5/5: Testing and Service Integration"
  
  # Test model response
  log "Testing model functionality..."
  TEST_PROMPT="malware-c2.example.com"
  
  if timeout 30 curl -s -X POST http://127.0.0.1:11434/api/generate \
     -H "Content-Type: application/json" \
     -d "{\"model\": \"$OLLAMA_MODEL_NAME\", \"prompt\": \"$TEST_PROMPT\", \"stream\": false}" | \
     grep -q '"response"'; then
    success "Model test successful"
  else
    warn "Model test failed or timed out (this may be normal for first run)"
  fi
  
  # Restart Azazel services if requested
  if [[ $SKIP_RESTART -eq 0 && $VERIFY_ONLY -eq 0 ]]; then
    if systemctl is-active --quiet azctl-unified.service; then
      check_root
      log "Restarting Azazel services with new configuration..."
      systemctl restart azctl-unified.service
      sleep 3
      
      if systemctl is-active --quiet azctl-unified.service; then
        success "Azazel services restarted successfully"
      else
        warn "Azazel service restart may have issues"
      fi
    else
      log "Azazel service not running, skipping restart"
    fi
  fi
}

# Function: Display Final Status
show_final_status() {
  log "Setup Status Summary"
  echo
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📊 Ollama System Status:"
  echo
  
  # Check Docker service
  if docker ps | grep -q "azazel_ollama.*Up"; then
    echo "✅ Docker Service: azazel_ollama running"
  else
    echo "❌ Docker Service: azazel_ollama not running"
  fi
  
  # Check model file
  if [[ -f "$MODEL_PATH" ]]; then
    MODEL_SIZE=$(stat -f%z "$MODEL_PATH" 2>/dev/null || stat -c%s "$MODEL_PATH" 2>/dev/null)
    echo "✅ Model File: $(($MODEL_SIZE / 1024 / 1024))MB at $MODEL_PATH"
  else
    echo "❌ Model File: Not found at $MODEL_PATH"
  fi
  
  # Check Ollama model
  if docker exec azazel_ollama ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL_NAME"; then
    echo "✅ Ollama Model: $OLLAMA_MODEL_NAME registered"
  else
    echo "❌ Ollama Model: $OLLAMA_MODEL_NAME not registered"
  fi
  
  # Check AI config
  if [[ -f "/etc/azazel/ai_config.json" ]] && grep -q "$OLLAMA_MODEL_NAME" "/etc/azazel/ai_config.json" 2>/dev/null; then
    echo "✅ AI Config: Model configuration updated"
  else
    echo "⚠️  AI Config: Not updated or model name mismatch"
  fi
  
  # Check Azazel service
  if systemctl is-active --quiet azctl-unified.service 2>/dev/null; then
    echo "✅ Azazel Service: Running and integrated"
  else
    echo "⚠️  Azazel Service: Not running (manual start may be needed)"
  fi
  
  # API accessibility
  if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "✅ API Access: http://127.0.0.1:11434 responding"
  else
    echo "❌ API Access: Ollama API not responding"
  fi
  
  echo
  echo "🎯 Quick Commands:"
  echo "   • Test model:    curl -X POST http://127.0.0.1:11434/api/generate -H 'Content-Type: application/json' -d '{\"model\": \"$OLLAMA_MODEL_NAME\", \"prompt\": \"test malware\", \"stream\": false}'"
  echo "   • Check status:  python3 -m azctl.cli status"
  echo "   • View logs:     docker logs -f azazel_ollama"
  echo "   • AI decisions:  tail -f /var/log/azazel/decisions.log"
  echo
  echo "🔧 Management:"
  echo "   • Start all:     cd $DEPLOY_DIR && docker compose up -d"
  echo "   • Stop Ollama:   cd $DEPLOY_DIR && docker compose stop ollama"
  echo "   • Restart:       cd $DEPLOY_DIR && docker compose restart ollama"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Main execution logic
if [[ $VERIFY_ONLY -eq 1 ]]; then
  log "Verification mode - checking existing setup"
fi

# Execute phases based on options
if [[ $MODEL_ONLY -eq 0 ]]; then
  deploy_docker_service
fi

if [[ $DEPLOY_ONLY -eq 0 ]]; then
  setup_model
  create_modelfile
  update_ai_config
  test_and_integrate
fi

# Always show final status
show_final_status

if [[ $VERIFY_ONLY -eq 0 ]]; then
  success "Unified Ollama setup completed successfully!"
  echo
  log "The Enhanced AI Integration v3 system is now ready for use."
  log "Unknown threats will be analyzed by Ollama while known threats use fast paths."
else
  log "Verification completed."
fi

exit 0