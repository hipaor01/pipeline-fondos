-- Contrato C4: tablas gestora, fondo, clase_fondo, documento y kid_version.
-- Reglas de idempotencia:
--   * documento.sha256 es único: el mismo PDF descargado dos veces es un solo documento.
--   * kid_version es única por (isin, fecha_documento, documento_id): versión lógica.
-- Cada sentencia termina en ';' al final de línea (el runner de la Data API las separa así).

CREATE TABLE gestora (
    codigo      text        PRIMARY KEY CHECK (codigo ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    nombre      text        NOT NULL CHECK (length(nombre) BETWEEN 1 AND 200),
    creado_en   timestamptz NOT NULL DEFAULT now()
);

INSERT INTO gestora (codigo, nombre) VALUES
    ('bestinver', 'Bestinver'),
    ('azvalor', 'Azvalor'),
    ('cobas', 'Cobas AM')
ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE fondo (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gestora_codigo  text        NOT NULL REFERENCES gestora (codigo),
    nombre_producto text        NOT NULL CHECK (length(nombre_producto) BETWEEN 1 AND 300),
    creado_en       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fondo_gestora_nombre_uk UNIQUE (gestora_codigo, nombre_producto)
);

CREATE TABLE clase_fondo (
    isin       text        PRIMARY KEY CHECK (isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
    fondo_id   bigint      NOT NULL REFERENCES fondo (id),
    creado_en  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documento (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sha256          text        NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    gestora_codigo  text        NOT NULL REFERENCES gestora (codigo),
    tipo_documento  text,
    s3_bucket       text        NOT NULL,
    s3_key          text        NOT NULL,
    s3_version_id   text,
    url_origen      text,
    fecha_descarga  timestamptz,
    correlation_id  text,
    json_s3_key     text,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT documento_sha256_uk UNIQUE (sha256)
);

CREATE TABLE kid_version (
    id                          bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento_id                bigint       NOT NULL REFERENCES documento (id),
    isin                        text         NOT NULL REFERENCES clase_fondo (isin),
    nombre_producto             text         NOT NULL,
    nombre_clase                text,
    gestora_productor           text         NOT NULL,
    fecha_documento             date,
    sri                         smallint     NOT NULL CHECK (sri BETWEEN 1 AND 7),
    periodo_mantenimiento_anios numeric(6, 2) CHECK (periodo_mantenimiento_anios >= 0),
    gastos_corrientes_pct       numeric(7, 4) CHECK (gastos_corrientes_pct BETWEEN 0 AND 100),
    costes_entrada_pct          numeric(7, 4) CHECK (costes_entrada_pct BETWEEN 0 AND 100),
    costes_salida_pct           numeric(7, 4) CHECK (costes_salida_pct BETWEEN 0 AND 100),
    schema_version              text         NOT NULL,
    modelo_id                   text         NOT NULL,
    extraido_en                 timestamptz  NOT NULL,
    cargado_en                  timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT kid_version_logica_uk UNIQUE NULLS NOT DISTINCT (isin, fecha_documento, documento_id)
);

CREATE INDEX kid_version_isin_fecha_idx ON kid_version (isin, fecha_documento DESC);

CREATE INDEX fondo_gestora_idx ON fondo (gestora_codigo);
