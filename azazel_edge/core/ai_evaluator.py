#!/usr/bin/env python3
"""
AI-powered threat evaluation using Ollama LLM
Integrates with existing state_machine and scoring system
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

class AIThreatEvaluator:
    """LLM-based threat evaluator for Suricata alerts"""
    
    def __init__(self, 
                 ollama_url: str = "http://127.0.0.1:11434/api/generate",
                 model: str = "phi3:mini",
                 timeout: int = 30,
                 max_payload_chars: int = 400):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout
        self.max_payload_chars = max_payload_chars
        self._model_available = False
        self._last_health_check = 0
        self._health_check_interval = 300  # 5 minutes
        
    def _check_model_availability(self) -> bool:
        """Check if Ollama service and model are available"""
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return self._model_available
            
        self._last_health_check = now
        try:
            # Quick health check
            response = requests.get(
                "http://127.0.0.1:11434/api/tags", 
                timeout=5
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                # Check if any models are available (not necessarily the preferred one)
                if models:
                    # Prefer the configured model, but accept any available model
                    available_models = [model.get("name", "") for model in models]
                    if any(self.model in name for name in available_models):
                        self._model_available = True
                    elif available_models:
                        # Use first available model as fallback
                        logger.info(f"Preferred model {self.model} not found, using {available_models[0]}")
                        self.model = available_models[0].split(":")[0] + ":" + available_models[0].split(":")[1]
                        self._model_available = True
                    else:
                        self._model_available = False
                else:
                    self._model_available = False
            else:
                self._model_available = False
        except Exception as e:
            logger.debug(f"Ollama health check failed: {e}")
            self._model_available = False
            
        return self._model_available
    
    def _shorten_payload(self, payload: str) -> str:
        """Truncate payload to reasonable length"""
        if not payload:
            return ""
        try:
            if len(payload) <= self.max_payload_chars:
                return payload
            return payload[:self.max_payload_chars] + "..."
        except Exception:
            return ""
    
    def _build_prompt(self, alert_data: Dict[str, Any]) -> str:
        """Build structured prompt from alert data"""
        signature = alert_data.get("signature", "")
        src_ip = alert_data.get("src_ip", "")
        dest_ip = alert_data.get("dest_ip", "")
        proto = alert_data.get("proto", "")
        dest_port = alert_data.get("dest_port", "")
        http_host = alert_data.get("http", {}).get("hostname", "")
        payload = self._shorten_payload(
            alert_data.get("payload_printable", "")
        )
        
        prompt = f"""あなたはネットワーク脅威アナリスト。次のSuricataアラートを評価し、厳密にJSONフォーマットで応答:
{{"risk":1,"reason":"理由","category":"カテゴリ"}}

risk: 1-5の整数 (1=低, 2=軽微, 3=中程度, 4=高, 5=深刻)
category: scan|bruteforce|exploit|malware|dos|benign のいずれか

アラート情報:
シグネチャ: {signature}
プロトコル/ポート: {proto}/{dest_port}
送信元: {src_ip} → 宛先: {dest_ip}
HTTPホスト: {http_host}
ペイロード: {payload}

JSONのみ出力:"""
        
        return prompt
    
    def _extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response text"""
        # Try to find JSON in the response
        json_match = re.search(r'\{[^}]*\}', text, re.S)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Fallback: try to parse the entire response
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Default fallback
        return {
            "risk": 2,
            "reason": "AI解析失敗 - デフォルト判定",
            "category": "unknown"
        }
    
    def evaluate_threat(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate threat level using LLM or enhanced offline AI"""
        
        # Check if AI is available
        if not self._check_model_availability():
            logger.debug("Ollama not available, using enhanced offline AI evaluation")
            return evaluate_with_offline_ai(alert_data)
        
        try:
            prompt = self._build_prompt(alert_data)
            
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 128,
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "stop": ["\n", "```"]
                    }
                },
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"Ollama request failed: {response.status_code}")
                return self._fallback_evaluation(alert_data)
            
            response_data = response.json()
            ai_response = response_data.get("response", "{}")
            
            result = self._extract_json_from_response(ai_response)
            
            # Validate and sanitize result
            risk = max(1, min(5, int(result.get("risk", 2))))
            reason = str(result.get("reason", "AI評価"))[:200]  # Limit reason length
            category = str(result.get("category", "unknown"))
            
            logger.info(f"AI評価: risk={risk}, category={category}, reason={reason[:50]}...")
            
            return {
                "risk": risk,
                "reason": reason,
                "category": category,
                "ai_used": True,
                "model": self.model
            }
            
        except Timeout:
            logger.warning("Ollama request timeout")
            return self._fallback_evaluation(alert_data)
        except RequestException as e:
            logger.warning(f"Ollama request error: {e}")
            return self._fallback_evaluation(alert_data)
        except Exception as e:
            logger.error(f"AI evaluation error: {e}")
            return self._fallback_evaluation(alert_data)
    
    def _fallback_evaluation(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback threat evaluation when AI is unavailable"""
        signature = alert_data.get("signature", "").lower()
        proto = alert_data.get("proto", "").lower()
        dest_port = alert_data.get("dest_port", 0)
        
        # Rule-based fallback scoring
        risk = 2  # Default medium-low
        reason = "ルールベース判定"
        category = "unknown"
        
        # High-risk patterns
        if any(pattern in signature for pattern in [
            "exploit", "malware", "trojan", "backdoor", "shellcode"
        ]):
            risk = 4
            category = "exploit"
            reason = "既知の攻撃パターン"
        elif any(pattern in signature for pattern in [
            "brute", "password", "login", "auth"
        ]):
            risk = 3
            category = "bruteforce"
            reason = "認証攻撃の疑い"
        elif any(pattern in signature for pattern in [
            "scan", "probe", "recon", "nmap"
        ]):
            risk = 2
            category = "scan"
            reason = "偵察活動"
        elif "dos" in signature or "flood" in signature:
            risk = 4
            category = "dos"
            reason = "DoS攻撃の疑い"
        
        # Port-based adjustment
        if dest_port in (22, 23, 3389):  # SSH, Telnet, RDP
            risk = min(5, risk + 1)
        elif dest_port in (80, 443, 8080):  # Web services
            if risk < 3:
                risk = 2
                
        return {
            "risk": risk,
            "reason": reason,
            "category": category,
            "ai_used": False,
            "model": "fallback"
        }


# Global AI evaluator instance
_ai_evaluator: Optional[AIThreatEvaluator] = None

def get_ai_evaluator(config: Optional[Dict[str, Any]] = None) -> AIThreatEvaluator:
    """Get or create AI evaluator instance"""
    global _ai_evaluator
    
    if _ai_evaluator is None:
        if config is None:
            config = {}
            
        ai_config = config.get("ai", {})
        _ai_evaluator = AIThreatEvaluator(
            ollama_url=ai_config.get("ollama_url", "http://127.0.0.1:11434/api/generate"),
            model=ai_config.get("model", "phi3:mini"),
            timeout=ai_config.get("timeout", 30),
            max_payload_chars=ai_config.get("max_payload_chars", 400)
        )
    
    return _ai_evaluator

def evaluate_alert_with_ai(alert_data: Dict[str, Any], 
                          config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function to evaluate alert with AI"""
    evaluator = get_ai_evaluator(config)
    return evaluator.evaluate_threat(alert_data)