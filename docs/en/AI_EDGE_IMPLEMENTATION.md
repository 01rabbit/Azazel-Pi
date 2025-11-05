# Azazel-Pi AI Edge Computing Implementation (Current)

## Overview

This implementation is a hybrid threat evaluation system that integrates "Offline AI + Rule-based + Ollama (for unknown threats)". It analyzes Suricata alerts and applies composite tc/nftables controls (DNAT/delay/bandwidth limit) based on AI-enhanced scores.

### 3-Tier Evaluation Architecture

```
1. Legacy Rules (Base evaluation)         - Fast (<10ms)
   ↓
2. Mock LLM (Known threats)               - Fast (<50ms) - Main evaluation engine
   ├→ Confidence ≥ 0.7: Confirmed
   └→ Confidence < 0.7: Unknown threat?
       ↓
3. Ollama (Deep analysis of unknown)      - Detailed (2-5s) - Optional supplement
```

**Processing Distribution**:
- Mock LLM only: ~80-90% (fast processing)
- Ollama supplement: ~10-20% (deep analysis)

## Implementation Components

### 1) Hybrid Threat Evaluator (`azazel_pi/core/hybrid_threat_evaluator.py`)
- Integrates Legacy rule evaluation and Offline AI (including Mock LLM)
- **Ollama Integration**: Executes deep analysis when unknown threats are detected
  - Trigger conditions: Confidence < 0.7, unknown category, low risk but uncertain
- Integration weights: 
  - Known threats: Legacy 60% + Mock LLM 40%
  - Unknown threats: Ollama 70% + Mock LLM 30%
- Minimum score guarantee by category (e.g., exploit/malware/sqli minimum 60 points)
- Benign traffic override judgment
- Returns detailed components (legacy_score/mock_llm_score/weights)

### 2) AI Evaluator (`azazel_pi/core/ai_evaluator.py`)
- **Ollama LLM Evaluator**: Deep analysis for unknown threats
- API endpoint: `http://127.0.0.1:11434/api/generate`
- Model: threatjudge (Qwen2.5-1.5B-Instruct-uncensored)
- Timeout: 30 seconds (configurable)
- Fallback functionality: Automatically falls back to Mock LLM when Ollama is unavailable

### 3) Offline AI Evaluator (`azazel_pi/core/offline_ai_evaluator.py`)
- Features: Signature/payload complexity/target service criticality/reputation/temporal frequency/protocol anomaly
- Reputation: Strict classification of RFC1918・loopback・link-local・invalid addresses using `ipaddress`
- No model dependency. Pseudo-deterministic even when using Mock LLM (random seed from prompt hash)
- Outputs risk as 1-5, converted to 0-100 on integration side

### 4) Suricata Monitor (`azazel_pi/monitor/main_suricata.py`)
- Category normalization in `parse_alert` (absorbs uppercase/lowercase/underscore differences)
- Reads allow/deny categories from `soc.allowed_categories` / `soc.denied_categories` in `configs/network/azazel.yaml` (uses default list when unset)
- Independent frequency counter (signature×src_ip time series) for stable concentrated attack detection
- Risk-based control activation: Applies composite control when threat_score >= t1 (threshold)
- Separates notification cooldown and control activation (control still executed even when notification is suppressed)
- Moving average reflection and mode transition via `state_machine.apply_score()`
- Cleanup call for expired rules every 10 minutes

### 5) State Machine (`azazel_pi/core/state_machine.py`)
- 3 modes: portal/shield/lockdown + temporary user mode
- Reads thresholds and unlock delays from YAML. Added `configs/network/azazel.yaml` as fallback in path search
- Transition judgment using moving average window, supports user mode timeout

### 6) Integrated Traffic Control (`azazel_pi/core/enforcer/traffic_control.py`)
- Composite control: DNAT→OpenCanary + suspect QoS + netem delay + HTB shaping
- Idempotency: Suppresses re-application of same rule type to same IP, uses retained `prio` for accurate filter removal on deletion
- Expired cleanup API and statistics retrieval API

### 7) Wrapper Compatibility (`azazel_pi/utils/delay_action.py`)
- Bridge from old API to integrated engine. Legacy fallback is deprecated

