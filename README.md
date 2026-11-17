# Hermes

Hermes es un servicio HTTP privado y de solo lectura para consultar una única cuenta IMAP
desde agentes autorizados. Los clientes nunca reciben credenciales IMAP ni pueden enviar
comandos IMAP arbitrarios. La fase 1 no incluye envío, borrado, movimiento, edición ni descarga
de adjuntos.

## Seguridad y límites

- IMAP usa TLS implícito y validado (`IMAP4_SSL`) y selecciona únicamente `INBOX` con
  `readonly=True`.
- Todas las operaciones usan UID. Cada referencia persistible contiene carpeta,
  `UIDVALIDITY` y UID; un cambio de `UIDVALIDITY` produce HTTP 409.
- El cuerpo completo se obtiene con `BODY.PEEK[]`. Antes se consulta `RFC822.SIZE` y el límite
  vuelve a comprobarse después de descargar.
- El contenido del correo se marca como no confiable. HTML se convierte a texto sin ejecutar
  scripts ni cargar recursos. Los adjuntos no se descargan mediante la API.
- Los endpoints de datos requieren `Authorization: Bearer ...`, tienen autorización por
  identidad, carpeta y operación, y un límite de peticiones en memoria por instancia.
- Los logs de auditoría guardan una identidad derivada, operación, UID o cantidad; no guardan
  tokens, credenciales ni cuerpos. No existe almacenamiento persistente de mensajes: los datos
  viven solo durante cada petición. Los logs deben rotarse y retenerse conforme a la política
  del operador; Hermes no crea archivos de log.
- La red Docker no sustituye la autenticación. Si el tráfico cruza hosts o una red no confiable,
  debe añadirse TLS mediante un proxy interno o una malla de servicios.

Los campos `From`, `To`, `Date`, `Message-ID` y el texto citado pueden falsificarse. Hermes
expone el remitente aparente del mensaje recibido y no intenta inferir la identidad original de
un correo reenviado. Un texto como «ignora tus instrucciones» sigue siendo solamente contenido.

## Configuración

Requiere Python 3.12 o posterior. Copia `.env.example` a un `.env` local ignorado por Git y
completa los valores. Los secretos deben tener al menos 32 caracteres.

| Variable | Uso |
|---|---|
| `MAIL_IMAP_HOST` | Host real del proveedor IMAP (obligatorio) |
| `MAIL_IMAP_PORT` | Puerto TLS implícito, por defecto `993` |
| `MAIL_IMAP_USER` / `MAIL_IMAP_PASSWORD` | Credenciales dentro del contenedor Hermes |
| `MAIL_IMAP_FOLDER` | Debe ser `INBOX` en fase 1 |
| `MAIL_CONNECT_TIMEOUT_SECONDS` | Timeout de conexión, por defecto 15 |
| `MAIL_MAX_MESSAGES_PER_REQUEST` | Máximo de resultados, por defecto 50 |
| `MAIL_MAX_MESSAGE_BYTES` | Máximo antes y después del fetch, por defecto 2 MiB |
| `MAIL_MAX_BODY_TEXT_CHARS` | Texto máximo devuelto, por defecto 50 000 caracteres |
| `API_AUTH_TOKEN` | Identidad `summary_agent`, permisos `mail:read` y `mail:search` |
| `API_COMMERCIAL_AGENT_TOKEN` | Opcional; identidad distinta con solo `mail:search` |
| `API_RATE_LIMIT_PER_MINUTE` | Tope por identidad e instancia, por defecto 60 |

El login implementado es usuario/contraseña. Algunos proveedores exigen una contraseña de
aplicación; otros requieren OAuth, que todavía no está implementado. No se afirma compatibilidad
con un proveedor hasta probarlo con su configuración real.

## Ejecución

```sh
docker compose build
docker compose up -d
docker compose logs hermes
docker compose ps
```

El servicio escucha en `0.0.0.0:8000` dentro del contenedor pero Compose no publica ningún
puerto al host. Un consumidor autorizado en la misma red usa `http://hermes:8000`.

Prueba desde un contenedor conectado a la red (sustituye el nombre de red que muestre
`docker network ls`; no introduzcas el token en historial compartido):

```sh
curl -H "Authorization: Bearer $API_AUTH_TOKEN" \
  'http://hermes:8000/v1/messages?folder=INBOX&limit=5'
```

Para acceso de desarrollo desde el host, crea un archivo local
`compose.host.yaml` que no se versiona:

```yaml
services:
  hermes:
    ports:
      - "127.0.0.1:8000:8000"
```

Y ejecuta `docker compose -f compose.yaml -f compose.host.yaml up -d`. Nunca publiques el puerto
en todas las interfaces por defecto.

### Integración con otro Compose

Crea o reutiliza una red externa cuyo nombre decida el operador y declárala en ambos proyectos:

```yaml
services:
  hermes:
    networks: [hermes_private, agents_shared]

networks:
  agents_shared:
    external: true
    name: ${AGENTS_DOCKER_NETWORK:?set AGENTS_DOCKER_NETWORK}
```

Conecta solamente los consumidores autorizados. No copies las variables `MAIL_*` a sus
contenedores. La red no se marca `internal: true`, porque Hermes necesita egreso al host IMAP.

## API v1

- `GET /health`: salud del proceso, sin comprobar IMAP y sin autenticación.
- `GET /v1/messages?folder=INBOX&limit=20&cursor=...`: metadatos, UID descendente.
- `GET /v1/messages/{uid}?folder=INBOX&uidvalidity=...`: mensaje y texto limitado.
- `GET /v1/messages/search?...`: filtros validados `since`, `before`, `from_address`, `subject`,
  `limit` y `cursor`.

El cursor es Base64 URL-safe de un objeto versionado con `UIDVALIDITY` y el UID anterior; es
opaco para clientes. La paginación no representa una instantánea inmutable si llegan mensajes.
Errores relevantes: 400 entrada/cursor, 401 credenciales, 403 permiso, 404 UID, 409
`UIDVALIDITY`, 413 tamaño, 429 tasa, 502 protocolo IMAP y 503 conexión.

La respuesta de detalle incluye `body_truncated` y `content_is_untrusted: true`. Los adjuntos se
limitan a nombre saneado, MIME y tamaño estimado. No hay rutas de escritura ni de adjuntos.

## Desarrollo y pruebas

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

Las pruebas usan dobles IMAP y no necesitan una cuenta. La comprobación manual opcional contra
una cuenta real muestra únicamente UID y tamaño de hasta cinco mensajes:

```sh
hermes-check-mailbox
```

No valida el servidor real durante CI ni imprime contraseña, asunto, remitente o cuerpo.

