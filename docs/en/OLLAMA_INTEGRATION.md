# Azazel-Edge Ollama Integration - Design Implementation Complete

## Overview
Complete implementation of a real-time threat detection and automatic response system
using Ollama + Qwen2.5-1.5B-Instruct-q4_K_M on Raspberry Pi 5

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Suricata      │───▶│  Alert Handler  │───▶│  Policy Engine  │
│   EVE JSON      │    │  (AI Enhanced)  │    │  tc/nftables    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
                    ┌─────────────────┐    ┌─────────────────┐
                    │     Ollama      │    │   Mattermost    │
                    │  Qwen2.5-1.5B   │    │  Notification   │
                    └─────────────────┘    └─────────────────┘

Host: /opt/models/qwen/*.gguf (Read-Only)
  ↓ Volume Mount
Docker: Ollama Container (Inference Engine Only)
  ↓ HTTP API (127.0.0.1:11434)
Handler: alert_handler.py (Utilizing existing ai_evaluator.py)
  ↓ Risk Assessment & Action
System: tc/nftables + Mattermost Notification
```

## File Structure

```
/opt/models/qwen/
├── Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf  # 1.5GB Model file
├── Modelfile                                      # Ollama config  
├── model_info.json                                # Metadata
└── model.sha256                                   # Checksum

/opt/azazel/
├── docker-compose.yml                 # Ollama integrated version
├── alert_handler.py                   # Main handler
├── policy_delay.sh                    # tc delay control
├── policy_block.sh                    # nftables blocking
└── .env                              # Environment settings

Azazel-Edge/
├── deploy/
│   ├── docker-compose-ollama.yml     # Docker configuration
│   ├── alert_handler.py              # Alert handler
│   ├── policy_*.sh                   # Policy scripts
│   └── models/                       # Model settings
├── scripts/
│   └── install_ollama.sh             # Automatic installation
├── azazel_edge/core/
│   ├── ai_config.py                  # AI config (Ollama enabled)
│   └── ai_evaluator.py               # Existing AI evaluator (supported)
└── configs/
    └── ai_config.json                # Ollama config (updated)
```

## Installation Steps

### 1. Pre-download Model (Required)
```bash
# Create model directory
sudo mkdir -p /opt/models/qwen
sudo chown $USER:$USER /opt/models/qwen
```

**Browser Download (Recommended - Faster):**
1. Access https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF
2. Download `Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf`
3. Place in `/opt/models/qwen/`

**Command Line Download (Takes time):**
```bash
cd /opt/models/qwen
wget https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
```

### 2. Run Automatic Installation
```bash
cd /home/azazel/Azazel-Edge
sudo ./scripts/install_ollama.sh
```

### 3. Manual Installation (For Debugging)
```bash
# 1. Verify model is placed
ls -la /opt/models/qwen/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

# 3. Place configuration files
sudo mkdir -p /opt/azazel
cd /home/azazel/Azazel-Edge
cp deploy/docker-compose-ollama.yml /opt/azazel/docker-compose.yml
cp deploy/alert_handler.py /opt/azazel/
cp deploy/policy_*.sh /opt/azazel/
cp deploy/models/* /opt/models/qwen/

# 4. Set permissions
chmod +x /opt/azazel/policy_*.sh
chmod +x /opt/azazel/alert_handler.py

# 5. Start service
cd /opt/azazel
docker-compose up -d ollama

# 6. Register model
sleep 10
docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile

# 7. Start handler
docker-compose up -d threat-handler
```

## Configuration

### Environment Variables (.env)
```bash
# Mattermost notification
MATTERMOST_WEBHOOK=https://your-mattermost.com/hooks/xxx

# Ollama settings
AZ_MODEL=threatjudge
OLLAMA_URL=http://127.0.0.1:11434/api/generate
LOG_LEVEL=INFO

# Network
AZ_INTERFACE=eth0
```

### Suricata Configuration
```yaml
outputs:
  - eve-log:
      enabled: yes
      filename: /var/log/suricata/eve.json
      types:
        - alert:
            payload: yes
            payload-printable: yes
            metadata: yes

vars:
  address-groups:
    HOME_NET: "[172.16.0.254]"  # Azazel-Edge's own IP
```

## Verification

### 1. Service Status Check
```bash
# Docker services
cd /opt/azazel
docker-compose ps

# Ollama model
docker exec azazel_ollama ollama list

# Log monitoring
docker logs -f azazel_threat_handler
```

### 2. Test Execution
```bash
# Inject dummy alert
echo '{"event_type":"alert","src_ip":"1.2.3.4","dest_ip":"172.16.0.254","proto":"tcp","dest_port":22,
"alert":{"signature":"SSH brute-force attempt"},
"payload_printable":"user: root pass: 123456"}' | sudo tee -a /var/log/suricata/eve.json

# Check policy
tc -s qdisc show dev eth0
sudo nft list ruleset | grep -A2 'table inet azazel'
```

### 3. AI Response Test
```bash
# Direct Ollama test
docker exec -it azazel_ollama ollama run threatjudge "SSH brute-force from 1.2.3.4"
```

## Feature Details

### Risk Level Determination
- **1-2**: Log recording only
- **3**: tc delay control (200ms)
- **4-5**: Complete nftables blocking

### AI Processing Flow
1. Parse Suricata EVE JSON
2. Qwen2.5-1.5B threat evaluation
3. Parse JSON format results
4. Apply policy
5. Mattermost notification

### Failsafe
- Falls back to existing offline AI evaluator on Ollama failure
- Conservative judgment on API timeout
- Default risk=2 on JSON parsing failure

## Operations & Maintenance

### Log Management
```bash
# Application logs
docker logs azazel_threat_handler

# System logs
journalctl -u azazel-ollama.service -f

# Ollama internal logs
docker exec azazel_ollama ollama logs
```

### Policy Cleanup
```bash
# Remove tc rules
sudo tc qdisc del dev eth0 root

# Delete nftables table
sudo nft delete table inet azazel
```

### Model Update
```bash
# 1. Download new model via browser → /opt/models/qwen/
# 2. Update FROM path in Modelfile
# 3. Recreate model
docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile
```

### Recommended Model
- **mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF**
- Size: ~1.5GB (Q4_K_M quantization)
- Features: Uncensored version suitable for security analysis
- URL: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF

## Performance

### Expected Values on Pi 5
- **Memory Usage**: 2.5-3GB (Model 1.5GB + System)
- **Inference Time**: 2-5 seconds/alert
- **CPU Usage**: 50-80% (during inference)
- **Disk Usage**: 2GB (Model + System)

### Optimization Settings
```bash
# Ollama environment variables
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_KEEP_ALIVE=24h

# Docker resource limits
docker update --memory=3g --cpus=3 azazel_ollama
```

## Troubleshooting

### Common Issues
1. **Out of Memory** → Configure swap, limit parallel processing
2. **Model Load Failure** → Check permissions, disk space
3. **API Timeout** → Adjust timeout value, check CPU performance
4. **Policy Application Failure** → Check permissions, network settings

### Enable Detailed Logging
```bash
# Debug mode
export LOG_LEVEL=DEBUG
docker-compose restart threat-handler
```

---

## Implementation Complete ✅

All components are implemented and ready for one-line execution:

```bash
sudo /home/azazel/Azazel-Edge/scripts/install_ollama.sh
```
