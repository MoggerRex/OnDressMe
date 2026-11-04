# Computadora D: worker de outfits

```powershell
Set-Location .\workers\outfits
py -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
python check_connection.py
```

Configura `REDIS_URL`, `BACKEND_URL` y, mas adelante, `OLLAMA_URL`/`OLLAMA_MODEL`. Ollama y Llama 3.1 8B no se descargan ni se ejecutan en esta etapa.

## Prueba de conectividad

En D, con la red Tailscale activa:

```powershell
python check_connection.py
```

Debe mostrar `OK Redis` y `OK Backend`. Para probar el recorrido completo:

1. En D, inicia el worker en una terminal:

   ```powershell
   python worker.py
   ```

2. En otra terminal de D, ejecuta:

   ```powershell
   python check_connection.py --e2e
   ```

El script crea un trabajo de prueba en A, A lo publica en `outfit_jobs`, D lo consume y D devuelve el estado a A. En esta fase el resultado esperado es `failed` con el mensaje de que la generación todavía no está implementada; eso confirma que la comunicación funcionó y que no se inventó un outfit.

Para instalar sin activar el entorno:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe check_connection.py --e2e
```

Si tu terminal ya esta ubicada en `workers`, usa solamente:

```powershell
Set-Location .\outfits
.\.venv\Scripts\python.exe worker.py
```
