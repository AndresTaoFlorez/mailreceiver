# mailwindow

Two-service RPA: **API** (REST, Litestar) + **Agent** (Outlook browser automation, Playwright).

## Quick start

El proyecto usa **Litestar** (no FastAPI ni Django). El API arranca el Agent automáticamente
como subproceso, así que solo necesitas **una terminal**:

```bash
# 1. Activar el entorno virtual
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# 2. Arrancar (API en puerto 8000, Agent se inicia solo en 8001)
litestar --app api.app:app run --reload
```

> **No uses `uvicorn main:app`** directamente porque en Windows puede fallar con
> `Fatal error in launcher: Unable to create process`. Usa `litestar run`
> o `python -m uvicorn api.app:app --reload --port 8000`.

Si necesitas arrancar el Agent por separado (debug):

```bash
python -m agent --port 8001 --reload
```

Swagger UI: `http://localhost:8000/schema/swagger`

Docker:

```bash
docker compose up -d --build   # API en 8010, Agent en 8011
```

---

## Arquitectura general

```
┌──────────────────────┐          ┌──────────────────────────────────┐
│  API  (port 8000)    │──HTTP──> │  Agent  (port 8001)              │
│  Litestar            │          │  Litestar + Playwright           │
│                      │          │                                  │
│  POST /{app}/unread- │          │  POST /process                   │
│    conversations     │          │    └─ Pipeline de 5 steps        │
│                      │          │                                  │
│  Consulta PostgreSQL │          │  Guarda resultados en PostgreSQL │
│  y retorna paginado  │          │  via browser automation          │
└──────────────────────┘          └──────────────────────────────────┘
```

---

## Flujo completo paso a paso

Cuando el cliente llama `POST /tutela-en-linea/unread-conversations`:

### Fase 1: API recibe la petición

```
api/routes/tutela_en_linea.py:48
  → Verifica que el agent esté corriendo (api/agent_manager.py)
  → Hace POST http://localhost:8001/process con { application, folder, unread_only }
```

### Fase 2: Agent ejecuta el pipeline de scraping

El agent recibe la petición en `agent/routes/process.py` y ejecuta **dos pipelines secuenciales**:

