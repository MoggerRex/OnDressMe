# Computadora B: frontend

```powershell
Set-Location .\frontend
Copy-Item .env.example .env
npm install
npm run dev -- --host 0.0.0.0
```

Configura `VITE_API_BASE_URL` con la URL Tailscale del backend. El frontend no conoce Redis ni ejecuta modelos.
