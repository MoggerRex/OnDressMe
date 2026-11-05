# Computadora A: backend central (`desktop-vs5lm9k`, Windows)

La IP Tailscale actual de esta computadora es `100.82.214.123`. Configura
Redis para escuchar en esa interfaz y permite los puertos 6379 y 8000 en el
firewall de Windows solo para la red privada de Tailscale.

```powershell
Set-Location .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Antes de arrancar, ajusta `.env` con el `REDIS_URL`, `STORAGE_PATH` y las URLs privadas de los workers. Copia `infra\.env.example` a `infra\.env` para conservar `REDIS_BIND_IP=100.82.214.123` y luego inicia Redis con `docker compose -f ..\infra\docker-compose.yml up -d redis`. No subas `.env` ni `storage/`.
