# Guía de integración para el frontend

Todo lo que hace falta para construir la interfaz contra esta API, incluido lo
que el esquema OpenAPI no te puede decir: en qué orden van las llamadas, qué
cabecera va en cada una y dónde están las trampas.

- **Base URL**: `http://localhost:8000` en desarrollo
- **Prefijo**: todos los endpoints de negocio cuelgan de `/api/v1`
- **Documentación viva**: `GET /docs` (Swagger UI) y `GET /api/v1/openapi.json`
- **Tipos**: genera el cliente desde el esquema en vez de escribirlo a mano

```bash
npx openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/api/schema.d.ts
```

Este documento explica el *cómo*; el esquema es la fuente de verdad del *qué*.

---

## 1. Los dos ejes: quién eres y en qué empresa estás

Es el concepto que hay que entender antes de escribir la primera pantalla.

```text
Authorization: Bearer <access_token>   →  quién eres          (siempre)
X-Company-ID: <uuid>                   →  en qué empresa      (casi siempre)
```

Un usuario puede pertenecer a **varias empresas**. El token dice quién es, no
dónde está trabajando. El backend nunca confía en la cabecera por sí sola:
valida que existas como miembro activo de esa empresa antes de dejarte hacer
nada, en cada petición.

Solo tres grupos de endpoints **no** llevan `X-Company-ID`:

| Grupo | Por qué |
|---|---|
| `/api/v1/auth/*` | Todavía no hay empresa elegida |
| `GET`/`POST /api/v1/companies` | Es la lista para elegir, y la creación |
| `/api/v1/admin/*` | Son de plataforma; la empresa va en la ruta cuando aplica |

Todo lo demás la exige. Si falta:

```json
{"error": {"code": "COMPANY_REQUIRED",
           "message": "X-Company-ID header is required for this endpoint",
           "details": {}}}
```

Ponla en el cliente HTTP una vez, no en cada llamada.

---

## 2. Autenticación

### Registro

`POST /api/v1/auth/register`

```json
{"email": "ana@example.com", "password": "una-clave-larga",
 "first_name": "Ana", "last_name": "Gómez", "company_name": "Ferretería Demo"}
```

`company_name` es opcional. Si va, se crea la empresa y quien se registra queda
como `OWNER`. Si no va, la cuenta existe pero sin ninguna empresa — es el caso
de alguien a quien van a invitar.

```json
{"user": {"id": "0f85...", "email": "ana@example.com", "first_name": "Ana",
          "last_name": "Gómez", "is_active": true, "created_at": "..."},
 "company_id": "3d05..."}
```

### Login

`POST /api/v1/auth/login` → `{"email", "password"}`

```json
{"access_token": "eyJ...", "refresh_token": "eyJ...",
 "token_type": "bearer", "expires_in": 900}
```

**El access token dura 15 minutos** (`expires_in` en segundos). El refresh dura
14 días. Necesitas un interceptor de refresco desde el primer día; no es algo
que se deje para después.

### Refresco

`POST /api/v1/auth/refresh` → `{"refresh_token": "..."}` → un par nuevo.

Devuelve **ambos** tokens: guarda los dos. Errores posibles:

| Código | Qué hacer |
|---|---|
| `TOKEN_EXPIRED` | Cerrar sesión y mandar al login |
| `INVALID_TOKEN` | Igual |
| `INACTIVE_USER` | La cuenta fue desactivada: login con mensaje |

### Sesión actual

`GET /api/v1/auth/me` → el usuario del token. Úsalo al arrancar la app para
saber si la sesión sigue viva.

### Logout

`POST /api/v1/auth/logout` → `204`.

**Es sin estado**: el backend no revoca nada todavía. El cliente borra sus
tokens. Un access token robado sigue sirviendo hasta que expira (15 min). La
revocación real (denylist de `jti` en Redis) está pendiente en el backend.

### Dónde guardar los tokens

`localStorage` es simple y vulnerable a XSS. Si la app maneja dinero — y esta lo
hace — vale la pena el esfuerzo de guardar el access token en memoria y el
refresh en una cookie `httpOnly`, lo que requiere un pequeño proxy en el
frontend. Decídelo antes de tener pantallas construidas encima.

---

## 3. Elegir empresa

Después del login, antes de cualquier otra cosa:

