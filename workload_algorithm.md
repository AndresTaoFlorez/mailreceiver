# Workload Dispatch Algorithm
## Algoritmo de Asignación de Cargas — Documentación Conceptual Completa

> Versión 3.0 — Incluye tabla `applications`, `work_windows` con schedule por fecha concreta y franjas múltiples

---

## 1. Contexto del sistema · System Context

El sistema `mailwindow` extrae conversaciones de Outlook Web y las persiste en PostgreSQL. Una vez guardadas, el **Dispatcher** toma esas conversaciones y las asigna a especialistas según su nivel, disponibilidad y carga acumulada. Los tickets de Judit (creados vía TybaCase RPA) se relacionan con la asignación a través de la tabla `assignments`.

```
Outlook Web
    │
    ▼
[Scraper Agent]  ──────────────────────────────────────────────────────►  conversations
    │                                                                          │
    │                                                                          ▼
    │                                                               [Dispatcher / Assign]
    │                                                                          │
    │                                               ┌──────────────────────────┤
    │                                               ▼                          ▼
    │                                          especialist              work_windows
    │                                               │                    balance_snapshots
    │                                               └──────────────────────────┐
    │                                                                          ▼
    └──────────────────────────────────────────────────────────────►  assignments
                                                                           │
                                                                           ▼
                                                                        tickets
                                                                    (Judit / TybaCase)
```

---

## 2. Modelo de datos · Data Model

### Principio de referencia centralizada

Todas las tablas referencian `applications.code` como FK en lugar de repetir el string del aplicativo. Esto evita datos huérfanos, facilita renombrar un aplicativo y permite hacer consultas cruzadas sin joins innecesarios.

### 2.1 Tabla nueva: `applications`

Catálogo central de aplicativos. Todas las demás tablas apuntan aquí.

