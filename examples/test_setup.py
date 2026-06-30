#!/usr/bin/env python3
"""
Book Lab Environment Test Script
Tests that everything is set up correctly for 100% Ollama-based book labs
"""

import sys
import subprocess
import requests
from pathlib import Path


def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def check_python():
    print_header("Python Version Check")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    print(f"❌ Python {version.major}.{version.minor} - Need 3.10+")
    return False


def check_ollama():
    print_header("Ollama Check")
    try:
        subprocess.run(["ollama", "--version"], capture_output=True, timeout=5)
        print("✅ Ollama installed")
        
        # Check if running
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            print("✅ Ollama service running")
            
            # Check models used across the chapter flow.
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            required_models = {
                "llama3.2:3b": "Labs 1-3 baseline model",
                "deepseek-r1:8b": "Lab 4 agentic workflow model",
            }
            missing_models = []
            for model, label in required_models.items():
                if any(model in installed_model for installed_model in models):
                    print(f"✅ {model} installed ({label})")
                else:
                    print(f"❌ {model} not found ({label})")
                    missing_models.append(model)

            if missing_models:
                for model in missing_models:
                    print(f"   Run: ollama pull {model}")
                return False

            return True
        except:
            print("❌ Ollama not running")
            print("   Run: ollama serve")
            return False
    except:
        print("❌ Ollama not installed")
        print("   macOS: brew install ollama")
        return False


def check_labs():
    print_header("Lab Files Check")
    labs = [
        "labs/lab1-ollama/simple_ollama_test.py",
        "labs/lab3-chatbot/chatbot_v2_with_memory.py",
        "labs/lab4-agentic/agentic_network_bot_ollama.py"
    ]
    all_ok = True
    for lab in labs:
        if Path(lab).exists():
            print(f"✅ {lab}")
        else:
            print(f"❌ {lab} missing")
            all_ok = False
    return all_ok


def main():
    print("\n🤖 Building AI Agents for Network Operations - Setup Test".center(70))
    print("100% Free with Ollama - No API Keys!".center(70))
    
    checks = [check_python(), check_ollama(), check_labs()]
    
    print_header("Summary")
    if all(checks):
        print("✅ All checks passed! You're ready!")
        print("\nNext: python3 labs/lab1-ollama/simple_ollama_test.py\n")
        return 0
    else:
        print("❌ Some checks failed - fix issues above\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
