#!/bin/bash
set -e

echo "========================================"
echo "Starting Ollama"
echo "========================================"

ollama serve &
OLLAMA_PID=$!

for i in $(seq 1 30); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "========================================"
echo "Installing qwen3:8b"
echo "========================================"

echo "ollama list | grep -q "qwen3:8b" || ollama pull qwen3:8b"

echo "========================================"
echo "Creating local models"
echo "========================================"
ollama list | grep -q "^qwen3:8b" || ollama create qwen3:8b -f /models/Qwen3_8b/Modelfile
ollama list | grep -q "^coder" || ollama create coder -f /models/Qwen_Code_Q4/Modelfile
ollama list | grep -q "^docs" || ollama create docs -f /models/Mistral_Q4/Modelfile
ollama list | grep -q "^reasoning" || ollama create reasoning -f /models/Qwen_Instruct_Q4/Modelfile
ollama list | grep -q "^embeded" || ollama create embeded -f /models/Embed_BGE_m3/Modelfile
echo "========================================"
echo "Installed models"
echo "========================================"

ollama list

echo "========================================"
echo "Mounted projects"
echo "========================================"

ls -la /workspace
ls -la /workspace/SynDemos || true
ls -la /workspace/workforce || true

cd /workspace/SynDemos

echo "========================================"
echo "Launching run.py"
echo "========================================"

python3 run.py

wait $OLLAMA_PID