# Escáner de Etiquetas — Instrucciones de instalación en Railway

## Archivos necesarios (todos en la misma carpeta)
- app.py
- escaner.html
- requirements.txt
- Procfile
- railway.json

---

## Paso 1 — Crear cuenta en Railway
1. Ve a https://railway.app
2. Haz clic en "Login" → "Login with Google"
3. Acepta los términos

---

## Paso 2 — Instalar Railway CLI (solo la primera vez)
1. Ve a https://docs.railway.app/guides/cli
2. Descarga el instalador para Windows
3. Instálalo y abre una ventana de CMD o PowerShell

---

## Paso 3 — Subir el proyecto
Abre CMD en la carpeta donde están los archivos y ejecuta:

```
railway login
railway init
railway up
```

Cuando te pregunte el nombre del proyecto escribe: escaner-etiquetas

---

## Paso 4 — Obtener la URL pública
1. Ve a https://railway.app y entra a tu proyecto
2. Haz clic en tu servicio → pestaña "Settings"
3. En "Networking" haz clic en "Generate Domain"
4. Te dará una URL como: https://escaner-etiquetas.up.railway.app

---

## Paso 5 — Usar el sistema
- Abre esa URL en cualquier navegador, desde cualquier dispositivo
- Los datos se guardan automáticamente en la nube
- El plan gratuito de Railway incluye 500 horas/mes (suficiente para uso diario)

---

## Notas importantes
- Si el servidor se "duerme" por inactividad, la primera vez puede tardar 5-10 segundos en cargar
- Los datos se guardan en una base de datos SQLite dentro del servidor
- Para hacer backup de los datos, descarga el reporte semanal regularmente

---

## ¿Problemas?
Contacta a soporte o vuelve a subir los archivos con: railway up
