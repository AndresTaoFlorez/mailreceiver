# Mailreceiver

Sistema RPA de dos servicios que extrae correos de Outlook Web mediante automatizacion de navegador y los distribuye entre especialistas usando un algoritmo de asignacion por deficit.

## Quick start

```bash
# Activar venv, luego:
litestar --app api.app:app run --reload
```

Un solo comando levanta ambos servicios. La API (puerto 8000) inicia automaticamente el Agent (puerto 8001) como subproceso.

Swagger UI: `http://localhost:8000/schema/swagger`

---

## Arquitectura

```
                          ┌──────────────────────────────────┐
  Cliente                 │           API (8000)             │
  (dashboard,  ─── HTTP ──│  Litestar REST                   │
   scheduler)             │  - Endpoints por aplicacion      │
                          │  - Dispatch (WDD)                │
                          │  - CRUD especialistas/ventanas   │
                          └────────────┬─────────────────────┘
                                       │ HTTP interno
                          ┌────────────▼─────────────────────┐
                          │          Agent (8001)             │
                          │  Litestar + Playwright            │
                          │  - Login en Outlook               │
                          │  - Scraping de carpetas           │
                          │  - Extraccion de cuerpo HTML      │
                          └────────────┬─────────────────────┘
                                       │
                          ┌────────────▼─────────────────────┐
                          │        PostgreSQL                 │
                          │  asyncpg + SQLAlchemy async       │
                          └──────────────────────────────────┘
```

La API es el punto de entrada unico. El Agent es un servicio interno que solo la API consume.

---

## Conceptos clave

### Aplicacion

Una aplicacion representa un buzon de Outlook independiente con sus propias credenciales, carpetas y equipo de especialistas. Cada aplicacion tiene endpoints identicos bajo su propio prefijo (`/{app}/...`). Se registran en la tabla `applications`.

### RPA: Flujo de scraping

El Agent ejecuta un pipeline de 5 pasos sobre Outlook Web (outlook.office.com):

```
POST /{app}/unread-conversations
  │
  ├─ Paso 1: Login
  │   Navega a Outlook, inicia sesion si no hay sesion activa.
  │   Critico: si falla, se aborta.
  │
  ├─ Paso 2: Navegar a carpeta
  │   Recarga Outlook, espera el panel de carpetas, hace click en la carpeta solicitada.
  │   Extrae el conteo de no leidos del badge de la carpeta.
  │   Critico: si falla, se aborta.
  │
  ├─ Paso 3: Filtrar no leidos
  │   Aplica el filtro "No leidos" en la UI de Outlook.
  │   No critico: si falla, el paso 4 extrae todos los correos.
  │
  ├─ Paso 4: Scraping de conversaciones
  │   Loop de scroll incremental sobre el listado virtual (Virtuoso).
  │   Outlook solo mantiene ~15-20 filas en el DOM, asi que el scraper
  │   hace scroll, parsea las filas visibles, y repite.
  │   Extrae: conversation_id, subject, sender, fecha, tags.
  │   Critico: si falla, se aborta.
  │
  └─ Paso 5: Extraccion de cuerpo
      Para cada conversacion del paso 4, hace click en la fila,
      espera el panel de lectura y extrae el HTML del cuerpo.
      No critico: si falla, la conversacion queda con body="".
```

Los resultados se persisten con upsert: si el `conversation_id` ya existe se actualiza, si es nuevo se inserta.

### Folder Config

Mapea carpetas de Outlook a niveles de soporte dentro de una aplicacion. Tabla `folder_config`.

```
"SOPORTE BASICO"    → nivel 1
"SOPORTE AVANZADO"  → nivel 2
```

El nivel determina a que pool de especialistas se enrutan los casos durante el dispatch. Un especialista de nivel 1 solo recibe casos de carpetas configuradas como nivel 1.

### Especialistas

Tabla `especialist`. Cada especialista tiene:

- **code**: identificador unico corto
- **level**: nivel de soporte que atiende (debe coincidir con folder_config)
- **load_percentage**: porcentaje fijo de carga (null = auto-distribuir equitativamente)
- **priority**: desempate cuando dos especialistas tienen el mismo deficit

### Specialist Folder

Mapea cada especialista a su carpeta personal de Outlook dentro de una aplicacion. Tabla `specialist_folders`. Se usa para saber donde mover o marcar correos una vez asignados.

### Work Windows (Ventanas de trabajo)

Una ventana de trabajo define **cuando** y **con que capacidad** un especialista esta disponible para recibir casos. Tabla `work_windows`.

```json
{
  "especialist_code": "spec01",
  "application_code": "mi_app",
  "load_percentage": 40,
  "schedule": {
    "2026-04-28": [{"start": "08:00", "end": "12:00"}],
    "2026-04-29": [{"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "17:00"}]
  }
}
```

- Dias no listados = especialista no disponible
- El `load_percentage` de la ventana puede sobreescribir el del especialista
- Solo los especialistas con ventana activa **en el momento del dispatch** entran al pool
- Cada ventana acumula su propio snapshot de deficit (`balance_snapshots`)
- Al crear una ventana nueva se puede heredar el deficit de una anterior (`inherit_balance_from`)