## Configuration

### AI Configuration (`configs/ai_config.json`)

```json
{
  "ai": {
    "ollama_url": "http://127.0.0.1:11434/api/generate",
    "model": "threatjudge",
    "timeout": 30,
    "max_payload_chars": 400,
    "unknown_threat_detection": {
      "enabled": true,
      "confidence_threshold": 0.7,
      "trigger_categories": ["unknown", "benign"],
      "trigger_low_risk": true
    }
  },
  "hybrid": {
    "legacy_weight": 0.6,
    "mock_llm_weight": 0.4,
    "ollama_weight": 0.7,
    "unknown_detection_enabled": true
  }
}
```

### Network Configuration (`configs/network/azazel.yaml`)

Main keys:

```
actions:
   portal:   { delay_ms: 100, shape_kbps: null, block: false }
   shield:   { delay_ms: 200, shape_kbps: 128,  block: false }
   lockdown: { delay_ms: 300, shape_kbps: 64,   block: true  }
thresholds:
   t1_shield: 50
   t2_lockdown: 80
   unlock_wait_secs: { shield: 600, portal: 1800 }
soc:
   allowed_categories: ["Malware", "Exploit", "SCAN", "Web Specific Apps"]  # Optional
   denied_categories:  ["DNS", "POP3"]                                       # Optional
```

When allow/deny is unset, passes default major categories (prevents missed detections). deny takes priority over allow.

## Operation Flow (Current)

```
Suricata Alert → Hybrid Evaluator → Score(0-100) → State Transition → Composite Control(tc/nft) → Mattermost Notification
       ↓                 ↓                    ↓            ↓                    ↓
   eve.json      Legacy+Mock LLM        moving average   DNAT/delay/bandwidth     webhook
                      ↓
                 (confidence < 0.7)
                      ↓
                 Ollama Deep Analysis
```

### Detailed Evaluation Flow

1. **Fast Evaluation** (majority of alerts)
   - Legacy Rules + Mock LLM
   - Processing time: <50ms
   - Immediately confirmed when confidence is high

2. **Deep Evaluation** (unknown threats)
   - Detailed analysis by Ollama
   - Processing time: 2-5 seconds
   - Low confidence, unknown category, uncertain low-risk alerts

## Docker Compose Integration

Ollama is integrated with existing Mattermost/PostgreSQL environment.

### Service Configuration (`deploy/docker-compose.yml`)

```yaml
services:
  postgres:      # Mattermost database
  ollama:        # AI threat analysis engine
```

### Management Commands

```bash
cd /home/azazel/Azazel-Pi/deploy

# Start all services
docker compose up -d

# Start Ollama only
docker compose up -d ollama

# Check status
docker compose ps

# Check logs
docker logs -f azazel_ollama
```

## Installation/Setup

### 1. Ollama Setup

```bash
# Run automatic setup script
sudo /home/azazel/Azazel-Pi/scripts/setup_ollama.sh
```

Download model file in advance:
- URL: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF
- File: Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
- Location: /opt/models/qwen/

### 2. Test Execution
```bash
python3 -m venv .venv
source .venv/bin/activate
pytest -q
```

### 3. Integration Test
```bash
python3 - << 'PY'
from azazel_pi.monitor.main_suricata import calculate_threat_score

# Known threat test (Mock LLM)
print("=== Known Threat: SQLi ===")
alert1 = {
   'signature': 'ET WEB_SPECIFIC_APPS SQL Injection Attack',
   'src_ip': '203.0.113.44','dest_ip': '192.168.1.10','dest_port': 80,
   'proto': 'TCP','severity': 1,
   'payload_printable': "GET /admin.php?id=1' UNION SELECT user,pass FROM admin--",
   'details': {'metadata': {'attack_target': 'web_application'}}
}
score, detail = calculate_threat_score(alert1, alert1['signature'], use_ai=True)
print(f"  Score: {score}, Category: {detail.get('category')}, Method: {detail.get('evaluation_method')}")

# Unknown threat test (Ollama)
print("\n=== Unknown Threat: Unknown Activity ===")
alert2 = {
   'signature': 'ET INFO Unknown suspicious activity',
   'src_ip': '192.168.1.100','dest_ip': '10.0.0.1','dest_port': 8888,
   'proto': 'TCP','severity': 3,'payload_printable': 'strange binary data'
}
score, detail = calculate_threat_score(alert2, alert2['signature'], use_ai=True)
print(f"  Score: {score}, Category: {detail.get('category')}, Method: {detail.get('evaluation_method')}")
# Verify that evaluation_method is "ollama_unknown_threat"
PY
```

