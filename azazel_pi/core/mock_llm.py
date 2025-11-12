#!/usr/bin/env python3
"""
Enhanced Offline AI Model Simulation
Simulates LLM-like responses for threat evaluation when real models are unavailable
"""

import json
import re
import random
import hashlib
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class MockLLMEvaluator:
    """Mock LLM that provides realistic threat evaluation responses"""
    
    def __init__(self):
        self.response_templates = self._load_response_templates()
        self.conversation_history = []
        
    def _load_response_templates(self) -> Dict[str, List[str]]:
        """Load response templates for different threat categories"""
        return {
            "bruteforce": [
                "認証攻撃パターンを検出。複数回の失敗ログインから、自動化されたパスワード攻撃の可能性が高い。",
                "辞書攻撃またはブルートフォース攻撃の典型的なパターン。攻撃者が認証情報を総当たりで試行している。",
                "SSH/RDPなどのリモートアクセスサービスに対する認証突破試行。防御措置が必要。"
            ],
            "scan": [
                "ネットワーク偵察活動を確認。攻撃者がシステムの脆弱性を調査している可能性。",
                "ポートスキャンやサービス列挙の兆候。攻撃準備段階の活動と推定される。",
                "システム情報収集を目的とした探査活動。後続の攻撃に備えた偵察フェーズ。"
            ],
            "exploit": [
                "既知の脆弱性を狙った攻撃コードを検出。システムへの不正侵入を試行している。",
                "エクスプロイトペイロードの特徴を確認。リモートコード実行の危険性が高い。",
                "脆弱性攻撃ツールの使用を示すパターン。即座の対応が必要な深刻な脅威。"
            ],
            "malware": [
                "マルウェア通信またはC2サーバーとの接続を検出。感染端末の可能性がある。",
                "悪意のあるペイロードまたはボットネット活動の兆候。システム感染が疑われる。",
                "トロイの木馬やバックドアの動作パターン。データ窃取や横展開のリスクあり。"
            ],
            "sqli": [
                "SQLインジェクション攻撃を検出。データベースへの不正アクセス試行。",
                "データベース操作を狙った悪意のあるクエリ。機密情報漏洩のリスクが高い。",
                "Webアプリケーションの脆弱性を悪用した攻撃。データ改ざんの可能性あり。"
            ],
            "dos": [
                "サービス拒否攻撃の兆候を確認。システムリソースの枯渇を狙っている。",
                "大量のトラフィックによる過負荷攻撃。サービス可用性への脅威。",
                "DDoS攻撃またはリソース消費型攻撃。システム停止のリスクあり。"
            ],
            "benign": [
                "正常なネットワーク活動と判定。定期的な通信または管理作業の可能性。",
                "通常業務の範囲内の活動。脅威レベルは低いが継続監視が推奨される。",
                "良性のトラフィックと評価。一般的なネットワーク動作の範囲内。"
            ]
        }
    
    def generate_response(self, prompt: str) -> str:
        """Generate LLM-like response for threat evaluation"""
        # Defensive: ensure prompt is a string to avoid NoneType errors
        prompt = str(prompt or "")

        # Extract key information from prompt
        risk_level = self._analyze_prompt_for_risk(prompt)
        category = self._analyze_prompt_for_category(prompt)
        reason = self._generate_reason(category, prompt)
        
        # Simulate LLM response with some natural variation
        response = {
            "risk": risk_level,
            "reason": reason,
            "category": category
        }
        
        # Add conversation to history
        self.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "response": response
        })
        
        # Keep only last 10 conversations
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]
        
        return json.dumps(response, ensure_ascii=False)
    
    def _analyze_prompt_for_risk(self, prompt: str) -> int:
        """Analyze prompt to determine risk level"""
        # Defensive: coerce to string and lowercase once
        prompt_lower = str(prompt or "").lower()
        # 乱数の非決定性を抑えるため、プロンプト内容から安定シードを生成
        seed = int(hashlib.md5(prompt_lower.encode("utf-8")).hexdigest(), 16) & 0x7FFFFFFF
        rng = random.Random(seed)
        
        # High risk indicators
        high_risk_patterns = [
            "exploit", "malware", "trojan", "backdoor", "shellcode",
            "injection", "overflow", "vulnerability", "攻撃", "悪意"
        ]
        
        # Medium risk indicators  
        medium_risk_patterns = [
            "brute", "force", "dos", "ddos", "flood", "scan", "probe",
            "認証", "ブルート", "スキャン"
        ]
        
        # Low risk indicators
        low_risk_patterns = [
            "ping", "discovery", "benign", "normal", "legitimate",
            "正常", "通常", "発見"
        ]
        
        if any(pattern in prompt_lower for pattern in high_risk_patterns):
            return rng.randint(4, 5)
        elif any(pattern in prompt_lower for pattern in medium_risk_patterns):
            return rng.randint(2, 4)
        elif any(pattern in prompt_lower for pattern in low_risk_patterns):
            return rng.randint(1, 2)
        else:
            return rng.randint(2, 3)  # Default medium-low
    
    def _analyze_prompt_for_category(self, prompt: str) -> str:
        """Analyze prompt to determine threat category with priority-based matching"""
        # Defensive: coerce to string and lowercase once
        prompt_lower = str(prompt or "").lower()
        
        # 優先度順でカテゴリパターンを定義（具体的なものから先に判定）
        category_patterns = [
            ("sqli", ["sql injection", "union select", "database injection", "select from", "drop table", "sql", "union", "データベース"]),
            ("malware", ["trojan", "malware", "c2 server", "beacon", "virus", "bot", "backdoor", "マルウェア", "ウイルス"]),
            ("exploit", ["buffer overflow", "exploit", "shellcode", "vulnerability", "overflow", "脆弱性"]),
            ("dos", ["dos", "ddos", "syn flood", "flood", "amplification", "過負荷"]),
            ("scan", ["nmap", "port scan", "scan", "probe", "recon", "discovery", "スキャン", "探査"]),
            ("bruteforce", ["brute", "force", "login", "auth", "password", "認証", "ログイン"])
        ]
        
        # 優先度順にマッチング
        for category, patterns in category_patterns:
            if any(pattern in prompt_lower for pattern in patterns):
                return category
        
        # フォールバック: より細かいマッチング
        if "injection" in prompt_lower:
            return "sqli"
        elif "attack" in prompt_lower and "brute" not in prompt_lower:
            return "exploit"
        elif "communication" in prompt_lower or "server" in prompt_lower:
            return "malware"
        
        return "unknown"
    
    def _generate_reason(self, category: str, prompt: str) -> str:
        """Generate explanation reason based on category"""
        if category in self.response_templates:
            base_reason = random.choice(self.response_templates[category])

            # Defensive: coerce prompt to string and lowercase for checks
            prompt_lower = str(prompt or "").lower()

            # Add some context from the prompt
            if "ssh" in prompt_lower:
                base_reason += " SSHサービスが標的。"
            elif "http" in prompt_lower:
                base_reason += " Webサービスへの攻撃。"
            elif "database" in prompt_lower or "sql" in prompt_lower:
                base_reason += " データベースが標的。"

            return base_reason
        else:
            return "総合的な脅威分析に基づく評価。継続的な監視が推奨される。"
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get recent conversation history"""
        return self.conversation_history.copy()


# Global mock LLM instance
_mock_llm: MockLLMEvaluator = None

def get_mock_llm() -> MockLLMEvaluator:
    """Get or create mock LLM instance"""
    global _mock_llm
    
    if _mock_llm is None:
        _mock_llm = MockLLMEvaluator()
    
    return _mock_llm

def simulate_llm_request(prompt: str) -> str:
    """Simulate LLM API request"""
    mock_llm = get_mock_llm()
    return mock_llm.generate_response(prompt)