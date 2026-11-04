# Computadora C: worker de avatar

```powershell
Set-Location .\workers\avatar
py -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
python worker.py
```

Este proceso solo prepara la cola y reporta que el procesamiento no esta implementado. SAM 3D Body, PyTorch y CUDA se integraran despues en este modulo.
