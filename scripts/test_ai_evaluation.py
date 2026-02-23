#!/usr/bin/env python3
"""
AI-enhanced threat evaluation test script
Generates synthetic Suricata alerts for testing AI evaluation
"""

import json
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Test alert patterns
TEST_ALERTS = [
    {
        "event_type": "alert",
        "src_ip": "192.168.1.100",
        "dest_ip": "172.16.0.254",
        "proto": "TCP",
        "dest_port": 22,
        "alert": {
            "signature": "SSH brute-force attempt detected",
            "severity": 2
        },
        "payload_printable": "user: admin password: 123456",
        "expected_ai_risk": 3,
        "description": "SSH brute-force attack"
    },
    {
        "event_type": "alert", 
        "src_ip": "10.0.0.50",
        "dest_ip": "172.16.0.254",
        "proto": "TCP",
        "dest_port": 80,
        "alert": {
            "signature": "Nmap OS detection probe",
            "severity": 3
        },
        "payload_printable": "GET / HTTP/1.1\\r\\nHost: target\\r\\n",
        "expected_ai_risk": 2,
        "description": "Network reconnaissance"
    },
    {
        "event_type": "alert",
        "src_ip": "203.0.113.45",
        "dest_ip": "172.16.0.254", 
        "proto": "TCP",
        "dest_port": 5432,
        "alert": {
            "signature": "SQL injection attempt in HTTP request",
            "severity": 1
        },
        "payload_printable": "POST /login HTTP/1.1\\r\\nContent-Type: application/x-www-form-urlencoded\\r\\n\\r\\nusername=admin' OR '1'='1&password=test",
        "expected_ai_risk": 4,
        "description": "SQL injection attack"
    },
    {
        "event_type": "alert",
        "src_ip": "198.51.100.20",
        "dest_ip": "172.16.0.254",
        "proto": "TCP", 
        "dest_port": 443,
        "alert": {
            "signature": "Malware callback detected",
            "severity": 1
        },
        "payload_printable": "GET /c2/beacon.php?id=12345 HTTP/1.1\\r\\nUser-Agent: MalwareBot/1.0",
        "expected_ai_risk": 5,
        "description": "Malware C2 communication"
    },
    {
        "event_type": "alert",
        "src_ip": "192.168.1.200",
        "dest_ip": "172.16.0.254",
        "proto": "ICMP",
        "dest_port": 0,
        "alert": {
            "signature": "ICMP ping sweep detected",
            "severity": 4
        },
        "payload_printable": "",
        "expected_ai_risk": 1,
        "description": "Benign network discovery"
    }
]

def generate_alert(alert_template: dict) -> dict:
    """Generate a timestamped alert from template"""
    alert = alert_template.copy()
    alert["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    alert["flow_id"] = hash(f"{alert['src_ip']}{alert['dest_ip']}{time.time()}") % 100000
    
    # Remove test-specific fields
    for key in ["expected_ai_risk", "description"]:
        alert.pop(key, None)
    
    return alert

def inject_alert_to_eve(eve_path: Path, alert: dict):
    """Append alert to EVE JSON file"""
    try:
        with open(eve_path, "a") as f:
            f.write(json.dumps(alert) + "\n")
        print(f"✓ Injected alert: {alert['alert']['signature']}")
        return True
    except Exception as e:
        print(f"✗ Failed to inject alert: {e}")
        return False

def test_ai_evaluator_direct():
    """Test AI evaluator directly without file injection"""
    try:
        from azazel_edge.core.ai_evaluator import evaluate_alert_with_ai
        
        print("\n=== Direct AI Evaluator Testing ===")
        
        for i, template in enumerate(TEST_ALERTS, 1):
            print(f"\nTest {i}: {template['description']}")
            print(f"Expected risk: {template['expected_ai_risk']}")
            
            alert = generate_alert(template)
            
            # Debug: Show what signature we're passing
            print(f"Testing signature: '{alert['alert']['signature']}'")
            
            result = evaluate_alert_with_ai(alert)
            
            print(f"AI Result: risk={result['risk']}, category={result['category']}")
            print(f"Reason: {result['reason']}")
            print(f"AI Used: {result['ai_used']}")
            print(f"Model: {result.get('model', 'unknown')}")
            
            # Simple validation
            if abs(result['risk'] - template['expected_ai_risk']) <= 1:
                print("✓ Risk assessment within expected range")
            else:
                print("⚠ Risk assessment differs from expected")
            
            time.sleep(1)  # Rate limiting
            
    except ImportError as e:
        print(f"✗ Cannot import AI evaluator: {e}")
        print("Make sure you're running from Azazel-Edge root directory")
    except Exception as e:
        print(f"✗ Direct test failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Test AI-enhanced threat evaluation")
    parser.add_argument("--eve-file", "-e", 
                       default="/var/log/suricata/eve.json",
                       help="Path to Suricata EVE JSON file")
    parser.add_argument("--count", "-c", type=int, default=1,
                       help="Number of alert rounds to inject")
    parser.add_argument("--interval", "-i", type=float, default=2.0,
                       help="Interval between alerts (seconds)")
    parser.add_argument("--direct-test", "-d", action="store_true",
                       help="Run direct AI evaluator test")
    parser.add_argument("--dry-run", "-n", action="store_true",
                       help="Show alerts without injecting")
    
    args = parser.parse_args()
    
    if args.direct_test:
        test_ai_evaluator_direct()
        return
    
    eve_path = Path(args.eve_file)
    
    if not args.dry_run:
        if not eve_path.parent.exists():
            print(f"✗ Directory does not exist: {eve_path.parent}")
            return
        
        if not eve_path.exists():
            print(f"⚠ EVE file does not exist, will be created: {eve_path}")
    
    print(f"=== AI Threat Evaluation Test ===")
    print(f"EVE file: {eve_path}")
    print(f"Alert rounds: {args.count}")
    print(f"Interval: {args.interval}s")
    print(f"Dry run: {args.dry_run}")
    
    for round_num in range(args.count):
        if args.count > 1:
            print(f"\n--- Round {round_num + 1} ---")
        
        for alert_template in TEST_ALERTS:
            alert = generate_alert(alert_template)
            
            if args.dry_run:
                print(f"Would inject: {alert['alert']['signature'][:50]}...")
                print(f"  Risk level: {alert_template['expected_ai_risk']}/5")
                print(f"  Description: {alert_template['description']}")
            else:
                if inject_alert_to_eve(eve_path, alert):
                    time.sleep(args.interval)
        
        if args.count > 1 and round_num < args.count - 1:
            print(f"Waiting before next round...")
            time.sleep(5)
    
    print(f"\n✓ Test completed")
    print(f"Monitor Mattermost notifications and check:")
    print(f"  - /var/log/azazel/ai_decisions.log (if configured)")
    print(f"  - Docker logs: docker logs azazel_ollama")
    print(f"  - systemctl status azctl-unified.service")

if __name__ == "__main__":
    main()