```http
GET /api/v1/companies
Authorization: Bearer <token>
```

```json
[{"company_id": "3d05...", "company_name": "Demo", "role": "OWNER", "is_active": true}]
```

- **Una sola** → entra directo, guarda el `company_id`.
- **Varias** → selector. Guarda la elección (`localStorage`) y respétala al
  volver.
- **Ninguna** → pantalla de "todavía no perteneces a ninguna empresa". Puede
  crear una con `POST /api/v1/companies` o esperar una invitación.

Cambiar de empresa es cambiar la cabecera y **recargar todo el estado**: no hay
nada compartido entre empresas y mezclar datos de dos es el bug más caro que
puedes introducir. Lo más seguro es limpiar la caché del cliente de datos
(React Query: `queryClient.clear()`) al cambiar.

### Si la empresa queda suspendida

El operador de la plataforma puede suspender una empresa. A partir de la
siguiente petición de sus miembros:

```json
{"error": {"code": "INVALID_COMPANY", "message": "Company is suspended", "details": {}}}
```

Trátalo como un estado de la aplicación, no como un error suelto: pantalla
explicativa y vuelta al selector de empresa.

---

## 4. Permisos: cómo construir la UI

Los roles viven en la base de datos. Cada empresa tiene cuatro del sistema
(`OWNER`, `ADMIN`, `SELLER`, `INVENTORY_MANAGER`) y puede crear los suyos.

**Los permisos se leen en cada petición**, así que un cambio de rol surte efecto
sin que el usuario vuelva a iniciar sesión. Tu UI debería reflejar eso: no
guardes los permisos en el token (no están ahí) ni los caches para siempre.

### Saber qué puede hacer el usuario actual

```http
GET /api/v1/roles          # los roles de esta empresa, con sus permisos
GET /api/v1/companies      # tu rol en cada empresa (el campo "role")
```

Cruza tu `role` de `/companies` con el rol correspondiente de `/roles` para
obtener tu lista de permisos. `OWNER` tiene el comodín `"*"`:

```ts
const can = (permission: string) =>
  myPermissions.includes("*") || myPermissions.includes(permission);
```

### Regla de oro

Esconder un botón es cortesía, no seguridad. El backend rechaza igual:

```json
{"error": {"code": "INSUFFICIENT_ROLE",
           "message": "Role SELLER cannot perform 'products.create'",
           "details": {"required_permission": "products.create", "role": "SELLER"}}}
```

`details.required_permission` viene siempre: úsalo para un mensaje útil
("necesitas el permiso *Crear productos*") en vez de un "no autorizado" seco.

### Catálogo de permisos

`GET /api/v1/roles/permissions` devuelve los 34 permisos con etiqueta y módulo
— es lo que necesitas para construir la pantalla de edición de roles.

| Módulo | Permisos |
|---|---|
| system | `*` |
| company | `company.read`, `company.update`, `members.read`, `members.manage`, `roles.read`, `roles.manage` |
| catalog | `categories.read`, `categories.write`, `products.read`, `products.create`, `products.update`, `products.delete` |
| inventory | `warehouses.read`, `warehouses.write`, `inventory.read`, `inventory.adjust`, `inventory.transfer` |
| partners | `customers.read`, `customers.write`, `suppliers.read`, `suppliers.write` |
| sales | `sales.read`, `sales.create`, `sales.cancel` |
| purchases | `purchases.read`, `purchases.create`, `purchases.cancel` |
| imports | `imports.read`, `imports.run` |
| files | `files.read`, `files.write` |
| reports | `reports.read` |
| audit | `audit.read` |

---

## 5. Convenciones de la API

### Los decimales son strings. Siempre.

```json
{"sale_price": "15000.0000", "quantity": "2.0000", "total": "30000.0000"}
```

Cuatro decimales, como texto. **No uses `parseFloat` para dinero.** Usa
`decimal.js`, `dinero.js` o `BigInt` sobre centavos. Un `0.1 + 0.2` en una
factura es un problema real, no teórico.

Al **enviar** también manda strings: `{"cost_price": "8000.50"}`. El backend
acepta número o string, pero un `Number` grande en JavaScript ya perdió
precisión antes de salir de tu código.

### Fechas

