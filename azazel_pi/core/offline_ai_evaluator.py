#!/usr/bin/env python3
"""
Lightweight Local AI Evaluator - Offline Alternative
Rule-based threat assessment with ML-inspired scoring for network isolation scenarios
"""

import re
import json
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import ipaddress

logger = logging.getLogger(__name__)

class OfflineAIEvaluator:
    """Rule-based threat evaluator with ML-inspired ensemble scoring"""
    
    def __init__(self, use_mock_llm: bool = True):
        self.logger = logging.getLogger(__name__)
        self.history = defaultdict(list)  # Track per-IP behavior
        self.threat_signatures = self._load_attack_patterns()
        self.scoring_weights = self._load_scoring_weights()
        self.use_mock_llm = use_mock_llm
        self.reputation_cache = {}  # IP reputation cache
        self.context_history = defaultdict(list)  # Context history for temporal analysis
        
        # Initialize mock LLM if requested
        if self.use_mock_llm:
            try:
                from .mock_llm import get_mock_llm
                self.mock_llm = get_mock_llm()
                self.logger.info("Mock LLM evaluator loaded successfully")
            except ImportError as e:
                self.logger.warning(f"Could not load mock LLM: {e}")
                self.mock_llm = None
                self.use_mock_llm = False
        
    def _load_attack_patterns(self) -> Dict[str, Dict]:
        """Load attack pattern definitions with ML-inspired confidence scoring"""
        return {
            # High-risk exploitation patterns
            "exploit": {
                "patterns": [
                    r"buffer\s*overflow", r"stack\s*overflow", r"heap\s*spray",
                    r"shellcode", r"rop\s*chain", r"return\s*oriented",
                    r"use\s*after\s*free", r"double\s*free", r"format\s*string"
                ],
                "base_risk": 5,
                "confidence": 0.95,
                "category": "exploit"
            },
            
            # SQL injection patterns
            "sqli": {
                "patterns": [
                    r"('\s*or\s*'1'\s*=\s*'1|'\s*or\s*1\s*=\s*1)",
                    r"union\s*select", r"drop\s*table", r"delete\s*from",
                    r"insert\s*into", r"update\s*.*set", r"exec\s*\(",
                    r"sp_executesql", r"xp_cmdshell"
                ],
                "base_risk": 4,
                "confidence": 0.90,
                "category": "sqli"
            },
            
            # Malware C2 patterns
            "malware": {
                "patterns": [
                    r"beacon|c2|command.*control|bot.*net",
                    r"trojan|backdoor|rootkit|keylogger",
                    r"ransomware|cryptolocker|wannacry",
                    r"payload.*download|stage.*2|dropper"
                ],
                "base_risk": 5,
                "confidence": 0.85,
                "category": "malware"
            },
            
            # Brute force patterns
            "bruteforce": {
                "patterns": [
                    r"brute.*force|dictionary.*attack|password.*spray",
                    r"login.*attempt|auth.*failed|invalid.*credential",
                    r"admin.*admin|root.*root|123456|password"
                ],
                "base_risk": 3,
                "confidence": 0.80,
                "category": "bruteforce"
            },
            
            # Reconnaissance patterns
            "recon": {
                "patterns": [
                    r"nmap|masscan|zmap|port.*scan",
                    r"banner.*grab|service.*enum|version.*detect",
                    r"directory.*enum|web.*crawl|spider",
                    r"dns.*enum|subdomain.*enum"
                ],
                "base_risk": 2,
                "confidence": 0.75,
                "category": "scan"
            },
            
            # DoS patterns
            "dos": {
                "patterns": [
                    r"dos|ddos|flood|amplification",
                    r"syn.*flood|udp.*flood|icmp.*flood",
                    r"slowloris|http.*flood|bandwidth.*exhaust"
                ],
                "base_risk": 4,
                "confidence": 0.85,
                "category": "dos"
            }
        }
    
    def _load_scoring_weights(self) -> Dict[str, float]:
        """Load ML-inspired feature weights"""
        return {
            "signature_match": 0.4,      # 40% - Pattern matching confidence
            "payload_complexity": 0.15,   # 15% - Payload analysis
            "target_criticality": 0.15,  # 15% - Target port/service importance
            "source_reputation": 0.10,   # 10% - Historical behavior
            "temporal_context": 0.10,    # 10% - Time-based patterns
            "protocol_anomaly": 0.10     # 10% - Protocol-specific anomalies
        }
    
    def evaluate_threat(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced threat evaluation with ML-inspired scoring"""
        
        # Handle both direct signature and nested alert structure
        signature = ""
        if "signature" in alert_data:
            signature = alert_data["signature"].lower()
        elif "alert" in alert_data and "signature" in alert_data["alert"]:
            signature = alert_data["alert"]["signature"].lower()
        
        src_ip = alert_data.get("src_ip", "")
        payload = alert_data.get("payload_printable", "").lower()
        dest_port = alert_data.get("dest_port", 0)
        proto = alert_data.get("proto", "").lower()
        
        logger.debug(f"Evaluating signature: '{signature}'")
        
        # Feature extraction and scoring
        features = {
            "signature_score": self._analyze_signature(signature),
            "payload_score": self._analyze_payload(payload),
            "target_score": self._analyze_target(dest_port, proto),
            "reputation_score": self._analyze_source_reputation(src_ip),
            "temporal_score": self._analyze_temporal_context(src_ip, signature),
            "protocol_score": self._analyze_protocol_anomaly(proto, dest_port, payload)
        }
        
        # Weighted ensemble scoring
        final_risk = self._calculate_ensemble_score(features)
        primary_category = features["signature_score"]["category"]
        confidence = features["signature_score"]["confidence"]
        
        # Generate explanation
        explanation = self._generate_explanation(features, final_risk)
        
        # Enhanced with Mock LLM evaluation if enabled
        if self.use_mock_llm and self.mock_llm:
            try:
                llm_prompt = self._create_llm_prompt(alert_data, features)
                llm_response = json.loads(self.mock_llm.generate_response(llm_prompt))
                
                # Combine ensemble score with LLM assessment
                combined_risk = int((final_risk + llm_response.get("risk", final_risk)) / 2)
                combined_reason = f"{explanation} LLM分析: {llm_response.get('reason', '')}"
                
                # Use more reliable category (ensemble vs LLM)
                final_category = primary_category if primary_category != "unknown" else llm_response.get("category", primary_category)
                
                return {
                    "risk": combined_risk,
                    "reason": combined_reason,
                    "category": final_category,
                    "ai_used": True,
                    "model": "offline_ensemble_v1.0+mock_llm",
                    "confidence": min(confidence, 0.95),  # Slightly lower for mock
                    "features": features,
                    "llm_evaluation": llm_response
                }
            except Exception as e:
                self.logger.warning(f"Mock LLM evaluation failed: {e}")
        
        return {
            "risk": final_risk,
            "reason": explanation,
            "category": primary_category,
            "ai_used": True,  # This is our "AI" - rule-based ML
            "model": "offline_ensemble_v1.0",
            "confidence": confidence,
            "features": features
        }
    
    def _analyze_signature(self, signature: str) -> Dict[str, Any]:
        """Analyze signature patterns with confidence scoring"""
        best_match = {"category": "unknown", "risk": 1, "confidence": 0.5}
        
        logger.debug(f"Analyzing signature: {signature}")
        
        for pattern_type, config in self.threat_signatures.items():
            for pattern in config["patterns"]:
                if re.search(pattern, signature, re.IGNORECASE):
                    logger.debug(f"Pattern match: {pattern} -> {config['category']}")
                    if config["base_risk"] > best_match["risk"]:
                        best_match = {
                            "category": config["category"],
                            "risk": config["base_risk"],
                            "confidence": config["confidence"]
                        }
                    break
        
        # If no pattern matched, try simple keyword matching
        if best_match["category"] == "unknown":
            signature_lower = signature.lower()
            if any(word in signature_lower for word in ["brute", "force", "login", "auth", "password"]):
                best_match = {"category": "bruteforce", "risk": 3, "confidence": 0.7}
            elif any(word in signature_lower for word in ["scan", "nmap", "probe", "recon"]):
                best_match = {"category": "scan", "risk": 2, "confidence": 0.7}
            elif any(word in signature_lower for word in ["injection", "sql", "xss", "script"]):
                best_match = {"category": "sqli", "risk": 4, "confidence": 0.8}
            elif any(word in signature_lower for word in ["malware", "trojan", "virus", "bot"]):
                best_match = {"category": "malware", "risk": 5, "confidence": 0.8}
            elif any(word in signature_lower for word in ["dos", "flood", "amplification"]):
                best_match = {"category": "dos", "risk": 4, "confidence": 0.8}
        
        return best_match
    
    def _analyze_payload(self, payload: str) -> Dict[str, Any]:
        """Analyze payload complexity and suspicious content"""
        if not payload:
            return {"score": 0, "complexity": "none"}
        
        # Complexity indicators
        complexity_score = 0
        
        # Length-based complexity
        if len(payload) > 1000:
            complexity_score += 0.3
        elif len(payload) > 500:
            complexity_score += 0.2
        elif len(payload) > 100:
            complexity_score += 0.1
        
        # Entropy estimation (simplified)
        unique_chars = len(set(payload))
        if unique_chars > 50:
            complexity_score += 0.3
        elif unique_chars > 30:
            complexity_score += 0.2
        
        # Suspicious content patterns
        suspicious_patterns = [
            r"\\x[0-9a-f]{2}", r"%[0-9a-f]{2}", r"eval\s*\(",
            r"exec\s*\(", r"system\s*\(", r"shell_exec",
            r"base64_decode", r"javascript:", r"<script"
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, payload, re.IGNORECASE):
                complexity_score += 0.2
                break
        
        return {
            "score": min(complexity_score, 1.0),
            "complexity": "high" if complexity_score > 0.6 else "medium" if complexity_score > 0.3 else "low"
        }
    
    def _analyze_target(self, dest_port: int, proto: str) -> Dict[str, Any]:
        """Analyze target criticality"""
        critical_ports = {
            22: ("ssh", 0.9),
            23: ("telnet", 0.8),
            80: ("http", 0.7),
            443: ("https", 0.7),
            3389: ("rdp", 0.9),
            5432: ("postgresql", 0.8),
            3306: ("mysql", 0.8),
            1433: ("mssql", 0.8),
            21: ("ftp", 0.6),
            25: ("smtp", 0.6)
        }
        
        if dest_port in critical_ports:
            service, criticality = critical_ports[dest_port]
            return {"score": criticality, "service": service, "critical": True}
        
        # High port range (potentially custom services)
        if dest_port > 8000:
            return {"score": 0.4, "service": "custom", "critical": False}
        
        return {"score": 0.3, "service": "unknown", "critical": False}
    
    def _analyze_source_reputation(self, src_ip: str) -> Dict[str, Any]:
        """Analyze source IP reputation with CIDR-aware classification"""
        if src_ip in self.reputation_cache:
            return self.reputation_cache[src_ip]

        reputation_score = 0.5  # Neutral baseline
        rep_type = "neutral"

        try:
            ip = ipaddress.ip_address(src_ip)

            if ip.is_private:
                # RFC1918 (10/8, 172.16/12, 192.168/16)
                reputation_score = 0.3
                rep_type = "private"
            elif ip.is_loopback or ip.is_link_local:
                reputation_score = 0.2
                rep_type = "local"
            elif ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                reputation_score = 0.8
                rep_type = "suspicious"
            else:
                # Public IPs remain neutral; optionally increase if odd formatting handled above
                reputation_score = 0.5
                rep_type = "public"
        except ValueError:
            # Invalid IP format
            reputation_score = 0.9
            rep_type = "invalid"

        result = {"score": reputation_score, "type": rep_type}
        self.reputation_cache[src_ip] = result
        return result
    
    def _analyze_temporal_context(self, src_ip: str, signature: str) -> Dict[str, Any]:
        """Analyze temporal patterns and frequency"""
        now = datetime.now()
        key = f"{src_ip}:{signature}"
        
        # Clean old entries (keep last 1 hour)
        cutoff = now - timedelta(hours=1)
        self.context_history[key] = [
            ts for ts in self.context_history[key] if ts > cutoff
        ]
        
        # Add current event
        self.context_history[key].append(now)
        
        # Frequency analysis
        event_count = len(self.context_history[key])
        
        if event_count > 10:  # High frequency
            return {"score": 0.9, "frequency": "high", "count": event_count}
        elif event_count > 5:  # Medium frequency
            return {"score": 0.6, "frequency": "medium", "count": event_count}
        else:  # Low frequency
            return {"score": 0.3, "frequency": "low", "count": event_count}
    
    def _analyze_protocol_anomaly(self, proto: str, dest_port: int, payload: str) -> Dict[str, Any]:
        """Analyze protocol-specific anomalies"""
        anomaly_score = 0
        
        # TCP-specific analysis
        if proto == "tcp":
            # Check for common HTTP patterns on non-HTTP ports
            if dest_port not in [80, 443, 8080, 8443] and "http" in payload.lower():
                anomaly_score += 0.4
            
            # Check for binary content on text-based services
            if dest_port in [80, 443, 22, 23] and re.search(r'\\x[0-9a-f]{2}', payload):
                anomaly_score += 0.3
        
        # UDP-specific analysis
        elif proto == "udp":
            # Large UDP payloads (potential amplification)
            if len(payload) > 1000:
                anomaly_score += 0.5
        
        return {"score": min(anomaly_score, 1.0), "anomalies": anomaly_score > 0.3}
    
    def _calculate_ensemble_score(self, features: Dict[str, Any]) -> int:
        """Calculate weighted ensemble score (1-5 scale)"""
        
        # Extract feature scores
        signature_risk = features["signature_score"]["risk"]
        payload_complexity = features["payload_score"]["score"] * 3  # Scale to 0-3
        target_criticality = features["target_score"]["score"] * 2   # Scale to 0-2
        reputation_risk = features["reputation_score"]["score"] * 2  # Scale to 0-2
        temporal_risk = features["temporal_score"]["score"] * 2      # Scale to 0-2
        protocol_anomaly = features["protocol_score"]["score"] * 2   # Scale to 0-2
        
        # Weighted sum
        weighted_score = (
            signature_risk * self.scoring_weights["signature_match"] +
            payload_complexity * self.scoring_weights["payload_complexity"] +
            target_criticality * self.scoring_weights["target_criticality"] +
            reputation_risk * self.scoring_weights["source_reputation"] +
            temporal_risk * self.scoring_weights["temporal_context"] +
            protocol_anomaly * self.scoring_weights["protocol_anomaly"]
        )
        
        # Convert to 1-5 scale and round
        final_risk = max(1, min(5, round(weighted_score)))
        
        return final_risk
    
    def _generate_explanation(self, features: Dict[str, Any], risk: int) -> str:
        """Generate human-readable explanation"""
        explanation_parts = []
        
        # Primary pattern match
        sig_info = features["signature_score"]
        if sig_info["confidence"] > 0.7:
            explanation_parts.append(f"{sig_info['category']}パターン検出")
        
        # Payload complexity
        payload_info = features["payload_score"]
        if payload_info["score"] > 0.5:
            explanation_parts.append(f"複雑なペイロード({payload_info['complexity']})")
        
        # Target criticality
        target_info = features["target_score"]
        if target_info["critical"]:
            explanation_parts.append(f"重要サービス({target_info['service']})")
        
        # Frequency
        temporal_info = features["temporal_score"]
        if temporal_info["frequency"] == "high":
            explanation_parts.append(f"高頻度攻撃({temporal_info['count']}回)")
        
        if not explanation_parts:
            return "総合的リスク評価に基づく判定"
        
        return "、".join(explanation_parts)
    
    def _create_llm_prompt(self, alert_data: Dict[str, Any], features: Dict[str, Any]) -> str:
        """Create LLM prompt for threat evaluation"""
        
        # Extract key information
        signature = ""
        if "signature" in alert_data:
            signature = alert_data["signature"]
        elif "alert" in alert_data and "signature" in alert_data["alert"]:
            signature = alert_data["alert"]["signature"]
        
        src_ip = alert_data.get("src_ip", "unknown")
        dest_port = alert_data.get("dest_port", "unknown")
        proto = alert_data.get("proto", "unknown")
        
        # Create structured prompt
        prompt = f"""
Network security alert analysis:

Alert Details:
- Signature: {signature}
- Source IP: {src_ip}
- Destination Port: {dest_port}
- Protocol: {proto}

Feature Analysis:
- Signature Score: {features.get('signature_score', {}).get('score', 0)}/5
- Payload Score: {features.get('payload_score', {}).get('score', 0)}/5
- Target Score: {features.get('target_score', {}).get('score', 0)}/5
- Reputation Score: {features.get('reputation_score', {}).get('score', 0)}/5

Please evaluate this network security alert and provide:
1. Risk level (1-5 scale)
2. Threat category
3. Explanation in Japanese

Consider patterns like brute force attacks, malware communication, exploitation attempts, reconnaissance, and denial of service.
"""
        
        return prompt


# Global offline evaluator instance
_offline_evaluator: OfflineAIEvaluator = None

def get_offline_evaluator() -> OfflineAIEvaluator:
    """Get or create offline evaluator instance"""
    global _offline_evaluator
    
    if _offline_evaluator is None:
        _offline_evaluator = OfflineAIEvaluator()
    
    return _offline_evaluator

def evaluate_with_offline_ai(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function for offline AI evaluation"""
    evaluator = get_offline_evaluator()
    return evaluator.evaluate_threat(alert_data)