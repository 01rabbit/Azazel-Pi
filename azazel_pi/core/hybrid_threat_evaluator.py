#!/usr/bin/env python3
"""
Hybrid Threat Evaluator - Legacy + Mock LLM Integration
Combines rule-based legacy logic with AI-enhanced Mock LLM for optimal threat assessment
"""

import logging
from typing import Dict, Any, Tuple
from azazel_pi.core.offline_ai_evaluator import evaluate_with_offline_ai

logger = logging.getLogger(__name__)

class HybridThreatEvaluator:
    """統合脅威評価システム - Legacy Logic + Mock LLM"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # カテゴリ別基準スコア (Legacy準拠で調整)
        self.category_base_scores = {
            "exploit": 80,      # Buffer overflow, RCE
            "malware": 75,      # C2, Trojan, Backdoor  
            "sqli": 70,         # SQL injection
            "dos": 65,          # DoS, DDoS attacks
            "bruteforce": 55,   # Brute force attempts
            "scan": 45,         # Reconnaissance
            "unknown": 30,      # Unclassified
            "benign": 10        # Normal traffic
        }
        
        # 正常トラフィック判定パターン
        self.benign_patterns = [
            "legitimate", "normal", "benign", "routine",
            "https request", "http get", "dns query",
            "software update", "heartbeat", "keepalive"
        ]
        
        # 高危険シグネチャパターン (Legacy準拠)
        self.high_risk_patterns = [
            "exploit", "malware", "trojan", "backdoor",
            "shellcode", "injection", "overflow"
        ]
        
        # 中危険シグネチャパターン
        self.medium_risk_patterns = [
            "dos", "ddos", "flood", "brute", "bruteforce",
            "scan", "probe", "reconnaissance"
        ]
    
    def evaluate_threat_hybrid(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """ハイブリッド脅威評価 - Legacy + Mock LLM統合"""
        
        signature = alert_data.get("signature", "")
        
        # 1. Mock LLM評価を取得
        try:
            mock_result = evaluate_with_offline_ai(alert_data)
            mock_risk = mock_result["risk"]
            mock_category = mock_result["category"]
            
            self.logger.debug(f"Mock LLM: risk={mock_risk}, category={mock_category}")
        except Exception as e:
            self.logger.warning(f"Mock LLM evaluation failed: {e}")
            # フォールバック: Legacy のみ
            return self._legacy_only_evaluation(alert_data)
        
        # 2. Legacy ルールベース評価
        legacy_score = self._calculate_legacy_score(alert_data, signature)
        self.logger.debug(f"Legacy score: {legacy_score}")
        
        # 3. 正常トラフィック判定 (Legacy重視)
        if self._is_benign_traffic(signature, alert_data):
            return {
                "risk": 1,
                "reason": "正常トラフィックとして判定",
                "category": "benign",
                "score": min(legacy_score, 15),  # 正常トラフィックは15点以下
                "ai_used": True,
                "model": "hybrid_legacy+mock_llm",
                "confidence": 0.9,
                "evaluation_method": "benign_override"
            }
        
        # 4. カテゴリ別基準スコアの適用
        base_score = self.category_base_scores.get(mock_category, 30)
        
        # 5. Legacy とMock LLMの統合スコア計算
        # Legacy 60% + Mock LLM 40% の重み付け
        mock_score_100 = (mock_risk - 1) * 25  # 1-5 → 0-100
        integrated_score = int(legacy_score * 0.6 + mock_score_100 * 0.4)
        
        # 6. カテゴリベース較正
        if mock_category in ["exploit", "malware", "sqli"]:
            # 高危険カテゴリは最低60点保証
            final_score = max(integrated_score, 60)
        elif mock_category in ["dos", "bruteforce"]:
            # 中危険カテゴリは最低40点保証
            final_score = max(integrated_score, 40)
        else:
            final_score = integrated_score
        
        # 7. 最終リスクレベル計算 (1-5スケール)
        if final_score >= 80:
            final_risk = 5
        elif final_score >= 60:
            final_risk = 4
        elif final_score >= 40:
            final_risk = 3
        elif final_score >= 20:
            final_risk = 2
        else:
            final_risk = 1
        
        # 8. 統合理由生成
        legacy_contribution = f"Legacy評価: {legacy_score}点"
        mock_contribution = f"Mock LLM評価: {mock_result['reason'][:50]}"
        integrated_reason = f"{legacy_contribution} + {mock_contribution}"
        
        return {
            "risk": final_risk,
            "reason": integrated_reason,
            "category": mock_category,
            "score": final_score,
            "ai_used": True,
            "model": "hybrid_legacy+mock_llm",
            "confidence": mock_result.get("confidence", 0.8),
            "evaluation_method": "hybrid_integration",
            "components": {
                "legacy_score": legacy_score,
                "mock_llm_score": mock_score_100,
                "integration_weight": "legacy_60%_mock_40%"
            }
        }
    
    def _calculate_legacy_score(self, alert_data: Dict[str, Any], signature: str) -> int:
        """従来のルールベーススコア計算"""
        base_score = 0
        
        # 1. Suricata severity基準スコア
        suricata_severity = alert_data.get('severity', 3)
        severity_mapping = {1: 25, 2: 15, 3: 8, 4: 3}
        base_score = severity_mapping.get(suricata_severity, 5)
        
        # 2. シグネチャパターンベース加算
        sig_lower = signature.lower()
        
        # 高危険度パターン (+20-30)
        if any(pattern in sig_lower for pattern in self.high_risk_patterns):
            if any(pattern in sig_lower for pattern in ["exploit", "malware", "trojan", "backdoor"]):
                base_score += 30
            else:  # shellcode, injection, overflow
                base_score += 25
        # 中危険度パターン (+10-20)
        elif any(pattern in sig_lower for pattern in self.medium_risk_patterns):
            if any(pattern in sig_lower for pattern in ["nmap", "scan", "probe", "reconnaissance"]):
                base_score += 20
            elif any(pattern in sig_lower for pattern in ["dos", "ddos", "flood"]):
                base_score += 15
            elif any(pattern in sig_lower for pattern in ["brute", "bruteforce", "dictionary"]):
                base_score += 12
            else:
                base_score += 10
        
        # 3. ポートベース加算
        dest_port = alert_data.get('dest_port')
        critical_ports = [22, 80, 443, 3389, 5432, 3306, 1433]
        if dest_port in critical_ports:
            base_score += 8
        
        # 4. プロトコル調整
        proto = alert_data.get('proto', '').upper()
        if proto == 'TCP':
            base_score += 3
        elif proto == 'ICMP':
            base_score += 1
        
        return min(max(base_score, 0), 100)
    
    def _is_benign_traffic(self, signature: str, alert_data: Dict[str, Any]) -> bool:
        """正常トラフィック判定 (Legacy優先)"""
        sig_lower = signature.lower()
        
        # 明示的な正常パターン
        if any(pattern in sig_lower for pattern in self.benign_patterns):
            return True
        
        # HTTPSトラフィックで危険パターンがない場合
        dest_port = alert_data.get('dest_port')
        if dest_port == 443 and not any(pattern in sig_lower for pattern in 
                                      self.high_risk_patterns + self.medium_risk_patterns):
            return True
        
        # Suricata severity 4 (最低危険度) かつ危険パターンなし
        severity = alert_data.get('severity', 3)
        if severity == 4 and not any(pattern in sig_lower for pattern in 
                                   self.high_risk_patterns + self.medium_risk_patterns):
            return True
        
        return False
    
    def _legacy_only_evaluation(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock LLM失敗時のLegacyフォールバック"""
        signature = alert_data.get("signature", "")
        legacy_score = self._calculate_legacy_score(alert_data, signature)
        
        # Legacy スコアからリスクレベル計算
        if legacy_score >= 60:
            risk = 5
        elif legacy_score >= 45:
            risk = 4
        elif legacy_score >= 30:
            risk = 3
        elif legacy_score >= 15:
            risk = 2
        else:
            risk = 1
        
        return {
            "risk": risk,
            "reason": f"Legacy評価のみ: {legacy_score}点",
            "category": "unknown",
            "score": legacy_score,
            "ai_used": False,
            "model": "legacy_fallback",
            "confidence": 0.7,
            "evaluation_method": "legacy_only"
        }


# グローバルハイブリッド評価インスタンス
_hybrid_evaluator: HybridThreatEvaluator = None

def get_hybrid_evaluator() -> HybridThreatEvaluator:
    """ハイブリッド評価インスタンスの取得"""
    global _hybrid_evaluator
    
    if _hybrid_evaluator is None:
        _hybrid_evaluator = HybridThreatEvaluator()
    
    return _hybrid_evaluator

def evaluate_with_hybrid_system(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """ハイブリッド脅威評価の実行"""
    evaluator = get_hybrid_evaluator()
    return evaluator.evaluate_threat_hybrid(alert_data)