ISO 8601 en UTC con `Z`: `"2026-09-20T23:05:45.130642Z"`. Conviértelas a la zona
del usuario para mostrar; manda UTC de vuelta.

### Paginación

Toda lista larga tiene la misma forma:

```json
{"items": [...], "total": 42, "page": 1, "size": 20, "pages": 3}
```

Parámetros: `?page=1&size=20`. **`size` máximo 100.** Las listas cortas y
acotadas (categorías, bodegas, roles) devuelven un array pelado, sin envoltorio.

### Identificadores

Todos UUID v4 en texto. No asumas orden ni los uses como número.

### `X-Request-ID`

Cada respuesta trae uno. Si el usuario reporta un problema, ese id aparece en
los logs del backend. Muéstralo en tus pantallas de error — te ahorra horas.

```
x-request-id: 58c6442f-f636-4145-90c8-1f8ec1c540ff
```

También puedes mandarlo tú y el backend lo respeta, lo que permite correlacionar
una acción del usuario con varias llamadas.

---

## 6. Errores

**Todos** los errores de la API tienen la misma envoltura:

```json
{"error": {"code": "DUPLICATE_SKU",
           "message": "A product with that SKU already exists in this company",
           "details": {}}}
```

Nunca parsees el `message` (puede cambiar). Ramifica por `code`.

### Errores de validación de esquema

`VALIDATION_ERROR` (422) trae los campos, y `location` te dice exactamente
dónde, para pintar el error junto al input:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed",
  "details": {"fields": [
    {"location": ["body", "sku"], "message": "String should have at least 1 character",
     "type": "string_too_short"}]}}}
```

### Manejo por código HTTP

| HTTP | Qué significa | Qué hace la UI |
|---|---|---|
| 401 | Token inválido o expirado | Refrescar; si falla, login |
| 403 `INSUFFICIENT_ROLE` | Le falta un permiso | Mensaje con `required_permission` |
| 403 `INVALID_MEMBERSHIP` | No pertenece a esa empresa | Selector de empresa |
| 403 `INVALID_COMPANY` | Empresa suspendida/inactiva | Pantalla de empresa bloqueada |
| 403 `NOT_PLATFORM_ADMIN` | Ruta de plataforma | Ocultar la consola de admin |
| 404 | No existe **o no es de esta empresa** | "No encontrado" |
| 409 | Choque de unicidad | Error junto al campo (SKU, documento, nombre) |
| 422 | Regla de negocio o validación | Mensaje específico |
| 503 | Dependencia caída | Reintentar |

Un detalle importante del 404: si pides el producto de **otra** empresa, la
respuesta es `404`, no `403`. Es deliberado — un 403 confirmaría que el
identificador existe. Para tu UI es simplemente "no existe".

### Errores con contexto útil

Varios traen datos que vale la pena mostrar:

```json
{"error": {"code": "INSUFFICIENT_STOCK", "message": "Not enough stock for this operation",
  "details": {"product_id": "e3de...", "warehouse_id": "386f...",
              "available": "8.0000", "requested": "999.0000"}}}
```

Con eso puedes decir "solo quedan 8 unidades" en vez de "error".

### Catálogo

Hay ~75 códigos. Los que más vas a tocar:

**Auth**: `INVALID_CREDENTIALS`, `INACTIVE_USER`, `TOKEN_EXPIRED`, `INVALID_TOKEN`,
`EMAIL_ALREADY_REGISTERED`
**Tenant**: `COMPANY_REQUIRED`, `INVALID_MEMBERSHIP`, `INVALID_COMPANY`,
`INSUFFICIENT_ROLE`
**Catálogo**: `DUPLICATE_SKU`, `DUPLICATE_BARCODE`, `DUPLICATE_CATEGORY_NAME`,
`PRODUCT_NOT_FOUND`, `CATEGORY_NOT_FOUND`
**Inventario**: `INSUFFICIENT_STOCK`, `SAME_WAREHOUSE_TRANSFER`,
`INACTIVE_WAREHOUSE`, `WAREHOUSE_NOT_FOUND`
**Ventas/compras**: `EMPTY_SALE`, `INVALID_SALE_TRANSITION`, `INACTIVE_CUSTOMER`,
`INACTIVE_PRODUCT`, `INVALID_PURCHASE_TRANSITION`
**Roles**: `SYSTEM_ROLE_IMMUTABLE`, `DUPLICATE_ROLE_CODE`, `ROLE_IN_USE`,
`UNKNOWN_PERMISSION`, `CANNOT_GRANT_WILDCARD`, `CANNOT_CHANGE_OWN_ROLE`
**Archivos**: `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `EMPTY_FILE`,
`OWNER_ID_REQUIRED`
**Importación**: `MISSING_REQUIRED_COLUMNS`, `UNKNOWN_TARGET_FIELD`,
`IMPORT_NOT_OPEN`, `UNREADABLE_FILE`, `NO_HEADER_ROW`, `IMPORT_TOO_LARGE`

