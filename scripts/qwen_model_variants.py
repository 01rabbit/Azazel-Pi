#!/usr/bin/env python3
"""
Qwen2.5 1.5B Model Variants Discovery
Find available quantized versions and formats
"""

import requests
import json
from typing import List, Dict

def search_qwen_models():
    """Search for Qwen2.5 1.5B model variants"""
    
    print("🔍 Available Qwen2.5 1.5B Model Variants")
    print("=" * 60)
    
    # Known repositories with Qwen2.5 1.5B variants
    repositories = [
        {
            "name": "Qwen/Qwen2.5-1.5B-Instruct",
            "description": "Official Qwen2.5 1.5B Instruct model",
            "formats": ["pytorch", "safetensors"]
        },
        {
            "name": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", 
            "description": "Official GGUF format (Ollama compatible)",
            "formats": ["gguf"]
        },
        {
            "name": "bartowski/Qwen2.5-1.5B-Instruct-GGUF",
            "description": "Community GGUF with multiple quantizations",
            "formats": ["gguf - multiple quants"]
        },
        {
            "name": "lmstudio-community/Qwen2.5-1.5B-Instruct-GGUF",
            "description": "LM Studio optimized GGUF versions",
            "formats": ["gguf - optimized"]
        },
        {
            "name": "huggingface/Qwen2.5-1.5B-Instruct-Q4_0-GGUF",
            "description": "Hugging Face Q4_0 quantized version",
            "formats": ["gguf - q4_0"]
        }
    ]
    
    print("📋 Main Repositories:")
    for i, repo in enumerate(repositories, 1):
        print(f"{i}. {repo['name']}")
        print(f"   📝 {repo['description']}")
        print(f"   📦 Formats: {', '.join(repo['formats'])}")
        print()
    
    return repositories

def list_quantization_variants():
    """List common quantization variants for Qwen2.5 1.5B"""
    
    print("⚙️ Common Quantization Variants")
    print("=" * 60)
    
    quantizations = [
        {
            "name": "Q4_0",
            "size": "~900MB",
            "description": "4-bit quantization, good balance",
            "recommended": "General use"
        },
        {
            "name": "Q4_K_M",
            "size": "~950MB", 
            "description": "4-bit with improved accuracy",
            "recommended": "Better quality"
        },
        {
            "name": "Q5_0",
            "size": "~1.1GB",
            "description": "5-bit quantization, higher quality",
            "recommended": "High accuracy"
        },
        {
            "name": "Q5_K_M", 
            "size": "~1.2GB",
            "description": "5-bit with mixed precision",
            "recommended": "Best quality"
        },
        {
            "name": "Q8_0",
            "size": "~1.6GB",
            "description": "8-bit quantization, near original",
            "recommended": "Maximum quality"
        },
        {
            "name": "F16",
            "size": "~3.0GB",
            "description": "16-bit float, original quality",
            "recommended": "Research/benchmarking"
        }
    ]
    
    for quant in quantizations:
        print(f"🔧 {quant['name']:<8} | {quant['size']:<8} | {quant['description']}")
        print(f"   ✅ {quant['recommended']}")
        print()

def get_download_urls():
    """Get specific download URLs for different variants"""
    
    print("🔗 Direct Download URLs")
    print("=" * 60)
    
    urls = {
        "Q4_0": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_0.gguf",
        "Q4_K_M": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Q5_0": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q5_0.gguf",
        "Q5_K_M": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q5_k_m.gguf",
        "Q8_0": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf",
        "F16": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-f16.gguf"
    }
    
    # Alternative sources
    alt_urls = {
        "Q4_K_M (bartowski)": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
        "Q5_K_M (bartowski)": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q5_K_M.gguf",
        "Q8_0 (bartowski)": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q8_0.gguf"
    }
    
    print("📁 Official Qwen Repository:")
    for variant, url in urls.items():
        print(f"  {variant:<8}: {url}")
    
    print("\n📁 Alternative Sources (bartowski):")
    for variant, url in alt_urls.items():
        print(f"  {variant:<18}: {url}")
    
    return urls, alt_urls

def recommend_for_raspberry_pi5():
    """Recommend best variants for Raspberry Pi 5"""
    
    print("\n🎯 Raspberry Pi 5 Recommendations")
    print("=" * 60)
    
    recommendations = [
        {
            "rank": 1,
            "variant": "Q4_0",
            "reason": "Best balance of size/performance for Pi5",
            "use_case": "General purpose, production use"
        },
        {
            "rank": 2, 
            "variant": "Q4_K_M",
            "reason": "Slightly better quality, manageable size",
            "use_case": "High-quality responses needed"
        },
        {
            "rank": 3,
            "variant": "Q5_0", 
            "reason": "Good quality but larger size",
            "use_case": "If you have 8GB Pi5 and need quality"
        }
    ]
    
    print("🏆 Top Recommendations for Pi5:")
    for rec in recommendations:
        print(f"{rec['rank']}. {rec['variant']}")
        print(f"   💡 {rec['reason']}")
        print(f"   🎯 {rec['use_case']}")
        print()

def main():
    """Main function"""
    
    print("🤖 Qwen2.5 1.5B Instruct Model Variants")
    print("🔍 Comprehensive Guide for Raspberry Pi 5")
    print("=" * 60)
    print()
    
    # Search repositories
    repos = search_qwen_models()
    
    # List quantization options
    list_quantization_variants()
    
    # Get download URLs
    urls, alt_urls = get_download_urls()
    
    # Pi5 recommendations
    recommend_for_raspberry_pi5()
    
    print("💡 Quick Download Commands:")
    print("=" * 60)
    print("# For Q4_0 (recommended for Pi5):")
    print("./scripts/auto_retry_download.py /home/azazel/Azazel-Edge/models/qwen2.5-q4_0.gguf")
    print()
    print("# For Q4_K_M (current download):")
    print("./scripts/auto_retry_download.py /home/azazel/Azazel-Edge/models/qwen2.5-q4_k_m.gguf")
    print()
    print("# For Q5_0 (higher quality):")
    print("./scripts/auto_retry_download.py /home/azazel/Azazel-Edge/models/qwen2.5-q5_0.gguf")

if __name__ == "__main__":
    main()