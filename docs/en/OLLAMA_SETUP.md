# Ollama Integration Guide (Docker Compose Edition)

## Overview

Azazel-Pi is a hybrid AI system that uses Mock LLM (fast and lightweight) for known threats and Ollama (deep analysis) for unknown threats.

Ollama is managed via Docker Compose and integrated with PostgreSQL/Mattermost.

## Architecture

```
Suricata Alert
    ↓
┌─────────────────────────────────┐
│ Hybrid Threat Evaluation System  │
├─────────────────────────────────┤
│ 1. Legacy Rules (Base evaluation)│
│ 2. Mock LLM (Fast AI, <50ms)     │
│    ├→ Confidence ≥ 0.7: Confirmed│
│    └→ Confidence < 0.7: Unknown? │
│                                  │
│ 3. Ollama (Deep analysis, 2-5s)  │
│    └→ Detailed unknown analysis  │
└─────────────────────────────────┘
    ↓
Risk Score → Policy Application
```

## Docker Compose Configuration

`deploy/docker-compose.yml`:

```yaml
services:
  postgres:      # Mattermost database
  ollama:        # AI threat analysis engine
```

Both services can be managed centrally.

## Installation

### 1. Download Model (First Time Only)

```bash
# Create download directory
sudo mkdir -p /opt/models/qwen
sudo chown $USER:$USER /opt/models/qwen
cd /opt/models/qwen

# Download model
# URL: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF
# File: Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
# Size: ~1.1GB

# Example: Download with wget
wget https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
```

### 2. Ollama Setup

```bash
# Run automatic setup script
sudo /home/azazel/Azazel-Pi/scripts/setup_ollama.sh
```

This script performs the following:
1. Verify model file
2. Create Modelfile
3. Start container with Docker Compose
4. Create threatjudge model
5. Run functionality test

## Management Commands

### Docker Compose Operations

```bash
cd /home/azazel/Azazel-Pi/deploy

# Start all services (PostgreSQL + Ollama)
docker compose up -d

# Start Ollama only
docker compose up -d ollama

# Stop Ollama only
docker compose stop ollama

# Restart Ollama
docker compose restart ollama

# Check service status
docker compose ps

# Check logs
docker logs -f azazel_ollama
```

### Individual Commands

```bash
# List models
docker exec azazel_ollama ollama list

# Test model
docker exec azazel_ollama ollama run threatjudge "test"

# Launch shell in container
docker exec -it azazel_ollama /bin/bash
```


## Configuration

`configs/ai_config.json`:

```json
{
  "ai": {
    "ollama_url": "http://127.0.0.1:11434/api/generate",
    "model": "threatjudge",
    "timeout": 30,
    "unknown_threat_detection": {
      "enabled": true,
      "confidence_threshold": 0.7
    }
  }
}
```

## Unknown Threat Detection Triggers

Deep analysis by Ollama is executed under the following conditions:

1. **Low Confidence**: Mock LLM confidence < 0.7
2. **Unknown Category**: `unknown` or `benign` category
3. **Low Risk but Uncertain**: Risk level ≤ 2

## Verification

### Docker Compose Status Check

```bash
cd /home/azazel/Azazel-Pi/deploy
docker compose ps
```

Expected output:
```
NAME              IMAGE                  STATUS
azazel_ollama     ollama/ollama:latest   Up (healthy)
azazel_postgres   postgres:15            Up
```

### API Test

```bash
curl -X POST http://127.0.0.1:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "threatjudge",
    "prompt": "Analyze: ET SCAN Suspicious port scan",
    "stream": false
  }'
```

### Integration Test

```python
from azazel_pi.core.hybrid_threat_evaluator import evaluate_with_hybrid_system

# Test alert (unknown threat)
alert = {
    'signature': 'ET INFO Unknown suspicious activity',
    'src_ip': '192.168.1.100',
    'dest_ip': '10.0.0.1',
    'dest_port': 8888,
    'proto': 'TCP',
    'severity': 3,
    'payload_printable': 'strange binary data...'
}

# Execute evaluation
result = evaluate_with_hybrid_system(alert)
print(f"Risk: {result['risk']}/5")
print(f"Category: {result['category']}")
print(f"Method: {result['evaluation_method']}")  # Should show "ollama_unknown_threat"
print(f"Reason: {result['reason']}")
```

## Performance

| Evaluation Method | Processing Time | Use Case |
|------------------|----------------|----------|
| Mock LLM | <50ms | Known threats (majority) |
| Ollama | 2-5s | Unknown threats (minority) |

**Distribution in Production**:
- Mock LLM only: ~80-90% (fast processing)
- Ollama supplement: ~10-20% (deep analysis)

## Troubleshooting

### Ollama Container Won't Start

```bash
# Check logs
docker logs azazel_ollama

# Restart
cd /home/azazel/Azazel-Pi/deploy
docker compose restart ollama
```

### Model Not Found

```bash
# Check model list
docker exec azazel_ollama ollama list

# Recreate model
docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile
```

### Health Check Fails

```bash
# Manual check inside container
docker exec azazel_ollama ollama ps

# Check if port is open
curl http://127.0.0.1:11434/api/tags
```

### Timeout Errors

Adjust timeout in `configs/ai_config.json`:

```json
{
  "ai": {
    "timeout": 60
  }
}
```

## Auto-Start on System Boot

Docker Compose's restart policy automatically starts Ollama on system reboot.

To configure manually:

```bash
# Enable Docker service auto-start
sudo systemctl enable docker

# Auto-start containers on boot
cd /home/azazel/Azazel-Pi/deploy
docker compose up -d
```

## Resource Usage

### Memory
- **Container Resident**: ~100MB (Ollama service)
- **During Inference**: ~2-3GB (when model is loaded)
- **Recommended Memory**: 4GB+

### Disk
- **Model File**: ~1.1GB
- **Docker Volume**: ~500MB (cache, etc.)
- **Total**: ~2GB

### CPU
- **During Inference**: 50-80% (1 core)
- **Idle**: <5%

## Summary

- ✅ **Integrated Management**: Managed with PostgreSQL via Docker Compose
- ✅ **Fast**: Most threats processed instantly by Mock LLM
- ✅ **Accurate**: Unknown threats deeply analyzed by Ollama
- ✅ **Efficient**: Ollama used only when needed
- ✅ **Offline**: Runs completely locally
- ✅ **Auto-Start**: Automatically starts on system reboot

---

**Quick Start**: 
1. Download model
2. Run `sudo scripts/setup_ollama.sh`
3. Done!