La lista completa sale de `grep -rn 'code = "' app/` en el backend.

---

## 7. Enumeraciones

Valores exactos, tal cual viajan:

| Enum | Valores |
|---|---|
| `CompanyStatus` | `ACTIVE`, `SUSPENDED`, `INACTIVE` |
| `DocumentType` | `NIT`, `CC`, `CE`, `PASSPORT`, `RUT`, `OTHER` |
| `SaleStatus` | `DRAFT`, `COMPLETED`, `CANCELLED`, `REFUNDED` |
| `PurchaseStatus` | `DRAFT`, `COMPLETED`, `CANCELLED` |
| `MovementType` | `PURCHASE`, `SALE`, `RETURN`, `ADJUSTMENT`, `TRANSFER_IN`, `TRANSFER_OUT` |
| `ReferenceType` | `SALE`, `PURCHASE`, `TRANSFER`, `MANUAL` |
| `SubscriptionStatus` | `TRIALING`, `ACTIVE`, `PAST_DUE`, `CANCELLED` |
| `NotificationType` | `LOW_STOCK`, `SUBSCRIPTION`, `REPORT_READY`, `SYSTEM` |
| `FileOwnerType` | `PRODUCT`, `COMPANY`, `SALE`, `PURCHASE`, `IMPORT`, `EXPORT`, `REPORT` |
| `ImportEntity` | `CATEGORIES`, `PRODUCTS`, `WAREHOUSES`, `CUSTOMERS`, `SUPPLIERS`, `STOCK` |
| `ImportStatus` | `ANALYZED`, `VALIDATED`, `COMPLETED`, `FAILED`, `CANCELLED` |

Tradúcelos en el frontend; la API habla en códigos.

---

## 8. Flujos completos

### 8.1 Arranque de la aplicación

```text
¿hay tokens? ──no──> /login
      │sí
      ▼
GET /auth/me ──401──> refrescar ──falla──> /login
      │ok
      ▼
GET /companies
      ├─ 0 empresas ──> pantalla "sin empresa"
      ├─ 1 empresa  ──> entrar
      └─ N empresas ──> selector (recordar la última)
      ▼
GET /roles  →  permisos del usuario  →  render del menú
```

### 8.2 Venta (punto de venta)

La forma corta hace todo en **una** llamada atómica:

```http
POST /api/v1/sales
{
  "warehouse_id": "...",
  "customer_id": "...",          // opcional
  "complete": true,
  "items": [{"product_id": "...", "quantity": "2"}]
}
```

- Si omites `unit_price`, se usa el `sale_price` vigente del producto. Mándalo
  solo cuando haya un precio negociado.
- `complete: true` bloquea el stock, valida disponibilidad, crea la venta, sus
  líneas y los movimientos, y descuenta — **todo en una transacción**. Si una
  línea se queda sin stock, **la venta entera se revierte**. No existe el estado
  a medias, así que no lo modeles en la UI.
- Los totales los calcula el backend desde las líneas. Lo que mandes como total
  se ignora: no se puede cobrar algo distinto a lo que suman los ítems.

La forma larga (`complete: false`) crea un `DRAFT` que no toca stock, para
cotizaciones o pedidos en curso. Después:

```text
DRAFT ──POST /sales/{id}/complete──> COMPLETED ──/cancel──> CANCELLED  (devuelve stock)
  │                                      │
  │                                      └──/refund──> REFUNDED        (devuelve stock)
  └──/cancel──> CANCELLED                                              (no tocó stock)
```

`INVALID_SALE_TRANSITION` es la respuesta a un cambio de estado imposible;
deshabilita los botones según `status` para no llegar ahí.

