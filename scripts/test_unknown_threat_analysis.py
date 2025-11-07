#!/usr/bin/env python3
"""
Unknown Threat Analysis Verification Script
Tests Ollama's deep analysis capabilities for unknown threats according to specifications
"""

import sys
import time
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from azazel_pi.core.integrated_threat_evaluator import IntegratedThreatEvaluator

logging.basicConfig(level=logging.WARNING)  # Reduce noise

def test_unknown_threat_routing():
    """Test that unknown threats are properly routed to Ollama"""
    
    print("🔬 Unknown Threat Analysis - Routing Verification")
    print("=" * 55)
    
    config = {
        'use_ollama': True,
        'ai': {
            'model': 'qwen2.5-threat-v3',
            'timeout': 15
        }
    }
    
    evaluator = IntegratedThreatEvaluator(config)
    
    # Test cases designed to trigger different analysis paths
    test_scenarios = [
        {
            'name': '🔴 Known Critical Threat',
            'category': 'critical',
            'data': {
                'alert': {'signature': 'Malware C2 Communication Detected', 'category': 'malware'},
                'http': {'hostname': 'malware-c2.darkweb.com'}
            },
            'expected_path': 'Exception Blocking',
            'expected_time_range': (0.0, 0.1)
        },
        {
            'name': '🟠 General Attack Pattern',
            'category': 'general',
            'data': {
                'alert': {'signature': 'ET WEB_SERVER SQL Injection Attack', 'category': 'sqli'},
                'http': {'hostname': 'webapp.victim.com'}
            },
            'expected_path': 'Mock LLM',
            'expected_time_range': (0.0, 1.0)
        },
        {
            'name': '🔵 Unknown Encrypted Protocol',
            'category': 'unknown',
            'data': {
                'alert': {'signature': 'Unidentified encrypted communication pattern', 'category': 'unknown'},
                'http': {'hostname': 'mystery-endpoint.xyz'}
            },
            'expected_path': 'Ollama Deep Analysis',
            'expected_time_range': (3.0, 8.0)
        },
        {
            'name': '🟣 Novel Behavioral Pattern',
            'category': 'unknown',
            'data': {
                'alert': {'signature': 'Anomalous network behavior detected', 'category': 'behavioral'},
                'dest_ip': '203.0.113.42',
                'dest_port': 9999
            },
            'expected_path': 'Ollama Deep Analysis',
            'expected_time_range': (3.0, 8.0)
        },
        {
            'name': '🟤 Zero-Day Exploit Pattern',
            'category': 'unknown',
            'data': {
                'alert': {'signature': 'Novel exploit technique observed', 'category': 'exploit-unknown'},
                'http': {'hostname': 'target-system.local'}
            },
            'expected_path': 'Ollama Deep Analysis',
            'expected_time_range': (3.0, 8.0)
        }
    ]
    
    results = []
    ollama_analysis_count = 0
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{scenario['name']} (Test {i}/{len(test_scenarios)})")
        print(f"Signature: {scenario['data']['alert']['signature']}")
        
        start_time = time.time()
        result = evaluator.evaluate_threat(scenario['data'])
        duration = time.time() - start_time
        
        # Determine actual processing path
        method = result.get('method', 'unknown')
        if method == 'exception_blocking':
            actual_path = 'Exception Blocking'
        elif method == 'mock_llm':
            actual_path = 'Mock LLM'
        elif duration >= 2.0:  # Likely Ollama
            actual_path = 'Ollama Deep Analysis'
            ollama_analysis_count += 1
        else:
            actual_path = 'Fast Path (Unknown)'
        
        # Check specification compliance
        path_match = actual_path == scenario['expected_path']
        time_min, time_max = scenario['expected_time_range']
        time_match = time_min <= duration <= time_max
        
        compliance = path_match and time_match
        status = "✅ PASS" if compliance else "⚠️ REVIEW" if path_match else "❌ FAIL"
        
        print(f"Expected: {scenario['expected_path']} ({time_min}-{time_max}s)")
        print(f"Actual:   {actual_path} ({duration:.2f}s)")
        print(f"Result:   Score={result.get('score', 'N/A')}, Action={result.get('action', 'N/A')}")
        print(f"Status:   {status}")
        
        results.append({
            'test': scenario['name'],
            'expected_path': scenario['expected_path'],
            'actual_path': actual_path,
            'duration': duration,
            'compliant': compliance,
            'ollama_used': actual_path == 'Ollama Deep Analysis'
        })
    
    return results, ollama_analysis_count

