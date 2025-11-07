#!/usr/bin/env python3
"""
Enhanced AI-powered threat evaluation with improved JSON parsing
Integrates with existing state_machine and scoring system with better Ollama handling
"""

import json
import re
import logging
import time
from typing import Dict, Any, Optional
import requests
from requests.exceptions import RequestException, Timeout

from .offline_ai_evaluator import evaluate_with_offline_ai

logger = logging.getLogger(__name__)

class EnhancedAIThreatEvaluator:
    """Enhanced LLM-based threat evaluator with improved JSON parsing"""
    
    def __init__(self, 
                 ollama_url: str = "http://127.0.0.1:11434/api/generate",
                 model: str = "qwen2.5-threat-v3",
                 timeout: int = 15,
                 max_payload_chars: int = 200):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout
        self.max_payload_chars = max_payload_chars
        self._model_available = False
        
        # JSON extraction patterns
        self.json_patterns = [
            r'\{[^{}]*"score"\s*:\s*\d+[^{}]*\}',  # Look for JSON with score field
            r'\{[^{}]*"risk"\s*:\s*\d+[^{}]*\}',   # Alternative risk field
            r'\{[^{}]*\}',                          # Any JSON object
        ]
        
        # Threat keywords for fallback scoring
        self.threat_keywords = {
            'critical': ['malware', 'c2', 'c&c', 'botnet', 'ransomware', 'trojan'],
            'high': ['exploit', 'attack', 'brute', 'injection', 'vulnerability'],
            'medium': ['suspicious', 'anomaly', 'reconnaissance', 'scan'],
            'low': ['warning', 'notice', 'info']
        }
    
    def _extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract and validate JSON from Ollama response"""
        if not response_text:
            return None
            
        # Try direct JSON parsing first
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try pattern-based extraction
        for pattern in self.json_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if self._validate_threat_json(parsed):
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _validate_threat_json(self, data: Dict[str, Any]) -> bool:
        """Validate if JSON contains required threat analysis fields"""
        required_fields = ['score', 'explanation', 'action']
        alt_fields = ['risk', 'reason', 'category']  # Alternative field names
        
        # Check primary fields
        has_primary = all(field in data for field in required_fields)
        
        # Check alternative fields
        has_alt = 'risk' in data or 'score' in data
        
        return has_primary or has_alt
    
    def _create_fallback_response(self, alert_data: Dict[str, Any], raw_response: str = "") -> Dict[str, Any]:
        """Create fallback response based on alert analysis"""
        # Extract key information
        signature = alert_data.get('alert', {}).get('signature', '')
        category = alert_data.get('alert', {}).get('category', '')
        dest_ip = alert_data.get('dest_ip', '')
        hostname = alert_data.get('http', {}).get('hostname', '')
        
        # Combine all text for analysis
        analysis_text = f"{signature} {category} {hostname}".lower()
        
        # Calculate threat score based on keywords
        score = 30  # Default medium
        explanation = "Unknown threat pattern"
        action = "monitor"
        
        # Check for critical threats
        for keyword in self.threat_keywords['critical']:
            if keyword in analysis_text:
                score = 85
                explanation = f"Critical threat: {keyword}"
                action = "block"
                break
        
        # Check for high threats
        if score < 70:
            for keyword in self.threat_keywords['high']:
                if keyword in analysis_text:
                    score = 70
                    explanation = f"High threat: {keyword}"
                    action = "block"
                    break
        
        # Check for medium threats
        if score < 50:
            for keyword in self.threat_keywords['medium']:
                if keyword in analysis_text:
                    score = 50
                    explanation = f"Medium threat: {keyword}"
                    action = "delay"
                    break
        
        # Special handling for known bad domains
        if any(bad_domain in hostname for bad_domain in ['malware-c2', 'botnet', 'phishing']):
            score = 95
            explanation = "Known C&C domain"
            action = "block"
        
        return {
            "score": score,
            "explanation": explanation,
            "action": action,
            "ai_used": "enhanced_fallback",
            "raw_response": raw_response[:100] if raw_response else ""
        }
    
    def _normalize_response(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize JSON response to standard format"""
        normalized = {}
        
        # Handle score/risk field
        if 'score' in json_data:
            normalized['score'] = min(100, max(0, int(json_data['score'])))
        elif 'risk' in json_data:
            risk_val = json_data['risk']
            # Convert risk scale (1-5) to score scale (0-100)
            if isinstance(risk_val, int) and 1 <= risk_val <= 5:
                normalized['score'] = risk_val * 20  # 1->20, 5->100
            else:
                normalized['score'] = min(100, max(0, int(risk_val)))
        else:
            normalized['score'] = 50  # Default
        
        # Handle explanation/reason field
        explanation = json_data.get('explanation', json_data.get('reason', 'AI analysis'))
        normalized['explanation'] = str(explanation)[:100]  # Limit length
        
        # Handle action field
        action = json_data.get('action', 'monitor')
        valid_actions = ['allow', 'monitor', 'delay', 'block']
        if action not in valid_actions:
            # Map based on score
            if normalized['score'] >= 80:
                action = 'block'
            elif normalized['score'] >= 60:
                action = 'delay'
            elif normalized['score'] >= 30:
                action = 'monitor'
            else:
                action = 'allow'
        normalized['action'] = action
        
        normalized['ai_used'] = 'ollama_enhanced'
        return normalized
    
    def evaluate_threat(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced threat evaluation with better JSON handling"""
        try:
            # Prepare minimal prompt
            signature = alert_data.get('alert', {}).get('signature', '')
            category = alert_data.get('alert', {}).get('category', '')
            hostname = alert_data.get('http', {}).get('hostname', '')
            
            # Create concise prompt
            prompt = f"Analyze: {signature[:50]} Host: {hostname} Category: {category}"
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.01,
                    "num_predict": 30,
                    "top_k": 5,
                    "top_p": 0.5
                }
            }
            
            logger.info(f"Sending enhanced request to Ollama: {prompt[:50]}...")
            
            response = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                raw_response = data.get('response', '')
                
                logger.info(f"Ollama raw response: {raw_response[:100]}...")
                
                # Try to extract JSON
                json_data = self._extract_json_from_response(raw_response)
                
                if json_data and self._validate_threat_json(json_data):
                    logger.info("Successfully extracted JSON from Ollama response")
                    return self._normalize_response(json_data)
                else:
                    logger.warning("Failed to extract valid JSON, using enhanced fallback")
                    return self._create_fallback_response(alert_data, raw_response)
            else:
                logger.error(f"Ollama HTTP error: {response.status_code}")
                return self._create_fallback_response(alert_data)
                
        except Timeout:
            logger.warning("Ollama request timeout, using fallback")
            return self._create_fallback_response(alert_data)
        except Exception as e:
            logger.error(f"Ollama evaluation error: {e}")
            return self._create_fallback_response(alert_data)

# Backward compatibility - alias to existing class name
AIThreatEvaluator = EnhancedAIThreatEvaluator