```
agent/routes/process.py:25
  │
  ├─ Pipeline 1: LOGIN
  │   └─ Step 1: LoginStep (agent/browser/steps/step_01_login.py)
  │       ├─ Navega a https://outlook.office.com/mail/
  │       ├─ Si ya hay sesión activa → skip
  │       └─ Si no → ingresa email, password, confirma "Mantener sesión"
  │       └─ CRÍTICO: si falla, aborta todo
  │
  └─ Pipeline 2: SCRAPE (4 steps secuenciales)
      │
      ├─ Step 2: NavigateFolderStep (step_02_navigate_folder.py)
      │   ├─ Recarga Outlook para tener DOM limpio
      │   ├─ Espera el panel de carpetas [role="tree"]
      │   ├─ Click en la carpeta solicitada (ej: "Bandeja de entrada")
      │   ├─ Extrae conteo de no leídos del atributo title del treeitem
      │   │   Ejemplo: "Bandeja de entrada : Elementos 314 (92 no leídos)"
      │   │   Regex: \((\d+)\s+no\s+le  → 92
      │   ├─ Guarda en ctx.shared["expected_unread"] (puede ser None si falla)
      │   └─ CRÍTICO: si falla, aborta
      │
      ├─ Step 3: FilterUnreadStep (step_03_filter_unread.py)
      │   ├─ Si unread_only=False → skip
      │   ├─ Busca botón de filtro con múltiples selectores
      │   ├─ Click en botón → espera dropdown → click "No leído"
      │   ├─ Guarda screenshots de debug en storage/
      │   ├─ Guarda ctx.shared["filter_applied"] = True/False
      │   └─ NO CRÍTICO: si falla, el pipeline continúa SIN filtro
      │       ⚠️ Esto significa que Step 4 scrapeará TODOS los correos,
      │       no solo los no leídos
      │
      ├─ Step 4: ScrapeConversationsStep (step_04_scrape_conversations.py)
      │   ├─ Espera que aparezca [role="listbox"] (lista de correos)
      │   ├─ Lee aria-setsize del primer row para saber el total
      │   ├─ Detecta si Outlook usa Virtuoso scroller (virtual scroll)
      │   ├─ LOOP de scroll-parse (hasta 200 iteraciones):
      │   │   ├─ Lee todas las filas [role="option"] visibles en el DOM
      │   │   ├─ Para cada fila nueva (por id, no repetida):
      │   │   │   ├─ Ejecuta parse_email_card() → JS que extrae:
      │   │   │   │   conversation_id, subject, sender, sender_email, date
      │   │   │   ├─ Si subject="" Y sender="" → descarta silenciosamente
      │   │   │   └─ Si parse falla → log DEBUG (no visible por defecto)
      │   │   ├─ Scroll: si Virtuoso → JS scrollTop; si no → mouse.wheel(0,400)
      │   │   ├─ Espera scroll_wait_ms (1500ms) entre iteraciones
      │   │   └─ Detección de estancamiento: si 10 iteraciones sin nuevas filas → para
      │   ├─ Guarda ctx.shared["conversations"] = lista de dicts
      │   ├─ Timeout global: 300 segundos (5 min)
      │   └─ CRÍTICO: si falla, aborta
      │
      └─ Step 5: ExtractBodyStep (step_05_extract_body.py)
          ├─ Para CADA conversación recopilada en Step 4:
          │   ├─ Busca la fila en el DOM por [data-convid="..."]
          │   │   ⚠️ CUELLO DE BOTELLA: las filas pueden haber desaparecido
          │   │   del DOM virtual tras el scroll de Step 4
          │   ├─ Si no encuentra la fila → skip (log info)
          │   ├─ Click en la fila → espera 2s
          │   ├─ Espera que aparezca el panel de lectura (8s timeout)
          │   │   Selectores: div[role="document"], div[data-testid="message-body"],
          │   │   div.XbIp4, div[aria-label*="cuerpo"], div[aria-label*="body"]
          │   ├─ Si timeout → skip (log info)
          │   ├─ Cuenta mensajes en el hilo (JS)
          │   ├─ Si >1 mensaje: scroll 5 veces al fondo (800ms entre scrolls)
          │   │   para llegar al mensaje más antiguo (el primero de la conversación)
          │   ├─ Extrae innerHTML del ÚLTIMO div[role="document"] (= mensaje más antiguo)
          │   │   Con fallbacks: div.XbIp4, div[aria-label*="cuerpo"], div[dir="ltr"]
          │   └─ Guarda en conv["body"] = html_string
          ├─ Log final: "N/M conversations have body"
          └─ NO CRÍTICO: si falla parcial o totalmente, el pipeline continúa
              Las conversaciones se guardan en DB con body="" (vacío)
```

### Fase 3: Persistencia

```
agent/routes/process.py:62-68
  → Convierte cada dict a ScrapedEmail (Pydantic)
  → Upsert masivo en PostgreSQL:
      Si conversation_id ya existe → UPDATE (actualiza subject, body, etc.)
      Si es nuevo → INSERT
      Constraint: UNIQUE(conversation_id) previene duplicados
  → ⚠️ Si conversation_id="" → NULL != NULL en SQL, se inserta nuevo cada vez
```

### Fase 4: Respuesta al cliente

```
api/routes/tutela_en_linea.py:56-70
  → Consulta PostgreSQL filtrando por app + folder
  → Retorna respuesta paginada con new_saved (cuántos se guardaron esta vez)
```

---

## Cuellos de botella conocidos

### 1. Step 5: Filas desaparecen del DOM virtual (PRINCIPAL)

Outlook Web usa un **scroller virtual** (Virtuoso) que solo mantiene en el DOM las filas
visibles en pantalla (~15-20). Después de que Step 4 hace scroll hasta el fondo para
recopilar todas las conversaciones, las filas del inicio ya NO están en el DOM.

Cuando Step 5 intenta buscar `[data-convid="..."]` para cada conversación, la mayoría
retorna `count() == 0` y se salta. **Solo las últimas filas visibles en pantalla
tienen body extraído** — por eso de 10+ correos solo 2 tienen body.

**Solución necesaria:** Step 5 debe hacer scroll de vuelta al inicio y buscar
cada fila navegando el scroll virtual, no asumiendo que están en el DOM.