### WDD: Weighted Deficit Dispatch

Algoritmo de asignacion que distribuye casos entre los especialistas disponibles. Especificacion completa en [`wdd/ALGORITHM.md`](wdd/ALGORITHM.md).

**Idea central**: en cada ronda, sin importar cuantos casos lleguen, el sistema calcula la distribucion ideal y prioriza a quienes mas se han alejado de ella.

```
deficit(i) = ideal(i) - recibido(i)

ideal(i) = total_casos × (load_percentage(i) / 100)
```

- **Deficit positivo** → el sistema le debe casos al especialista (prioridad alta)
- **Deficit negativo** → el especialista esta adelantado (prioridad baja)

El algoritmo asigna caso por caso, recalculando el deficit despues de cada asignacion. Esto garantiza equidad incluso con lotes de tamano impredecible.

**Escalaciones**: cuando un especialista escala un caso a otro, el deficit se ajusta manualmente para mantener la equidad en rondas futuras.

Implementacion: `wdd/engine.py` (standalone, puro Python) + `domain/dispatcher.py` (adapter a DB).

### Assignments (Asignaciones)

Tabla `assignments`. Registro de que conversacion fue asignada a que especialista, en que nivel, y a traves de que ventana de trabajo.

```
conversacion X  →  especialista spec01  →  nivel 1  →  ventana abc-123
```

Las asignaciones son el resultado del dispatch. Una conversacion solo se asigna una vez (el dispatcher filtra las ya asignadas). El endpoint `GET /{app}/assignments` permite filtrar por:

- `specialist` / `!specialist` — tiene o no especialista
- `ticket` / `!ticket` — tiene o no ticket vinculado

### Tickets

Tabla `tickets`. Representa un ticket externo (ej. sistema de gestion) vinculado a una asignacion. Se crean despues de la asignacion y se vinculan via `PUT /dispatch/assignments/{id}/ticket`.

El flujo completo es: **scraping → asignacion → creacion de ticket**.

---

## Base de datos

PostgreSQL con asyncpg + SQLAlchemy async. Modelos en `domain/models.py`.

| Tabla | Proposito |
|-------|-----------|
| `applications` | Catalogo de aplicaciones. PK = `code` |
| `conversations` | Correos extraidos. `UNIQUE(conversation_id)` previene duplicados |
| `especialist` | Especialistas. `UNIQUE(code)` |
| `folder_config` | Carpeta de Outlook → nivel de soporte por aplicacion |
| `specialist_folders` | Especialista → carpeta personal de Outlook por aplicacion |
| `work_windows` | Disponibilidad: schedule JSONB por fecha + slots horarios |
| `balance_snapshots` | Contadores de deficit por especialista por ventana |
| `assignments` | Conversacion → especialista, creadas por el dispatcher |
| `tickets` | Referencias a tickets externos |

Migraciones en `migrations/`, se ejecutan manualmente.

---

## Endpoints

Documentacion completa con descripciones de campos en Swagger UI. Referencia de endpoints en `ENDPOINTS_MAP.md`.

### Globales

| Seccion | Proposito |
|---------|-----------|
| Applications | CRUD de aplicaciones |
| Specialists | CRUD de especialistas |
| Coordinator | Ventanas de trabajo, snapshots de deficit, dashboard de carga |
| Dispatch | Consultar asignaciones, vincular tickets |
| Tickets | Crear y listar tickets |
| Config | Configuracion de scraping y navegador en runtime |
| Agent | Control del agente de automatizacion |

### Por aplicacion

| Endpoint | Proposito |
|----------|-----------|
| `POST /{app}/unread-conversations` | Ejecutar scraping de Outlook |
| `GET /{app}/conversations` | Consultar conversaciones (filtrable, paginado) |
| `/{app}/folder-config` | CRUD de mapeo carpeta → nivel |
| `/{app}/specialists-folder` | CRUD de mapeo especialista → carpeta personal |
| `POST /{app}/assign-specialists/{level}` | Ejecutar dispatch WDD para un nivel |
| `GET /{app}/assignments` | Consultar asignaciones con filtros |

---

## Configuracion

| Archivo | Contenido |
|---------|-----------|
| `.env` | Credenciales de Outlook por aplicacion, URL de PostgreSQL |
| `storage/config.json` | Configuracion del navegador (viewport, headless, user agent) |
| `storage/scraping_config.json` | Parametros del loop de scroll, timeouts |

---

## Problemas conocidos

- **Virtual scroll**: Outlook solo mantiene ~15-20 filas en el DOM. Filas que salen del viewport durante el scraping pueden perderse en la extraccion de cuerpo.
- **Filtro no critico**: si Outlook cambia el selector del boton de filtro, el scraping continua sin filtrar (extrae todos los correos, no solo no leidos).
- **Dark mode**: el HTML extraido puede tener colores de texto blancos y atributos `data-ogsc` de Outlook en modo oscuro.
