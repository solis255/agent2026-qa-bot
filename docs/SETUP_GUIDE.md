# Workshop Setup Guide

Complete setup instructions for the AI Networking Workshop.

**Estimated time:** 15-20 minutes  
**Platforms:** macOS, Linux, Windows

---

## Prerequisites

### Required Software

1. **Python 3.10 or higher**
2. **Git**
3. **Ollama** (local LLM runtime)
4. **Text editor** (VS Code recommended)

### Optional

- **llama3.1:8b model** (Better quality, but slower)

**NOT Required:**
- ❌ API keys
- ❌ Docker Desktop  
- ❌ Cloud accounts
- ❌ Virtual machines

---

## macOS Setup

### 1. Install Homebrew (if not installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Install Python 3.10+

```bash
# Check current version
python3 --version

# If < 3.10, install latest
brew install python@3.11
```

### 3. Install Ollama

```bash
brew install ollama

# Start Ollama service
ollama serve &

# Pull required models
ollama pull llama3.2:3b
ollama pull llama3.1:8b  # Optional - larger, better quality
```

### 4. Install Git (if needed)

```bash
brew install git
```

### 5. Clone the Repository

```bash
cd ~/Documents  # Or your preferred location
git clone https://github.com/yourusername/ai-networking-workshop.git
cd ai-networking-workshop
```

### 6. Install Python Packages

```bash
pip3 install -r requirements.txt
```

### 7. (Optional) Set API Key

```bash
# Get free API key from https://console.anthropic.com/
# Add to ~/.zshrc for persistence
echo 'export ANTHROPIC_API_KEY=sk-ant-your-key-here' >> ~/.zshrc
source ~/.zshrc

# Or just for this session
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 8. Test Your Setup

```bash
python3 examples/test_setup.py
```

Expected output:
```
==================================================
AI Networking Workshop - Environment Test
==================================================
Checking Python version...
  ✅ Python 3.11.x
Checking Ollama...
  ✅ Ollama is installed
  ✅ llama3.2:3b model found
...
✅ All checks passed (5/5)
You're ready for the workshop! 🎉
```

---

## Linux Setup

### Ubuntu/Debian

```bash
# Update package list
sudo apt update

# Install Python 3.10+
sudo apt install python3.11 python3.11-pip git

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull llama3.2:3b

# Clone and setup
git clone https://github.com/yourusername/ai-networking-workshop.git
cd ai-networking-workshop
pip3 install -r requirements.txt

# Test
python3 examples/test_setup.py
```

### Red Hat/Fedora

```bash
sudo dnf install python3.11 python3-pip git
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b

git clone https://github.com/yourusername/ai-networking-workshop.git
cd ai-networking-workshop
pip3 install -r requirements.txt
python3 examples/test_setup.py
```

---

## Windows Setup

### 1. Install Python

Download from https://www.python.org/downloads/windows/
- **Important:** Check "Add Python to PATH" during installation

### 2. Install Git

Download from https://git-scm.com/download/win

### 3. Install Ollama

Download from https://ollama.com/download/windows

Open PowerShell:
```powershell
ollama pull llama3.2:3b
```

### 4. Clone and Setup

```powershell
cd C:\Users\YourUsername\Documents
git clone https://github.com/yourusername/ai-networking-workshop.git
cd ai-networking-workshop
pip install -r requirements.txt
```

### 5. Test

```powershell
python examples/test_setup.py
```

---

## API Key Setup (Optional)

### Get Anthropic API Key

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create a new key
5. Copy the key (starts with `sk-ant-`)

### Cost Estimate

- **Labs 1-2:** Free (uses Ollama)
- **Labs 3-4:** ~$1-5 (uses Claude API)
- **Alternative:** Use Ollama for all labs (free, slightly lower quality)

### Set the Key

**macOS/Linux:**
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Add to shell config for persistence
echo 'export ANTHROPIC_API_KEY=sk-ant-your-key-here' >> ~/.bashrc
```

**Windows:**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-your-key-here"

# For persistence, use System Environment Variables:
# Settings → System → About → Advanced system settings → Environment Variables
```

---

## Troubleshooting

### Ollama Connection Error

```bash
# Check if Ollama is running
ollama list

# If not, start it
ollama serve

# Test with simple prompt
ollama run llama3.2:3b "Hello"
```

### Python Import Errors

```bash
# Upgrade pip
pip3 install --upgrade pip

# Reinstall requirements
pip3 install -r requirements.txt --force-reinstall
```

### Permission Errors (macOS/Linux)

```bash
# Use user install
pip3 install -r requirements.txt --user
```

### Port Already in Use (Ollama)

```bash
# Kill existing Ollama process
pkill ollama

# Restart
ollama serve
```

---

## Verify Installation

### Quick Test Checklist

- [ ] Python 3.10+ installed
- [ ] Ollama installed and running
- [ ] llama3.2:3b model downloaded
- [ ] Repository cloned
- [ ] Python packages installed
- [ ] test_setup.py passes
- [ ] (Optional) API key set and working

### Test Each Lab

```bash
# Lab 1
python3 labs/lab1-ollama/simple_ollama_test.py

# Lab 2
python3 labs/lab2-prompts/prompt_engineering_race.py

# Lab 3 (requires API key)
python3 labs/lab3-chatbot/chatbot_v2_with_memory.py

# Lab 4 (requires API key)
python3 labs/lab4-agentic/agentic_network_bot.py
```

---

## Getting Help

**Before the Workshop:**
- GitHub Issues: Report setup problems
- Pre-workshop office hours: [Schedule TBD]
- Email: [contact email]

**During the Workshop:**
- Raise hand in Zoom
- Use chat for quick questions
- Breakout rooms for detailed help

---

## Next Steps

Once your environment is ready:

1. Review the [Complete Workshop Outline](docs/COMPLETE_OUTLINE.md)
2. Familiarize yourself with the repository structure
3. Optional: Read through lab code in advance
4. Join the workshop Discord/Slack (link will be shared)

---

**See you at the workshop!** 🚀