### 8.3 Compra (recepción de mercancía)

Espejo de la venta, pero suma stock. Las líneas llevan `unit_cost` (obligatorio,
no hay valor por defecto):

```http
POST /api/v1/purchases
{"warehouse_id": "...", "supplier_id": "...", "complete": true,
 "items": [{"product_id": "...", "quantity": "10", "unit_cost": "8000"}]}
```

Al completar puedes refrescar el costo de los productos con lo que realmente se
pagó: `POST /purchases/{id}/complete?update_product_costs=true`. Es **opt-in** a
propósito — muchos negocios prefieren costo promedio ponderado, y eso es una
decisión del negocio.

### 8.4 Inventario

```http
GET  /api/v1/inventory/stock?product_id=&warehouse_id=&only_non_zero=true
GET  /api/v1/inventory/movements?product_id=&warehouse_id=&reference_id=
POST /api/v1/inventory/adjustments   {"product_id","warehouse_id","quantity_delta":"-3","notes":"Rotura"}
POST /api/v1/inventory/transfers     {"product_id","source_warehouse_id","destination_warehouse_id","quantity":"5"}
```

`quantity_delta` es **con signo**: negativo descuenta, positivo suma. No es la
cantidad final, es la diferencia.

Los movimientos son el historial auditable. `reference_id` apunta a la venta o
compra que lo originó, así que puedes enlazar desde el movimiento al documento.

### 8.5 Importación masiva (4 pasos)

El flujo más complejo, y el que más UI necesita. Es de **dos fases a propósito**:
nada se adivina en silencio.

```text
1. GET  /imports/schemas              campos destino de cada entidad
   GET  /imports/templates/{entity}   plantilla .xlsx (el camino fácil)

2. POST /imports                      multipart: file + entity
                                      → propone mapeo, muestra vista previa
                                      → NO escribe nada

3. PATCH /imports/{id}/mapping        el usuario corrige columnas

4. POST /imports/{id}/validate        simulación: ejecuta y revierte
   POST /imports/{id}/run             carga de verdad
```

**Paso 2** devuelve todo lo que necesita la pantalla de mapeo:

```json
{
  "job": {"id": "...", "status": "ANALYZED", "...": "..."},
  "total_rows": 3,
  "columns": [
    {"source": "Referencia", "suggested_target": "sku", "confidence": 1.0,
     "reason": "exact", "needs_review": false, "samples": ["mar-01", "DES-02"]},
    {"source": "Centro de costo", "suggested_target": null, "confidence": 0.0,
     "reason": "unmatched", "samples": ["CC-900"]}
  ],
  "target_fields": [{"key": "sku", "label": "SKU", "type": "TEXT", "required": true,
                     "help": "...", "example": "MAR-01", "enum_values": []}],
  "missing_required": [],
  "preview": [{"row_number": 4, "cells": [
    {"field_key": "sale_price", "raw": "$ 15.000", "value": "15000", "error": null}]}]
}
```

Cómo renderizarlo:

- **Dos columnas**: a la izquierda `columns` (lo que el usuario subió, con sus
  `samples` reales); a la derecha un `<select>` con `target_fields`.
- **`needs_review: true`** → marca visual. El acierto es plausible pero no
  seguro ("Centro de costo" se parece a un costo y no lo es).
- **`missing_required`** → no dejes avanzar; el backend responde
  `MISSING_REQUIRED_COLUMNS` de todas formas.
- **`preview`** es lo más valioso: muestra `raw` y `value` **lado a lado**. Ahí
  es donde el usuario ve que su `1.500` se leyó como 1500 y no como 1,5. Si
  `error` no es nulo, píntalo en rojo en esa celda.

**Paso 3**: manda el mapeo completo (no un parche). Si los números o fechas se
leen mal, fija el criterio:

```json
{"mapping": {"Referencia": "sku", "Artículo": "name", "PVP": "sale_price"},
 "decimal_separator": ".",      // opcional: "." o ","
 "date_format": "%d/%m/%Y",     // opcional
 "options": {"create_missing_categories": true}}
```

La respuesta trae la vista previa recalculada: enséñala antes de dejar continuar.

**Paso 4**: `validate` ejecuta la carga real dentro de un savepoint y la
revierte. Sus números **no son una estimación**, son lo que va a pasar:

