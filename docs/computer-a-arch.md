# Computadora A: Central Tony con Arch Linux

Estas instrucciones corresponden al equipo central `100.120.77.108`.

## 1. Instalar paquetes base

```bash
sudo pacman -Syu --needed python python-pip python-virtualenv redis
```

Docker es opcional si Redis se ejecuta como servicio nativo. Si se usara Docker:

```bash
sudo pacman -S --needed docker docker-compose
sudo systemctl enable --now docker
```

## 2. Preparar el backend

Desde la raiz clonada del repositorio:

```bash
cd on-dress-me/backend
python -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Edita `.env` y utiliza:

```env
API_HOST=0.0.0.0
API_PORT=8000
REDIS_URL=redis://100.120.77.108:6379/0
STORAGE_PATH=./storage
AVATAR_WORKER_URL=http://100.124.98.96:8101
OUTFIT_WORKER_URL=http://100.121.138.3:8102
CORS_ORIGINS=http://100.96.252.81:5173
```

Instala dependencias y arranca FastAPI:

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3. Iniciar Redis como servicio nativo

```bash
sudo systemctl enable --now redis
systemctl status redis
redis-cli ping
```

La respuesta esperada es `PONG`.

Redis debe escuchar en la interfaz Tailscale de la computadora central, no en Internet. Revisa la configuración:

```bash
sudoedit /etc/redis/redis.conf
```

Configura `bind` con la IP de Tailscale y loopback:

```text
bind 127.0.0.1 100.120.77.108
protected-mode yes
port 6379
```

Reinicia Redis:

```bash
sudo systemctl restart redis
ss -lntp | grep 6379
```

## 4. Firewall

Si utilizas `ufw`:

```bash
sudo ufw allow in on tailscale0 to any port 8000 proto tcp
sudo ufw allow in on tailscale0 from 100.124.98.96 to any port 6379 proto tcp
sudo ufw allow in on tailscale0 from 100.121.138.3 to any port 6379 proto tcp
sudo ufw enable
sudo ufw status
```

No abras el puerto `6379` en la interfaz pública.

## 5. Verificar desde Central

```bash
curl http://127.0.0.1:8000/health
redis-cli -h 127.0.0.1 ping
```

Desde Worker 2, `check_connection.py` debe mostrar `OK Redis` y `OK Backend`.