Expected output:
```
=== Known Threat: SQLi ===
  Score: 60-80, Category: sqli, Method: hybrid_integration

=== Unknown Threat: Unknown Activity ===
  Score: 20-40, Category: unknown, Method: ollama_unknown_threat
```

## Monitoring & Operations

- Services (examples)
   - `systemd/azctl-unified.service` (integrated control)
   - `systemd/suricata.service` (Suricata)
- Logs
   - `/var/log/azazel/` (depends on configuration)
   - `journalctl -f -u azctl-unified.service` etc.

## Troubleshooting (Current)

### 1) Alerts not being ingested
- Check `parse_alert` category normalization and allow/deny settings
- Verify `configs/network/azazel.yaml` path is readable (has fallback)

### 2) Controls being applied repeatedly
- Engine is idempotent. Check application status with `get_active_rules()`

### 3) Score appears too high/low
- Adjust relationship between `thresholds.t1_shield`/`t2_lockdown` and category minimum guarantee
- Adjust `soc.allowed_categories/denied_categories` according to monitoring environment

### 4) Ollama not responding
```bash
# Check service status
docker logs azazel_ollama

# Restart
cd /home/azazel/Azazel-Pi/deploy
docker compose restart ollama

# Health check
docker exec azazel_ollama ollama ps
curl http://127.0.0.1:11434/api/tags
```

### 5) Frequent timeout errors
Adjust timeout in `configs/ai_config.json`:
```json
{
  "ai": {
    "timeout": 60
  }
}
```

## Performance Characteristics

| Evaluation Method | Processing Time | Memory Usage | Usage Rate | Purpose |
|-------------------|----------------|--------------|------------|---------|
| Legacy Rules | <10ms | <1MB | Fallback | Base evaluation |
| Mock LLM | <50ms | <10MB | 80-90% | Known threats (main) |
| Ollama | 2-5s | 2-3GB | 10-20% | Unknown threats (supplement) |

### Resource Requirements

- **Minimum Memory**: 2GB (Mock LLM only)
- **Recommended Memory**: 4GB+ (when using Ollama)
- **Disk**: ~2GB (including Ollama model)
- **CPU**: 4 cores recommended (verified on Raspberry Pi 5)

## Changes from Previous Documentation (Summary)

- **Ollama Integration**: Managed by Docker Compose, used for deep analysis of unknown threats
- **3-tier Evaluation**: Cascade evaluation of Legacy → Mock LLM → Ollama
- Utilizes `ai_evaluator.py`: Functions as Ollama LLM evaluator
- Updated `hybrid_threat_evaluator.py`: Added unknown threat detection logic
- Docker Integration: Integrated management with PostgreSQL/Mattermost
- main_suricata supports risk-based control activation, independent frequency counter, category normalization, periodic cleanup
- Traffic control enhanced with idempotency and cleanup

## Future Enhancements

1. Enhanced observability (metrics output/visualization)
2. Additional features (flow duration/directionality/size distribution)
3. Bayesian integration and fuzzy logic application beyond signatures
4. Selective use of larger LLM models (limited to critical alerts)
5. Automatic threat pattern updates through online learning

## Related Documentation

- **Ollama Setup Details**: [OLLAMA_SETUP.md](OLLAMA_SETUP.md)
- **Mock LLM Design Philosophy**: [MOCK_LLM_DESIGN.md](MOCK_LLM_DESIGN.md)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Operations Guide**: [OPERATIONS.md](OPERATIONS.md)

---

This document has been updated based on the current branch (edge-ai-verification) implementation.
Last updated: 2025-11-05 - Added Ollama integration, Docker Compose management, unknown threat detection functionality