```json
{"dry_run": true, "stats": {"total_rows": 100, "created": 95, "updated": 3,
                            "skipped": 2, "errors": 2},
 "errors_preview": [{"row_number": 12, "column": "PVP", "field_key": "sale_price",
                     "value": "mil pesos", "message": "'mil pesos' is not a valid number"}]}
```

Enseña ese resumen y pide confirmación. `run` repite la operación sin revertir.

**Errores de fila**: `GET /imports/{id}/errors?page=1&size=50`, paginados. El
`row_number` es el de la hoja del usuario (contando encabezado y filas en
blanco) y `column` es el nombre **de su columna**, no de nuestro campo. Una
tabla con esas dos cosas es suficiente para que arregle su archivo.

Notas:

- Todas las entidades hacen **upsert**. Volver a subir un archivo corregido es
  normal, no una limpieza.
- Orden recomendado (el que devuelve `/imports/schemas`): categorías → bodegas →
  productos → clientes → proveedores → stock. Un producto necesita su categoría;
  el stock necesita producto y bodega.
- Un job terminado no se puede reejecutar: `IMPORT_NOT_OPEN`. Sube el archivo de
  nuevo.
- Tope de 20.000 filas por archivo (`IMPORT_TOO_LARGE`).
- Las importaciones son **síncronas**: una de 20.000 filas puede tardar. Pon un
  estado de carga que aguante, no un spinner de 3 segundos.

### 8.6 Archivos e imágenes de producto

```http
POST /api/v1/files          multipart: file, owner_type, owner_id
GET  /api/v1/files?owner_type=PRODUCT&owner_id=...
GET  /api/v1/files/{id}/content
DELETE /api/v1/files/{id}
```

Para la imagen de un producto: `owner_type=PRODUCT`, `owner_id=<product_id>`.

> **La trampa más importante de este documento.**
>
> `GET /files/{id}/content` exige `Authorization` y `X-Company-ID`. Un
> `<img src="/api/v1/files/.../content">` **no funciona**: el navegador no manda
> esas cabeceras. Hay que descargar el blob y crear un object URL.

```ts
async function fileObjectUrl(id: string): Promise<string> {
  const res = await api.get(`/files/${id}/content`, { responseType: "blob" });
  return URL.createObjectURL(res.data);
}
// y al desmontar: URL.revokeObjectURL(url)
```

Guarda el object URL mientras el componente viva y revócalo al desmontar, o
tendrás una fuga de memoria en una grilla de productos.

Límites: **10 MB** por archivo y tipos permitidos `image/jpeg`, `image/png`,
`image/webp`, `image/gif`, `application/pdf`, `text/csv`, `.xlsx`. Valida en el
cliente para dar feedback inmediato, pero el backend rechaza igual
(`FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`).

El campo `download_url` viene ya armado en la respuesta; úsalo en vez de
construir la ruta.

### 8.7 Notificaciones

```http
GET  /api/v1/notifications?only_unread=true&page=1&size=20
POST /api/v1/notifications/{id}/read
```

La respuesta trae `unread` aparte del `total`, que es lo que necesitas para el
badge:

```json
{"items": [...], "total": 12, "unread": 3, "page": 1, "size": 20, "pages": 1}
```

**No hay websockets ni SSE todavía.** Haz polling cada 60 s (o al recuperar el
foco de la ventana). Las alertas de stock bajo las genera un job diario a las
07:00, así que no aparecen en tiempo real de todas formas.

### 8.8 Reportes

```http
GET /api/v1/reports/sales?since=2026-01-01T00:00:00Z&until=...&limit=10
GET /api/v1/reports/inventory-valuation
GET /api/v1/reports/low-stock?limit=50
GET /api/v1/reports/audit?page=1&size=20&action=SALE_COMPLETED
```

El de ventas cuenta **solo las `COMPLETED`**: los borradores no ocurrieron y las
canceladas o devueltas ya regresaron el dinero. Si tu tablero muestra otro
número, la diferencia es esa.

---

## 9. Consola de super admin

Rutas `/api/v1/admin/*`, solo para usuarios con `is_superuser`. **No llevan
`X-Company-ID`**: la empresa va en la ruta.

