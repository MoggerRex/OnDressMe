# Computadora A: backend central

```powershell
Set-Location .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Antes de arrancar, ajusta `.env` con el `REDIS_URL`, `STORAGE_PATH` y las URLs privadas de los workers. Redis puede iniciarse con `docker compose --env-file ..\infra\.env -f ..\infra\docker-compose.yml up -d redis`. No subas `.env` ni `storage/`.
