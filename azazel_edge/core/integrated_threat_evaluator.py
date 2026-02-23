#!/usr/bin/env python3
"""
Integrated Enhanced Threat Evaluator
Combines the best of all systems: Exception Blocking + Mock LLM + Enhanced Ollama
"""

import logging
from typing import Dict, Any, Optional
from azazel_edge.core.offline_ai_evaluator import evaluate_with_offline_ai
from azazel_edge.core.enhanced_ai_evaluator import EnhancedAIThreatEvaluator

logger = logging.getLogger(__name__)

class IntegratedThreatEvaluator:
    """統合脅威評価システム - 全手法の組み合わせ"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Enhanced Ollama evaluator initialization
        self.ollama_evaluator = None
        self.use_ollama = self.config.get("use_ollama", True)
        
        if self.use_ollama:
            try:
                ai_config = self.config.get("ai", {})
                self.ollama_evaluator = EnhancedAIThreatEvaluator(
                    ollama_url=ai_config.get("ollama_url", "http://127.0.0.1:11434/api/generate"),
                    model=ai_config.get("model", "qwen2.5-threat-v3"),
                    timeout=ai_config.get("timeout", 15)
                )
                logger.info("Enhanced Ollama evaluator initialized")
            except Exception as e:
                logger.warning(f"Enhanced Ollama evaluator init failed: {e}")
                self.ollama_evaluator = None
    
    def evaluate_threat(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """統合脅威評価 - 3段階アプローチ"""
        
        # Stage 1: Exception Blocking (immediate)
        exception_result = self._check_exception_blocking(alert_data)
        if exception_result:
            return exception_result
        
        # Stage 2: Mock LLM (fast, reliable)
        mock_result = self._evaluate_with_mock_llm(alert_data)
        if mock_result and mock_result.get("confidence", 0) > 0.7:
            return mock_result
        
        # Stage 3: Enhanced Ollama (for uncertain cases)
        if self.ollama_evaluator:
            try:
                ollama_result = self.ollama_evaluator.evaluate_threat(alert_data)
                if ollama_result and "score" in ollama_result:
                    return ollama_result
            except Exception as e:
                logger.warning(f"Enhanced Ollama evaluation failed: {e}")
        
        # Fallback: Basic rule-based
        return self._basic_fallback(alert_data)
    
    def _check_exception_blocking(self, alert_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """例外ブロック判定 - 即座にブロックすべき脅威"""
        signature = alert_data.get('alert', {}).get('signature', '').lower()
        category = alert_data.get('alert', {}).get('category', '').lower()
        hostname = alert_data.get('http', {}).get('hostname', '').lower()
        
        # Critical threats - immediate block
        critical_patterns = [
            'malware', 'c2', 'c&c', 'botnet', 'ransomware', 'trojan',
            'backdoor', 'exploit', 'shellcode', 'metasploit'
        ]
        
        for pattern in critical_patterns:
            if pattern in signature or pattern in hostname:
                return {
                    "score": 95,
                    "explanation": f"Critical threat detected: {pattern}",
                    "action": "block",
                    "confidence": 1.0,
                    "method": "exception_blocking"
                }
        
        # Known C&C domains
        if any(bad_domain in hostname for bad_domain in [
            'malware-c2', 'botnet', 'phishing', 'darkweb'
        ]):
            return {
                "score": 98,
                "explanation": "Known malicious domain",
                "action": "block",
                "confidence": 1.0,
                "method": "exception_blocking"
            }
        
        return None
    
    def _evaluate_with_mock_llm(self, alert_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mock LLM評価 - 高速で信頼性の高い判定"""
        try:
            result = evaluate_with_offline_ai(alert_data)
            if result:
                # Convert to standard format
                return {
                    "score": result.get("score", 50),
                    "explanation": result.get("explanation", "Mock LLM analysis"),
                    "action": result.get("action", "monitor"),
                    "confidence": result.get("confidence", 0.8),
                    "method": "mock_llm"
                }
        except Exception as e:
            logger.warning(f"Mock LLM evaluation failed: {e}")
        
        return None
    
    def _basic_fallback(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """基本的なルールベース判定"""
        signature = alert_data.get('alert', {}).get('signature', '').lower()
        category = alert_data.get('alert', {}).get('category', '').lower()
        
        # Category-based scoring
        category_scores = {
            'exploit': 85,
            'malware': 80,
            'sqli': 75,
            'dos': 60,
            'bruteforce': 50,
            'scan': 40,
            'unknown': 30
        }
        
        score = category_scores.get(category, 35)
        
        # Keyword adjustments
        if any(keyword in signature for keyword in ['critical', 'high', 'severe']):
            score += 20
        elif any(keyword in signature for keyword in ['medium', 'warning']):
            score += 10
        
        action = "block" if score >= 70 else "delay" if score >= 50 else "monitor"
        
        return {
            "score": min(100, score),
            "explanation": f"Rule-based analysis: {category}",
            "action": action,
            "confidence": 0.6,
            "method": "rule_based"
        }

# Backward compatibility
HybridThreatEvaluator = IntegratedThreatEvaluator