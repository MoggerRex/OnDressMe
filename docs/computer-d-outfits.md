# Computadora D: worker de outfits

```powershell
Set-Location .\workers\outfits
py -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
python worker.py
```

Configura `REDIS_URL`, `BACKEND_URL` y, mas adelante, `OLLAMA_URL`/`OLLAMA_MODEL`. Ollama y Llama 3.1 8B no se descargan ni se ejecutan en esta etapa.