Cómo saber si mostrar la consola: llama a `GET /api/v1/admin/stats`. Si responde
`403 NOT_PLATFORM_ADMIN`, el usuario no es operador. (`/auth/me` no expone
`is_superuser` — si te resulta incómodo, es un cambio pequeño en el backend.)

```http
GET  /admin/stats                              tablero global
GET  /admin/companies/supervision?with_metrics=true   tabla de supervisión
GET  /admin/companies/{id}/overview            una empresa en detalle
POST /admin/companies                          aprovisionar empresa + dueño + plan
PATCH /admin/companies/{id}                    editar / suspender / reactivar
GET  /admin/users, POST /admin/users, PATCH /admin/users/{id}
GET  /admin/plans, POST /admin/plans, PATCH /admin/plans/{id}
PUT  /admin/companies/{id}/subscription        asignar plan
GET  /admin/audit                              auditoría de toda la plataforma
```

### Supervisión

`GET /admin/companies/supervision?with_metrics=true` es la tabla principal: por
empresa, plan, estado de suscripción y números reales (miembros, productos,
bodegas, ventas y facturación de 30 días, valor del inventario, última venta).

`with_metrics=false` es mucho más rápido: el backend entra a cada empresa por
turno para calcular las métricas. Con 20 filas está bien; ofrece el modo rápido
para búsquedas.

### Aprovisionar una empresa

```http
POST /admin/companies
{"name": "Ferretería Central", "owner_email": "ana@ferreteria.com",
 "owner_password": "clave-inicial", "plan_code": "STANDARD"}
```

Si `owner_email` ya tiene cuenta, esa persona pasa a ser dueña y
`owner_password` sobra. Si no la tiene, es obligatoria
(`OWNER_PASSWORD_REQUIRED`). La respuesta trae `owner_created` para que sepas si
hay que entregarle credenciales.

### Operar dentro de una empresa

El operador puede usar **cualquier** endpoint normal mandando el
`X-Company-ID` de la empresa destino — no necesita ser miembro. Es como se
diagnostica un problema o se le carga data a un cliente.

### Carga inicial de una empresa

```http
GET  /admin/onboarding/template                        libro con una hoja por entidad
POST /admin/companies/{id}/onboarding?dry_run=true     multipart: file
```

Las hojas se cargan en orden de dependencia dentro de **un solo savepoint**: o
la empresa queda montada o no se tocó nada. La respuesta trae un resultado por
hoja (`LOADED`, `LOADED_WITH_ERRORS`, `SKIPPED`, `EMPTY`, `MISSING_COLUMNS`) más
los totales. Corre siempre `dry_run=true` primero y enseña el resumen.

---

## 10. Mapa de pantallas → endpoints

| Pantalla | Llamadas |
|---|---|
| Login | `POST /auth/login` |
| Selector de empresa | `GET /companies` |
| Dashboard | `GET /reports/sales`, `/reports/low-stock`, `/notifications?only_unread=true` |
| Catálogo | `GET /products`, `GET /categories` |
| Ficha de producto | `GET /products/{id}`, `GET /files?owner_type=PRODUCT&owner_id=`, `GET /inventory/stock?product_id=` |
| Inventario | `GET /inventory/stock`, `GET /warehouses` |
| Kardex | `GET /inventory/movements?product_id=` |
| Ajuste / traslado | `POST /inventory/adjustments`, `/inventory/transfers` |
| Punto de venta | `GET /products`, `GET /customers`, `POST /sales` |
| Historial de ventas | `GET /sales?status=&customer_id=` |
| Compras | `GET /purchases`, `POST /purchases` |
| Clientes / Proveedores | `GET/POST/PATCH /customers`, `/suppliers` |
| Equipo | `GET /companies/current/members`, `GET /roles`, `POST /companies/current/members` |
| Roles | `GET /roles`, `GET /roles/permissions`, `POST/PATCH/DELETE /roles` |
| Importar | `GET /imports/schemas`, el flujo de 4 pasos |
| Reportes | `/reports/*` |
| Consola de plataforma | `/admin/*` |

---

## 11. Cliente de ejemplo (TypeScript)

Lo mínimo que resuelve las tres cosas que se repiten: la cabecera de empresa, el
refresco de token y la envoltura de error.

