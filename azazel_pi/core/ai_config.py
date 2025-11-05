#!/usr/bin/env python3
"""
AI Integration Configuration for Azazel-Pi
Sets up the enhanced AI evaluator with Mock LLM support
"""

import json
from typing import Dict, Any

class AIConfig:
    """AI system configuration"""
    
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Get AI configuration"""
        return {
            "ai_system": {
                "primary_evaluator": "ollama_enhanced",
                "enable_mock_llm": False,
                "fallback_enabled": True,
                "ollama_integration": True,  # Enabled with Qwen2.5-1.5B
                "settings": {
                    "confidence_threshold": 0.7,
                    "risk_scaling": True,
                    "ensemble_weights": {
                        "pattern_matching": 0.4,
                        "payload_analysis": 0.15,
                        "target_analysis": 0.15,
                        "reputation_analysis": 0.1,
                        "temporal_analysis": 0.1,
                        "protocol_analysis": 0.1
                    }
                }
            },
            "mock_llm": {
                "enabled": True,
                "response_templates": True,
                "conversation_history": 10,
                "realistic_variation": True
            },
            "ollama": {
                "enabled": True,
                "container_name": "azazel_ollama",
                "model": "threatjudge",
                "base_url": "http://127.0.0.1:11434",
                "timeout_seconds": 30,
                "retry_attempts": 3,
                "model_file": "qwen2.5-1.5b-instruct-q4_K_M.gguf",
                "host_model_path": "/opt/models/qwen"
            }
        }
    
    @staticmethod
    def save_config(config_path: str = "/home/azazel/Azazel-Pi/configs/ai_config.json"):
        """Save AI configuration to file"""
        config = AIConfig.get_config()
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return config_path

if __name__ == "__main__":
    config_path = AIConfig.save_config()
    print(f"AI configuration saved to: {config_path}")
    
    # Test configuration loading
    with open(config_path, 'r', encoding='utf-8') as f:
        loaded_config = json.load(f)
    
    print("Configuration loaded successfully:")
    print(f"Primary evaluator: {loaded_config['ai_system']['primary_evaluator']}")
    print(f"Mock LLM enabled: {loaded_config['mock_llm']['enabled']}")
    print(f"Ollama enabled: {loaded_config['ollama']['enabled']}")