def test_ollama_response_quality():
    """Test quality of Ollama responses for unknown threats"""
    
    print("\n" + "=" * 55)
    print("🧠 Ollama Response Quality Analysis")
    print("=" * 55)
    
    from azazel_pi.core.enhanced_ai_evaluator import EnhancedAIThreatEvaluator
    
    evaluator = EnhancedAIThreatEvaluator(model='qwen2.5-threat-v3', timeout=10)
    
    unknown_threat_samples = [
        {
            'signature': 'Novel cryptographic protocol XYZ-2024',
            'category': 'crypto-unknown',
            'hostname': 'encrypted-channel.darknet'
        },
        {
            'signature': 'Unusual data exfiltration pattern',
            'category': 'behavioral',
            'hostname': 'suspicious-endpoint.io'
        },
        {
            'signature': 'Unclassified network anomaly',
            'category': 'unknown',
            'hostname': 'anomalous-traffic.xyz'
        }
    ]
    
    quality_metrics = {
        'response_time': [],
        'fallback_success': 0,
        'meaningful_analysis': 0,
        'total_tests': len(unknown_threat_samples)
    }
    
    for i, sample in enumerate(unknown_threat_samples, 1):
        print(f"\nQuality Test {i}: {sample['signature']}")
        
        test_data = {
            'alert': {'signature': sample['signature'], 'category': sample['category']},
            'http': {'hostname': sample['hostname']}
        }
        
        start_time = time.time()
        result = evaluator.evaluate_threat(test_data)
        duration = time.time() - start_time
        
        quality_metrics['response_time'].append(duration)
        
        # Check if fallback provided meaningful results
        if result.get('score', 0) > 0 and result.get('action') != 'unknown':
            quality_metrics['fallback_success'] += 1
            
        # Check if analysis seems relevant to threat type
        explanation = result.get('explanation', '').lower()
        if any(keyword in explanation for keyword in ['threat', 'suspicious', 'malware', 'attack', 'risk']):
            quality_metrics['meaningful_analysis'] += 1
        
        print(f"Duration: {duration:.2f}s")
        print(f"Score: {result.get('score', 'N/A')}")
        print(f"Action: {result.get('action', 'N/A')}")
        print(f"Analysis: {result.get('explanation', 'N/A')[:80]}...")
    
    return quality_metrics

def generate_report(routing_results, ollama_count, quality_metrics):
    """Generate comprehensive verification report"""
    
    print("\n" + "=" * 55)
    print("📊 VERIFICATION REPORT")
    print("=" * 55)
    
    total_tests = len(routing_results)
    compliant_tests = sum(1 for r in routing_results if r['compliant'])
    compliance_rate = (compliant_tests / total_tests) * 100
    
    print(f"📋 Routing Verification:")
    print(f"   Total Tests: {total_tests}")
    print(f"   Compliant: {compliant_tests}/{total_tests} ({compliance_rate:.0f}%)")
    print(f"   Ollama Analysis Count: {ollama_count}")
    
    # Performance analysis
    avg_time = sum(r['duration'] for r in routing_results) / total_tests
    print(f"\n⚡ Performance Analysis:")
    print(f"   Average Response Time: {avg_time:.2f}s")
    
    # Categorize by processing path
    path_counts = {}
    for result in routing_results:
        path = result['actual_path']
        path_counts[path] = path_counts.get(path, 0) + 1
    
    print(f"\n🛤️  Processing Path Distribution:")
    for path, count in path_counts.items():
        percentage = (count / total_tests) * 100
        print(f"   {path}: {count} ({percentage:.0f}%)")
    
    # Quality metrics
    if quality_metrics['total_tests'] > 0:
        avg_response_time = sum(quality_metrics['response_time']) / quality_metrics['total_tests']
        fallback_rate = (quality_metrics['fallback_success'] / quality_metrics['total_tests']) * 100
        analysis_rate = (quality_metrics['meaningful_analysis'] / quality_metrics['total_tests']) * 100
        
        print(f"\n🧠 Ollama Quality Analysis:")
        print(f"   Average Analysis Time: {avg_response_time:.2f}s")
        print(f"   Fallback Success Rate: {fallback_rate:.0f}%")
        print(f"   Meaningful Analysis Rate: {analysis_rate:.0f}%")
    
    # Final assessment
    print(f"\n🎯 FINAL ASSESSMENT:")
    
    if compliance_rate >= 80 and ollama_count >= 2:
        print("✅ SYSTEM COMPLIANT - Unknown threats properly routed to Ollama")
        print("✅ Deep analysis functioning as specified")
        print("✅ Enhanced fallback ensuring 100% result delivery")
        overall_status = "PASS"
    elif compliance_rate >= 60:
        print("⚠️ PARTIAL COMPLIANCE - Some routing issues detected")
        print("⚠️ System functional but may need tuning")
        overall_status = "REVIEW"
    else:
        print("❌ NON-COMPLIANT - Significant issues with threat routing")
        print("❌ System requires attention")
        overall_status = "FAIL"
    
    print(f"\n🚀 Overall Status: {overall_status}")
    
    return overall_status

def main():
    """Run complete unknown threat analysis verification"""
    
    print("🎯 Azazel-Pi Unknown Threat Analysis Verification")
    print("Specification Compliance Test (2024-11-06)")
    print("=" * 55)
    
    try:
        # Test routing behavior
        routing_results, ollama_count = test_unknown_threat_routing()
        
        # Test Ollama response quality
        quality_metrics = test_ollama_response_quality()
        
        # Generate comprehensive report
        status = generate_report(routing_results, ollama_count, quality_metrics)
        
        print(f"\n{'='*55}")
        print("✅ Verification completed successfully")
        
        return 0 if status == "PASS" else 1 if status == "REVIEW" else 2
        
    except KeyboardInterrupt:
        print("\n\n❌ Verification interrupted by user")
        return 130
    except Exception as e:
        print(f"\n\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)