```ts
import axios, { AxiosError } from "axios";

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL + "/api/v1" });

// --- sesión (en producción, considera memoria + cookie httpOnly) ---
const session = {
  get access() { return localStorage.getItem("access_token"); },
  get refresh() { return localStorage.getItem("refresh_token"); },
  get companyId() { return localStorage.getItem("company_id"); },
  set(tokens: { access_token: string; refresh_token: string }) {
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
  },
  setCompany(id: string) { localStorage.setItem("company_id", id); },
  clear() { localStorage.clear(); },
};

// --- las dos cabeceras, una sola vez ---
api.interceptors.request.use((config) => {
  if (session.access) config.headers.Authorization = `Bearer ${session.access}`;
  // Las rutas de auth, /companies y /admin no la quieren.
  const url = config.url ?? "";
  const skip = url.startsWith("/auth") || url === "/companies" || url.startsWith("/admin");
  if (session.companyId && !skip) config.headers["X-Company-ID"] = session.companyId;
  return config;
});

// --- refresco: una sola petición en vuelo, el resto espera ---
let refreshing: Promise<void> | null = null;

api.interceptors.response.use(undefined, async (error: AxiosError<ApiError>) => {
  const original = error.config!;
  const code = error.response?.data?.error?.code;

  if (error.response?.status === 401 && !(original as any)._retried && session.refresh) {
    (original as any)._retried = true;
    refreshing ??= axios
      .post(`${api.defaults.baseURL}/auth/refresh`, { refresh_token: session.refresh })
      .then((r) => session.set(r.data))
      .catch(() => { session.clear(); location.href = "/login"; })
      .finally(() => { refreshing = null; });
    await refreshing;
    return api(original);
  }

  if (code === "INVALID_COMPANY" || code === "INVALID_MEMBERSHIP") {
    location.href = "/select-company";
  }
  return Promise.reject(error);
});

// --- forma del error, para tipar los catch ---
export interface ApiError {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export const errorCode = (e: unknown) =>
  (e as AxiosError<ApiError>)?.response?.data?.error?.code;

export default api;
```

Dinero, con `decimal.js`:

```ts
import Decimal from "decimal.js";

export const money = (value: string) => new Decimal(value);
export const formatMoney = (value: string, currency = "COP") =>
  new Intl.NumberFormat("es-CO", { style: "currency", currency })
    .format(new Decimal(value).toNumber());   // solo para mostrar, nunca para calcular
```

---

## 12. Entorno de desarrollo

```bash
docker compose up --build            # api, postgres, redis, worker
make superuser email=tu@correo.com   # primer operador de plataforma
```

API en `http://localhost:8000`, Swagger en `/docs`.

### CORS

Configurado por variable de entorno en el backend:

```env
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Si tu dev server usa otro puerto, agrégalo ahí o las peticiones fallarán antes
de llegar a la API. `X-Request-ID` está expuesto como cabecera de respuesta.

### Datos de prueba

La forma más rápida de tener una empresa con datos: registrarte con
`company_name`, bajar `GET /imports/templates/PRODUCTS`, llenarla y subirla.

---

## 13. Limitaciones que afectan al frontend

Cosas que el backend todavía no hace y que conviene saber **antes** de diseñar:

- **Sin tiempo real.** Ni websockets ni SSE. Polling para notificaciones.
- **El logout no revoca.** Un access token robado sirve 15 minutos más.
- **Las imágenes requieren autenticación**, así que no se pueden usar en un
  `<img src>` directo (ver 8.6). URLs firmadas serían la solución; no existen
  todavía.
- **Sin numeración consecutiva de documentos.** Las ventas y compras se
  identifican por UUID. Si tu UI necesita mostrar "Factura #0001", eso todavía
  no existe en el backend.
- **Importaciones síncronas**, tope 20.000 filas.
- **Las cuotas de plan no bloquean.** `max_users`, `max_products` y
  `max_warehouses` se muestran en `/admin/companies/{id}/overview` pero no
  impiden crear el recurso. Si la UI dice "llegaste al límite", hoy lo dice sola.
- **Sin invitaciones por correo.** Para agregar un miembro, la persona ya debe
  tener cuenta (`POST /auth/register` sin `company_name`), o el operador se la
  crea desde `/admin/users`.
- **`/auth/me` no dice si eres super admin.** Se descubre llamando a
  `/admin/stats` y viendo si responde 403.
