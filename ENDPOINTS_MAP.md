# Mapa completo de endpoints para la interfaz

## 1. Applications (Catalogo de aplicativos)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /applications/` | Lista todos los aplicativos registrados (Tutela en Linea, Cierres Tyba, etc.) |
| `GET /applications/{code}` | Detalle de un aplicativo |
| `POST /applications/` | Crea un aplicativo nuevo |
| `PUT /applications/{code}` | Edita nombre, descripcion o desactiva un aplicativo |

**Vista sugerida:** Sidebar o tabs principales. Cada aplicativo es una "workspace".

---

## 2. Specialists (Gestion de analistas)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /especialists/` | Lista especialistas (filtrable por nivel y activos) |
| `POST /especialists/` | Crea uno o varios especialistas (array JSON). Valida codes unicos |
| `PUT /especialists/{code}` | Edita nombre, nivel, porcentaje de carga, prioridad, o desactiva |

**Vista sugerida:** Tabla/grid de analistas con columnas: codigo, nombre, nivel, % carga, prioridad, activo. Boton "Agregar" abre modal con formulario multi-row.

---

## 3. Per-Application endpoints (dentro de cada aplicativo)

Cada aplicativo (ej. `/cierres-tyba/`, `/tutela-en-linea/`) tiene estos endpoints identicos:

### 3a. Scraping (Obtener correos de Outlook)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `POST /{app}/unread-conversations` | Lanza el robot para scrape de correos de una carpeta. Devuelve resumen (nuevos guardados, total en BD) |

**Vista sugerida:** Boton "Scrape" por aplicativo con selector de carpeta y modo de extraccion (latest/oldest/full). Muestra resultado con badge de nuevos.

### 3b. Conversations (Correos almacenados)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /{app}/conversations` | Lista correos guardados. Filtrable por carpeta, IDs, campos vacios. Paginado. Campos pesados (body, date) son opt-in con `?include=` |

**Vista sugerida:** Tabla paginada de correos. Click en fila expande body (lazy load con `?include=body`). Filtros por carpeta (dropdown), busqueda por conversation_id.

### 3c. Folder Config (Que carpeta es nivel 1, cual es nivel 2)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /{app}/folder-config` | Lista mapeos carpeta -> nivel |
| `POST /{app}/folder-config` | Crea un mapeo (ej. "SOPORTE BASICO" = nivel 1) |
| `PUT /{app}/folder-config/{id}` | Cambia nombre de carpeta, nivel, o desactiva |
| `DELETE /{app}/folder-config/{id}` | Elimina un mapeo |

**Vista sugerida:** Tabla simple editable inline. Dos filas tipicas: nivel 1 -> SOPORTE BASICO, nivel 2 -> SOPORTE AVANZADO.

### 3d. Specialist Folders (Carpeta personal de cada analista en el app)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /{app}/specialists-folder` | Lista que carpeta de Outlook tiene cada especialista |
| `POST /{app}/specialists-folder` | Asigna carpetas a especialistas (array, upsert) |
| `PUT /{app}/specialists-folder/{id}` | Cambia la carpeta o desactiva |
| `DELETE /{app}/specialists-folder/{id}` | Elimina el mapeo |

**Vista sugerida:** Tabla: codigo especialista -> nombre carpeta. Editable inline.

### 3e. Assign Specialists — Weighted Deficit Dispatch (WDD)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `POST /{app}/assign-specialists/{level}` | Ejecuta el algoritmo WDD para el nivel dado. Distribuye correos sin asignar entre especialistas activos. Ver [`wdd/ALGORITHM.md`](wdd/ALGORITHM.md) |

**Vista sugerida:** Boton "Asignar Nivel N" por cada nivel configurado. Muestra resultado: cuantos asignados, a quien, cuantos en cola.

### 3f. Assignments (Consulta de asignaciones por app)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /{app}/assignments` | Lista asignaciones del aplicativo. Filtrable por especialista, nivel, presencia de ticket (`filter=!ticket`) |

**Vista sugerida:** Tabla con columnas: conversacion, especialista, nivel, fecha, ticket vinculado.

---

## 4. Coordinator (Ventanas de trabajo y balance)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /coordinator/work-windows` | Lista ventanas de trabajo (filtrable por app y especialista) |
| `POST /coordinator/work-windows` | Crea una ventana: especialista + app + horario JSON por fecha + % carga |
| `PUT /coordinator/work-windows/{id}` | Edita horario, % carga, o desactiva |
| `POST /coordinator/work-windows/{id}/close` | Cierra una ventana antes de tiempo |
| `GET /coordinator/balance/{window_id}` | Balance de asignaciones de una ventana (asignados vs esperados) |
| `POST /coordinator/balance/{window_id}/reset` | Resetea contadores a cero |
| `GET /coordinator/load-status?application_code=X` | Dashboard: cada especialista con casos asignados, esperados, balance, si esta activo |

**Vista sugerida (tipo Teams/Gantt):**
- Eje Y: especialistas
- Eje X: fechas/horas
- Bloques de color por cada time slot del schedule
- Color del bloque indica balance (verde = equilibrado, rojo = le deben casos, azul = tiene de mas)
- Click en bloque muestra detalle de la ventana
- Panel lateral con load-status en tiempo real (barras de progreso: asignados/esperados)

---

## 5. Dispatch (Consulta global de asignaciones)
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /dispatch/assignments` | Lista todas las asignaciones hechas (filtrable por app y especialista, paginado) |
| `PUT /dispatch/assignments/{id}/ticket` | Vincula un ticket de Judit/TybaCase a una asignacion |

---

## 6. Tickets
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `POST /tickets/create` | Envia conversaciones a TybaCase RPA para crear casos en Judit |
| `GET /tickets/` | Lista tickets creados (filtrable por app) |

---

## 7. Config & Agent
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /config` | Lee config del sistema (viewport, timeouts, paginacion) |
| `POST /config` | Modifica config del sistema |
| `GET /scraping-config` | Lee params del scraping (scroll, delays) |
| `POST /scraping-config` | Modifica params del scraping |
| `GET /agent/status` | Estado del robot (corriendo, PID) |
| `POST /agent/start` | Inicia el proceso del robot |
| `POST /agent/stop` | Detiene el proceso del robot |
| `POST /agent/restart` | Reinicia el proceso del robot |

**Vista sugerida:** Pagina de settings con toggles y un indicador de estado del agente (semaforo verde/rojo).

---

## 8. Utilidad
| Metodo | Endpoint | Que hace |
|--------|----------|----------|
| `GET /health` | Health check basico |
| `POST /debug` | Eco de headers, query y body recibidos (inspeccion) |

---

## Aplicativos registrados

| Path | Aplicativo |
|------|-----------|
| `/tutela-en-linea/` | Tutela en Linea |
| `/justicia-xxi-web/` | Justicia XXI Web |
| `/cierres-tyba/` | Cierres Tyba |
| `/demanda-en-linea/` | Demanda en Linea |
| `/firma-electronica/` | Firma Electronica |
