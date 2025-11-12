#!/usr/bin/env python3
"""
Hybrid Threat Evaluator - Legacy + Mock LLM + Ollama Integration
Combines rule-based legacy logic with AI-enhanced Mock LLM for known threats,
and uses Ollama for unknown/uncertain threats
"""

import logging
from typing import Dict, Any, Tuple, Optional
from azazel_pi.core.offline_ai_evaluator import evaluate_with_offline_ai
from .async_ai import enqueue as enqueue_deep_eval

logger = logging.getLogger(__name__)

# Ollama evaluator (遅延インポート)
_ollama_evaluator = None

def _get_ollama_evaluator(config: Optional[Dict[str, Any]] = None):
    """Ollama評価器を取得（初回のみインポート）"""
    global _ollama_evaluator
    if _ollama_evaluator is None:
        try:
            from azazel_pi.core.ai_evaluator import get_ai_evaluator
            _ollama_evaluator = get_ai_evaluator(config)
            logger.info("Ollama evaluator initialized for unknown threat analysis")
        except Exception as e:
            logger.warning(f"Ollama evaluator initialization failed: {e}")
            _ollama_evaluator = False  # 失敗をマーク
    return _ollama_evaluator if _ollama_evaluator is not False else None

class HybridThreatEvaluator:
    """統合脅威評価システム - Legacy Logic + Mock LLM + Ollama（未知の脅威用）"""
    
    def __init__(self, ollama_config: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(__name__)
        self.ollama_config = ollama_config or {}
        
        # 未知の脅威検出のしきい値
        self.unknown_confidence_threshold = 0.7  # 信頼度がこれ以下ならOllama使用
        self.unknown_categories = {"unknown", "benign"}  # これらのカテゴリでもOllama検討
        
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
        """ハイブリッド脅威評価 - Legacy + Mock LLM + Ollama（未知の脅威用）"""
        # Defensive: ensure signature is a string
        signature = str(alert_data.get("signature", "") or "")

        # 1. Mock LLM評価を取得（高速・軽量）
        try:
            mock_result = evaluate_with_offline_ai(alert_data)
            mock_risk = mock_result["risk"]
            mock_category = mock_result["category"]
            mock_confidence = mock_result.get("confidence", 0.5)
            
            self.logger.debug(f"Mock LLM: risk={mock_risk}, category={mock_category}, confidence={mock_confidence}")
        except Exception as e:
            self.logger.warning(f"Mock LLM evaluation failed: {e}")
            return self._legacy_only_evaluation(alert_data)
        
        # 2. 未知の脅威検出: 信頼度が低い or unknownカテゴリ
        is_unknown_threat = (
            mock_confidence < self.unknown_confidence_threshold or
            mock_category in self.unknown_categories or
            mock_risk <= 2  # 低リスクだが確証がない場合
        )
        
        # 3. 未知の脅威の場合、Ollamaで再評価
        ollama_result = None
        if is_unknown_threat:
            self.logger.info(f"未知の脅威の可能性 (confidence={mock_confidence}, category={mock_category}) - Ollama評価を実行")
            ollama_evaluator = _get_ollama_evaluator(self.ollama_config)
            
            if ollama_evaluator:
                try:
                    ollama_result = ollama_evaluator.evaluate_threat(alert_data)
                    if ollama_result.get("ai_used", False):
                        self.logger.info(f"Ollama評価成功: risk={ollama_result['risk']}, category={ollama_result['category']}")

                        # If legacy heuristic already labels this as benign, respect that override
                        if self._is_benign_traffic(signature, alert_data):
                            return {
                                "risk": 1,
                                "reason": "正常トラフィックとして判定",
                                "category": "benign",
                                "score": min(self._calculate_legacy_score(alert_data, signature), 15),
                                "ai_used": True,
                                "model": "hybrid_legacy+mock_llm",
                                "confidence": 0.9,
                                "evaluation_method": "benign_override"
                            }

                        # Ollamaの評価を優先（未知の脅威に強い）
                        ollama_score = (ollama_result["risk"] - 1) * 25  # 1-5 → 0-100

                        # Mock LLMとOllamaの統合（Ollama優先度高め: 70%）
                        mock_score = (mock_risk - 1) * 25
                        integrated_score = int(ollama_score * 0.7 + mock_score * 0.3)
                        
                        return self._finalize_evaluation(
                            integrated_score,
                            ollama_result["category"],
                            f"Ollama深堀り分析: {ollama_result['reason'][:50]}...",
                            ollama_result,
                            evaluation_method="ollama_unknown_threat"
                        )
                except Exception as e:
                    self.logger.warning(f"Ollama評価エラー、Mock LLMにフォールバック: {e}")
        
        # 4. Legacy ルールベース評価
        legacy_score = self._calculate_legacy_score(alert_data, signature)
        self.logger.debug(f"Legacy score: {legacy_score}")
        
        # 5. 正常トラフィック判定 (Legacy重視)
        if self._is_benign_traffic(signature, alert_data):
            return {
                "risk": 1,
                "reason": "正常トラフィックとして判定",
                "category": "benign",
                "score": min(legacy_score, 15),
                "ai_used": True,
                "model": "hybrid_legacy+mock_llm",
                "confidence": 0.9,
                "evaluation_method": "benign_override"
            }
        
        # 6. カテゴリ別基準スコアの適用
        base_score = self.category_base_scores.get(mock_category, 30)
        
        # 7. Legacy とMock LLMの統合スコア計算
        # Legacy 60% + Mock LLM 40% の重み付け
        mock_score_100 = (mock_risk - 1) * 25  # 1-5 → 0-100
        integrated_score = int(legacy_score * 0.6 + mock_score_100 * 0.4)
        
        # 8. カテゴリベース較正
        if mock_category in ["exploit", "malware", "sqli"]:
            final_score = max(integrated_score, 60)
        elif mock_category in ["dos", "bruteforce"]:
            final_score = max(integrated_score, 40)
        else:
            final_score = integrated_score
        
        # 9. 統合理由生成
        legacy_contribution = f"Legacy評価: {legacy_score}点"
        mock_contribution = f"Mock LLM評価: {mock_result['reason'][:50]}"
        integrated_reason = f"{legacy_contribution} + {mock_contribution}"
        
        return self._finalize_evaluation(
            final_score,
            mock_category,
            integrated_reason,
            mock_result,
            evaluation_method="hybrid_integration",
            components={
                "legacy_score": legacy_score,
                "mock_llm_score": mock_score_100,
                "integration_weight": "legacy_60%_mock_40%"
            }
        )
    
    
    def _finalize_evaluation(self, score: int, category: str, reason: str, 
                            ai_result: Dict[str, Any], evaluation_method: str,
                            components: Optional[Dict] = None) -> Dict[str, Any]:
        """最終評価結果の作成"""
        # スコアを1-5リスクレベルに変換
        if score >= 80:
            final_risk = 5
        elif score >= 60:
            final_risk = 4
        elif score >= 40:
            final_risk = 3
        elif score >= 20:
            final_risk = 2
        else:
            final_risk = 1
        
        result = {
            "risk": final_risk,
            "reason": reason,
            "category": category,
            "score": score,
            "ai_used": True,
            "model": ai_result.get("model", "hybrid_legacy+mock_llm"),
            "confidence": ai_result.get("confidence", 0.8),
            "evaluation_method": evaluation_method
        }
        
        if components:
            result["components"] = components
        
        return result
    
    def _calculate_legacy_score(self, alert_data: Dict[str, Any], signature: str) -> int:
        """従来のルールベーススコア計算"""
        # Defensive: ensure signature is a string
        signature = str(signature or "")
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
        # Defensive: ensure signature is a string
        signature = str(signature or "")
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
_hybrid_evaluator: Optional[HybridThreatEvaluator] = None

def get_hybrid_evaluator(config: Optional[Dict[str, Any]] = None) -> HybridThreatEvaluator:
    """ハイブリッド評価インスタンスの取得"""
    global _hybrid_evaluator
    
    if _hybrid_evaluator is None:
        # 設定ファイルからOllama設定を読み込み
        ollama_config = None
        if config:
            ollama_config = config.get("ai", {})
        _hybrid_evaluator = HybridThreatEvaluator(ollama_config)
    
    return _hybrid_evaluator

def evaluate_with_hybrid_system(alert_data: Dict[str, Any], 
                                config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ハイブリッド脅威評価の実行"""
    # The hybrid evaluator object still exists for legacy synchronous use,
    # but here we prioritize a fast Mock-LLM (offline) evaluation and
    # schedule expensive Ollama-based deep analysis asynchronously when
    # mock confidence is low or category is unknown.
    try:
        # Fast offline/mock evaluation
        mock_result = evaluate_with_offline_ai(alert_data)

        # If the mock LLM marks low confidence or unknown category, enqueue deep eval
        confidence = float(mock_result.get("confidence", 0.0) or 0.0)
        category = (mock_result.get("category") or "").lower()
        unknown_categories = {"unknown", "benign"}
        # Threshold under which we want deeper analysis (tunable)
        DEEP_CONF_THRESHOLD = 0.7

        if confidence < DEEP_CONF_THRESHOLD or category in unknown_categories:
            try:
                # Provide decisions log path to async worker so deep result can be persisted
                try:
                    from azazel_pi.core import notify_config as _nc
                    decisions_path = _nc._get_nested(_nc._CFG, "paths.decisions", None) or _nc._DEFAULTS["paths"]["decisions"]
                except Exception:
                    decisions_path = None

                enqueue_deep_eval(alert_data, context={"decisions_log": decisions_path})
                mock_result["deferred"] = True
            except Exception:
                # If enqueue fails, mark as not deferred but continue
                mock_result["deferred"] = False
        else:
            mock_result["deferred"] = False

        # If the offline/mock result does not provide a 0-100 'score' field,
        # fall back to the richer HybridThreatEvaluator path to produce a
        # fully-normalized evaluation result used elsewhere in the code/tests.
        if "score" not in mock_result:
            evaluator = get_hybrid_evaluator(config)
            return evaluator.evaluate_threat_hybrid(alert_data)

        return mock_result
    except Exception:
        # Fallback to the original hybrid evaluator when offline fails
        evaluator = get_hybrid_evaluator(config)
        return evaluator.evaluate_threat_hybrid(alert_data)