#!/usr/bin/env python3
"""
Enhanced AI Integration Test
Tests the improved Ollama JSON handling and integrated threat evaluation
"""

import sys
import json
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from azazel_pi.core.enhanced_ai_evaluator import EnhancedAIThreatEvaluator
from azazel_pi.core.integrated_threat_evaluator import IntegratedThreatEvaluator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_enhanced_ollama():
    """Test enhanced Ollama evaluator with JSON handling"""
    print("\n=== Enhanced Ollama Evaluator Test ===")
    
    evaluator = EnhancedAIThreatEvaluator(
        model="qwen2.5-threat-v3",
        timeout=15
    )
    
    test_cases = [
        {
            "name": "C&C Communication",
            "alert": {
                "signature": "HTTP POST to malware-c2.example.com",
                "category": "malware"
            },
            "http": {"hostname": "malware-c2.example.com"}
        },
        {
            "name": "SQL Injection",
            "alert": {
                "signature": "ET WEB_SERVER SQL Injection Attack",
                "category": "sqli"
            },
            "http": {"hostname": "webapp.example.com"}
        },
        {
            "name": "Port Scan",
            "alert": {
                "signature": "ET SCAN Potential SSH Brute Force",
                "category": "scan"
            },
            "dest_ip": "192.168.1.100"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"Input: {test_case['alert']['signature'][:50]}...")
        
        start_time = time.time()
        result = evaluator.evaluate_threat(test_case)
        duration = time.time() - start_time
        
        print(f"Duration: {duration:.2f}s")
        print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        # Validate JSON format
        required_fields = ['score', 'explanation', 'action']
        missing_fields = [field for field in required_fields if field not in result]
        
        if missing_fields:
            print(f"❌ Missing fields: {missing_fields}")
        else:
            print("✅ Valid JSON format")
        
        time.sleep(1)  # Avoid overloading

def test_integrated_evaluator():
    """Test integrated threat evaluator with all methods"""
    print("\n=== Integrated Threat Evaluator Test ===")
    
    config = {
        "use_ollama": True,
        "ai": {
            "model": "qwen2.5-threat-v3",
            "timeout": 15
        }
    }
    
    evaluator = IntegratedThreatEvaluator(config)
    
    test_cases = [
        {
            "name": "Known Malware (Exception Blocking)",
            "alert": {
                "signature": "Malware C2 Communication Detected",
                "category": "malware"
            },
            "http": {"hostname": "malware-c2.darkweb.com"}
        },
        {
            "name": "Normal SQL Query (Mock LLM)",
            "alert": {
                "signature": "Database SELECT Query",
                "category": "database"
            },
            "http": {"hostname": "webapp.company.com"}
        },
        {
            "name": "Unknown Pattern (Ollama)",
            "alert": {
                "signature": "Unusual Network Pattern Detected",
                "category": "unknown"
            },
            "http": {"hostname": "suspicious.example.org"}
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"Input: {test_case['alert']['signature']}")
        
        start_time = time.time()
        result = evaluator.evaluate_threat(test_case)
        duration = time.time() - start_time
        
        print(f"Duration: {duration:.3f}s")
        print(f"Method: {result.get('method', 'unknown')}")
        print(f"Score: {result.get('score', 0)}")
        print(f"Action: {result.get('action', 'unknown')}")
        print(f"Explanation: {result.get('explanation', 'N/A')}")
        
        # Performance check
        if duration < 0.1:
            print("⚡ Ultra-fast response")
        elif duration < 1.0:
            print("🟢 Fast response")
        elif duration < 5.0:
            print("🟡 Moderate response")
        else:
            print("🟠 Slow response")
        
        time.sleep(0.5)

def test_json_extraction():
    """Test JSON extraction capabilities"""
    print("\n=== JSON Extraction Test ===")
    
    evaluator = EnhancedAIThreatEvaluator()
    
    test_responses = [
        '{"score": 85, "explanation": "High risk", "action": "block"}',
        'Here is my analysis: {"score": 70, "explanation": "Medium risk", "action": "delay"} Hope this helps.',
        'Based on the data, I would say {"risk": 4, "reason": "Suspicious pattern", "category": "malware"}',
        'This looks like a malware communication pattern with C&C characteristics.',
        '{"score":90,"explanation":"Malware detected","action":"block"}',
        ''
    ]
    
    for i, response in enumerate(test_responses, 1):
        print(f"\nTest {i}: {repr(response[:50])}...")
        
        result = evaluator._extract_json_from_response(response)
        
        if result:
            print(f"✅ Extracted: {result}")
            if evaluator._validate_threat_json(result):
                print("✅ Valid threat JSON")
            else:
                print("❌ Invalid threat JSON")
        else:
            print("❌ No JSON extracted")

def main():
    """Run all tests"""
    print("Enhanced AI Integration Testing")
    print("=" * 50)
    
    try:
        # Test JSON extraction first
        test_json_extraction()
        
        # Test enhanced Ollama evaluator
        test_enhanced_ollama()
        
        # Test integrated evaluator
        test_integrated_evaluator()
        
        print("\n" + "=" * 50)
        print("✅ All tests completed")
        
    except KeyboardInterrupt:
        print("\n\n❌ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()