### 2. Step 3: Filtro falla silenciosamente

`FilterUnreadStep.is_critical = False`. Si el botón de filtro cambia de selector
(Outlook actualiza su UI frecuentemente), el filtro no se aplica pero el pipeline
continúa. Step 4 scrapeará TODOS los correos en vez de solo los no leídos.

### 3. Step 4: Detección de estancamiento agresiva

Si Outlook tarda más de `1500ms × 10 = 15s` en renderizar nuevas filas tras un scroll,
el scraper asume que no hay más y para. Puede detenerse con solo 20-30 correos
de 100+ disponibles.

### 4. Errores de parseo silenciosos

En Step 4, si `parse_email_card()` lanza excepción, se loguea a nivel DEBUG
(invisible en configuración normal). Correos con subject vacío Y sender vacío
se descartan sin aviso.

### 5. Timeout de lectura de body corto

Step 5 espera solo **8 segundos** para que cargue el panel de lectura.
Con hilos largos (muchos mensajes), Outlook puede tardar más → se salta.

---

## API endpoints

### Tutela en Linea

**`POST /tutela-en-linea/unread-conversations`**

```json
{ "folder": "Bandeja de entrada", "page": 1, "per_page": 20 }
```

### Justicia XXI Web

**`POST /justicia-xxi-web/unread-conversations`**

```json
{ "folder": "Bandeja de entrada", "page": 1, "per_page": 20 }
```

### Response (paginated)

```json
{
  "status": "ok",
  "page": 1,
  "per_page": 20,
  "total": 78,
  "pages": 4,
  "new_saved": 5,
  "conversations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "conversation_id": "AAQkADJm...",
      "subject": "SOLICITUD URGENTE",
      "sender": "Juzgado 01 Laboral",
      "sender_email": "j01lactociena@cendoj.ramajudicial.gov.co",
      "date": { "year": 2026, "month": 4, "day": 21, "hour": 19 },
      "body": "<div>HTML del primer mensaje...</div>",
      "created_at": "2026-04-21T19:11:00+00:00"
    }
  ]
}
```

- `new_saved`: conversaciones guardadas en este scrape (0 si todas eran duplicados)
- `total`: total en DB para este app+folder
- `pages`: páginas disponibles
- `body`: HTML del primer mensaje de la conversación (puede estar vacío si extracción falló)

### Config

**`GET /config`** — Leer configuración actual.

**`POST /config`** — Actualizar configuración (merge parcial).

**`GET /scraping-config`** — Parámetros de scraping.

**`POST /scraping-config`** — Actualizar parámetros de scraping.

### Agent control

**`GET /agent/status`** — Estado del agent.

**`POST /agent/start`** / **`POST /agent/stop`** / **`POST /agent/restart`**

---

## Database

PostgreSQL on `159.223.160.218:5432`, database `mailreceiver`.

Table `conversations`:
- `id` UUID PK
- `conversation_id` unique (previene duplicados)
- `app`, `folder`, `subject`, `sender`, `sender_email`
- `body` (HTML del primer mensaje, puede estar vacío)
- `year`, `month`, `day`, `hour`
- `created_at` timestamptz

---

## Configuration

Credentials in `.env` (never committed):

```
TUTELA_EN_LINEA_USER=...
TUTELA_EN_LINEA_PASSWORD=...
JUSTICIA_XXI_WEB_USER=...
JUSTICIA_XXI_WEB_PASSWORD=...
POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/mailreceiver
```

Scraping parameters in `storage/scraping_config.json`:

```json
{
  "max_scroll_iterations": 200,   // Máximo de iteraciones del loop de scroll
  "no_new_rows_limit": 10,        // Iteraciones sin nuevas filas antes de parar
  "scroll_wait_ms": 1500,         // Espera entre scrolls (ms)
  "scroll_amount_px": 600,        // Pixels de scroll con mouse wheel
  "max_conversations": 0,         // 0 = ilimitado
  "batch_size": 10,               // (sin uso actual)
  "listbox_timeout_ms": 15000,    // Timeout para que aparezca la lista
  "row_render_wait_ms": 2000,     // Espera para que se rendericen filas
  "filter_wait_ms": 3000          // Espera después de aplicar filtro
}
```

Browser config in `storage/config.json`.