```sql
CREATE TABLE applications (
    code         VARCHAR(50) PRIMARY KEY,      -- "tutela_en_linea"
    name         VARCHAR(200) NOT NULL,         -- "Tutela en Línea"
    description  TEXT,
    levels       INTEGER[] NOT NULL DEFAULT '{1,2}',  -- niveles que maneja
    active       BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

> Usar `code` como PK (no UUID) hace las queries legibles sin joins. Ejemplo: `WHERE application_code = 'tutela_en_linea'` en lugar de `WHERE application_id = 'uuid...'`.

### 2.2 Tablas existentes (ajustadas)

| Tabla | Cambio |
|---|---|
| `conversations` | `app VARCHAR(50)` → `application_code VARCHAR(50) REFERENCES applications(code)` |
| `especialist` | `level INTEGER` se mantiene; si puede atender múltiples niveles, se agrega columna `levels INTEGER[]` |
| `folder_config` | `application VARCHAR(50)` → `application_code VARCHAR(50) REFERENCES applications(code)` |

### 2.3 Tablas nuevas

#### `tickets`
Registro completo de cada ticket creado en Judit vía TybaCase. Tiene vida propia porque acumula estado, respuestas y metadata de Judit independientemente de la asignación.

```sql
CREATE TABLE tickets (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code              VARCHAR(50),               -- número devuelto por Judit
    type              VARCHAR(100),              -- tipo/template de caso
    application_code  VARCHAR(50) NOT NULL REFERENCES applications(code),
    status            VARCHAR(50),               -- estado en Judit
    raw_response      JSONB,                     -- respuesta completa de TybaCase
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ
);
```

#### `assignments`
La tabla central que une todo: el correo, el especialista y el ticket de Judit.

```sql
CREATE TABLE assignments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id),
    especialist_code    VARCHAR(20) NOT NULL REFERENCES especialist(code),
    ticket_id           UUID REFERENCES tickets(id),      -- puede llegar después
    application_code    VARCHAR(50) NOT NULL REFERENCES applications(code),
    level               INTEGER NOT NULL,                  -- 1 o 2
    assigned_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    work_window_id      UUID REFERENCES work_windows(id)
);
```

> `ticket_id` puede ser NULL en el momento de la asignación y actualizarse cuando TybaCase devuelva el número de Judit.

#### `work_windows`
Define **cuándo** un analista atiende un aplicativo. En lugar de campos separados de días y horarios globales, usa un campo `schedule` tipo JSONB donde cada clave es una **fecha concreta** (no un día abstracto de la semana) y el valor es un array de franjas horarias para ese día.

Esto permite:
- Días con jornada parcial (solo mañana, solo tarde)
- Múltiples franjas en el mismo día (mañana + tarde con hueco al mediodía)
- Festivos simplemente ausentes del schedule
- Cambios por fecha sin afectar el resto de la ventana

```sql
CREATE TABLE work_windows (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    especialist_code    VARCHAR(20) NOT NULL REFERENCES especialist(code),
    application_code    VARCHAR(50) NOT NULL REFERENCES applications(code),
    load_percentage     INTEGER,             -- NULL = auto-distribuir equitativamente
    schedule            JSONB NOT NULL,      -- ver estructura abajo
    active              BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Estructura del campo `schedule`:**

```json
{
  "2026-04-28": [
    { "start": "08:00", "end": "12:00" }
  ],
  "2026-04-29": [
    { "start": "08:00", "end": "12:00" },
    { "start": "14:00", "end": "17:00" }
  ],
  "2026-04-30": [
    { "start": "13:00", "end": "17:00" }
  ],
  "2026-05-02": [
    { "start": "08:00", "end": "17:00" }
  ]
}
```

Cada clave es una fecha ISO `YYYY-MM-DD`. El valor es un array de objetos `{start, end}`. Si una fecha no aparece como clave, el analista no atiende ese aplicativo ese día. Los festivos simplemente no se incluyen.

El Pool Builder determina si un analista está activo en un momento dado consultando si la fecha actual existe en el `schedule` y si la hora actual cae dentro de alguna de sus franjas.

#### `balance_snapshots`  
El estado del balance acumulado de cada analista dentro de una ventana de trabajo. Es el "cerebro" del algoritmo progresivo.

```sql
CREATE TABLE balance_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    especialist_code    VARCHAR(20) NOT NULL REFERENCES especialist(code),
    application_code    VARCHAR(50) NOT NULL REFERENCES applications(code),
    work_window_id      UUID NOT NULL REFERENCES work_windows(id),
    cases_assigned      INTEGER NOT NULL DEFAULT 0,       -- cuántos lleva
    expected_cases      NUMERIC(10,2) NOT NULL DEFAULT 0, -- cuántos debería
    balance             NUMERIC(10,2) NOT NULL DEFAULT 0, -- deuda (negativo = le deben)
    last_reset_at       TIMESTAMPTZ,
    inherited_from      UUID REFERENCES balance_snapshots(id), -- herencia de ventana anterior
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 3. Conceptos fundamentales · Core Concepts

### Cumulative Balance (Balance Acumulado)
El número central del algoritmo. Por cada analista dentro de una ventana activa, el sistema mantiene la diferencia entre los casos que *debería* tener (según su porcentaje) y los que *realmente* tiene.

- **Balance negativo** → el sistema le "debe" casos → mayor prioridad
- **Balance positivo** → ya está por encima del promedio → menor prioridad
- **Balance cero** → perfectamente al día

### Expected Cases (Casos Esperados)
`total_cases_in_window × (load_percentage / 100)`

Si el total de casos del grupo es 30 y el analista tiene 20% de carga, debería tener 6 casos.

### Debt (Deuda)
`expected_cases - cases_assigned`

Una deuda positiva significa que el sistema le debe trabajo. Una deuda negativa significa que ya está adelantado.

### Progressive Drip (Goteo Progresivo)
Cuando llegan múltiples casos simultáneamente, el dispatcher los procesa **uno por uno**, recalculando el balance después de cada asignación. Nadie recibe un bloque de golpe.

### Pool Builder (Constructor de Pool)
Antes de cada asignación, el sistema construye dinámicamente el grupo de analistas elegibles:
1. Filtra por `level` del caso (según la carpeta: SOPORTE BÁSICO = nivel 1, SOPORTE AVANZADO = nivel 2)
2. Consulta las `work_windows` activas y verifica que la fecha y hora actuales estén cubiertas por alguna franja del `schedule` JSONB
3. Excluye analistas con `active = false`

### Overflow Rule (Regla de Desbordamiento)
Si el pool primario está vacío (todos ausentes o fuera de ventana), el sistema busca analistas habilitados para múltiples niveles. Si sigue vacío, el caso queda en cola de espera hasta el próximo evento de disponibilidad.

---

## 4. Relación carpeta → nivel

La carpeta de Outlook determina el nivel del caso:

| Carpeta en Outlook | Nivel | Pool elegible |
|---|---|---|
| `SOPORTE BÁSICO` | 1 | Especialistas nivel 1 (y multi-nivel si overflow) |
| `SOPORTE AVANZADO` | 2 | Especialistas nivel 2 (y multi-nivel si overflow) |

Esto ya funciona con la tabla `folder_config` existente. La carpeta se guarda en `conversations.folder` al momento del scrape.

---

## 5. Flujo completo de asignación · Full Assignment Flow

```
1. Trigger: llegan N conversaciones nuevas al buzón principal
      │
      ▼
2. Classifier
   Lee conversations.folder → determina level (1 o 2)
      │
      ▼
3. Pool Builder
   Para cada level:
   - Consulta work_windows con active = true
   - Verifica que la fecha de hoy exista en schedule JSONB
   - Verifica que la hora actual caiga dentro de alguna franja {start, end} de ese día
   - Obtiene balance_snapshots de cada analista elegible
      │
      ├── Pool vacío? → Overflow Rule → pool secundario
      │                                      │
      │                              Aún vacío? → Cola de espera
      ▼
4. Progressive Drip (caso por caso)
   Para cada conversación:
   a. Ordena el pool por balance (más negativo = mayor prioridad)
   b. En caso de empate → desempate por last_assignment_timestamp
   c. Asigna al primero del pool
   d. Actualiza balance_snapshot (cases_assigned++, recalcula balance)
   e. Inserta registro en assignments
      │
      ▼
5. State Update
   - balance_snapshots actualizado
   - assignments creado
   - ticket_id queda NULL hasta que TybaCase responda
      │
      ▼
6. Siguiente conversación → vuelve al paso 4
```

---

## 6. Módulo coordinador · Coordinator Module

El coordinador es la capa de configuración del sistema. Expone endpoints para gestionar todo lo que cambia semana a semana.

### 6.1 Gestión de ventanas de trabajo

**Crear ventana:**
```json
POST /coordinator/work-windows
{
  "especialist_code": "s20",
  "application_code": "tutela_en_linea",
  "load_percentage": 30,
  "schedule": {
    "2026-04-28": [{ "start": "08:00", "end": "12:00" }],
    "2026-04-29": [{ "start": "08:00", "end": "12:00" }, { "start": "14:00", "end": "17:00" }],
    "2026-04-30": [{ "start": "08:00", "end": "17:00" }],
    "2026-05-02": [{ "start": "13:00", "end": "17:00" }]
  }
}
```

**Modificar en tiempo real** — agregar un día o una franja nueva:
```json
PUT /coordinator/work-windows/{id}
{
  "schedule": {
    "2026-04-28": [{ "start": "08:00", "end": "12:00" }],
    "2026-04-29": [{ "start": "08:00", "end": "12:00" }, { "start": "14:00", "end": "17:00" }],
    "2026-04-30": [{ "start": "08:00", "end": "17:00" }],
    "2026-05-02": [{ "start": "13:00", "end": "17:00" }],
    "2026-05-04": [{ "start": "08:00", "end": "12:00" }]
  },
  "load_percentage": 25
}
```

Los cambios en `load_percentage` afectan **casos futuros únicamente**. Los ya asignados no se tocan.

**Cerrar ventana anticipadamente:**
```
POST /coordinator/work-windows/{id}/close
```

### 6.2 Gestión de balances

**Reiniciar balance de una ventana:**
```
POST /coordinator/balance/{work_window_id}/reset
```
Pone `cases_assigned = 0`, `expected_cases = 0`, `balance = 0`. Útil cuando el coordinador quiere empezar a contar desde cero a mitad de semana.

**Heredar balance al crear nueva ventana:**
```
POST /coordinator/work-windows
{
  ...
  "inherit_balance_from": "uuid-de-la-ventana-anterior"
}
```
El sistema copia el `balance` de la ventana anterior al `balance_snapshot` inicial de la nueva. Esto permite continuidad cuando la misma semana se extiende o cuando el analista sigue en el mismo aplicativo la siguiente semana.

### 6.3 Vista de estado actual

**Cargas actuales por aplicativo:**
```
GET /coordinator/load-status?application=tutela_en_linea
```
Devuelve para cada analista activo: `cases_assigned`, `expected_cases`, `balance`, `window_active`.

---

## 7. Ejemplo práctico 1 · Distribución con historial desbalanceado

**Ventana activa esta semana para `tutela_en_linea`:**

| Analista | Schedule | Load % | Cases actuales | Balance |
|---|---|---|---|---|
| Ana | 28-abr al 30-abr, mañanas | 30% | 10 | −5 (le deben 5) |
| Bruno | 28-abr al 02-may, día completo | 35% | 20 | +3 |
| Carla | 30-abr al 02-may, tardes | 35% | 20 | +3 |

**Llegan 9 conversaciones de nivel 1 (carpeta SOPORTE BÁSICO) el martes 29 de abril a las 10am.**

El Pool Builder busca en el `schedule` JSONB de cada ventana si `"2026-04-29"` existe y si `10:00` cae en alguna franja. Ana: `08:00–12:00` ✓. Bruno: `08:00–17:00` ✓. Carla: su schedule no tiene `"2026-04-29"` ✗. Pool = [Ana, Bruno].

El Progressive Drip procesa uno por uno:

| Ciclo | Pool ordenado por balance | Asignado a | Balance post-asignación |
|---|---|---|---|
| 1 | Ana (−5), Bruno (+3) | Ana | Ana: −4 |
| 2 | Ana (−4), Bruno (+3) | Ana | Ana: −3 |
| 3 | Ana (−3), Bruno (+3) | Ana | Ana: −2 |
| 4 | Ana (−2), Bruno (+3) | Ana | Ana: −1 |
| 5 | Ana (−1), Bruno (+3) | Ana | Ana: 0 |
| 6 | Ana (0), Bruno (+3) | Ana | Ana: +1 |
| 7 | Bruno (+3), Ana (+1) | Ana | Ana: +2 ← desempate timestamp |
| 8 | Bruno (+3), Ana (+2) | Ana | Ana: +3 |
| 9 | Empate (+3, +3) | Bruno | Bruno: +4 ← timestamp desempate |

**Resultado:** Ana recibió 8, Bruno 1. El sistema compensó la deuda histórica de Ana de forma progresiva, sin darle todo de golpe.

---

## 8. Ejemplo práctico 2 · Herencia de balance entre ventanas

**Fin de semana:** Ana termina su ventana con `balance = −3` (el sistema le debe 3 casos). El coordinador crea la ventana de la siguiente semana y elige **heredar** el balance.

```json
POST /coordinator/work-windows
{
  "especialist_code": "s20",
  "application_code": "tutela_en_linea",
  "load_percentage": 30,
  "schedule": {
    "2026-05-05": [{ "start": "08:00", "end": "12:00" }],
    "2026-05-06": [{ "start": "08:00", "end": "17:00" }],
    "2026-05-07": [{ "start": "08:00", "end": "17:00" }],
    "2026-05-08": [{ "start": "08:00", "end": "12:00" }]
  },
  "inherit_balance_from": "uuid-ventana-anterior"
}
```

El `balance_snapshot` inicial de la nueva ventana empieza en `−3` en lugar de `0`. Los primeros casos de la semana siguiente irán preferentemente a Ana hasta compensar.

Si el coordinador prefiere **empezar limpio**, simplemente no envía `inherit_balance_from` o hace un reset explícito.

---

## 9. Decisiones de diseño pendientes antes de implementar

| Decisión | Opciones |
|---|---|
| ¿Cómo se activa la asignación? | Manual (el coordinador pulsa "asignar"), automático al llegar conversaciones, o programado cada N minutos |
| ¿Qué pasa si llega una conversación fuera del horario de todas las ventanas? | Se encola hasta la próxima ventana activa, o se asigna al analista con menor carga sin importar horario |
| ¿El `load_percentage` de `especialist` coexiste con el de `work_windows`? | Recomendado: `work_windows.load_percentage` tiene precedencia cuando hay ventana activa; el de `especialist` es el fallback global |
| ¿Qué nivel tiene un analista que atiende ambos niveles? | Columna `levels INTEGER[]` en `especialist` (ej. `{1,2}`), o tabla separada `especialist_levels` |
| ¿Qué pasa si llega una conversación fuera de todas las franjas del schedule? | Se encola hasta la próxima franja activa, o se asigna al analista con menor balance sin importar horario |
| ¿Cómo se activa la asignación? | Manual (coordinador pulsa "asignar"), automático al llegar conversaciones, o programado cada N minutos |

---

## 10. Resumen de módulos a construir · Implementation Modules

| Módulo | Descripción |
|---|---|
| `domain/application_repository.py` | CRUD de la tabla `applications` |
| `domain/work_window_repository.py` | CRUD de ventanas de trabajo + consulta de franjas activas por fecha/hora |
| `domain/balance_repository.py` | Lectura y actualización de `balance_snapshots` |
| `domain/dispatcher.py` | Pool Builder + Progressive Drip + Overflow Rule |
| `api/routes/coordinator.py` | Endpoints del módulo coordinador (ventanas, balances, cargas) |
| `api/routes/assignments.py` | Endpoints de asignaciones (crear, consultar, actualizar `ticket_id`) |
| `api/routes/applications.py` | CRUD de aplicativos |
| Migration SQL | Tablas nuevas: `applications`, `assignments`, `work_windows`, `balance_snapshots`; refactor FK en `conversations`, `folder_config`, `especialist`, `tickets` |