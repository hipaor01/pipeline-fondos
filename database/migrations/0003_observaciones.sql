-- Procedencias (contrato C1 v1): cada objeto S3 exacto que trajo un PDF, aunque su
-- contenido (sha256) ya estuviera cargado. Un mismo PDF puede llegar varios días,
-- desde varias URL o en reintentos de P1; `documento` guarda el contenido una vez y
-- aquí queda cada observación. Única por (bucket, key, versionId): repetir el
-- mismo evento no crea filas.

CREATE TABLE documento_observacion (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento_id    bigint      NOT NULL REFERENCES documento (id),
    gestora_codigo  text        NOT NULL,
    tipo_documento  text,
    s3_bucket       text        NOT NULL,
    s3_key          text        NOT NULL,
    s3_version_id   text,
    url_origen      text,
    fecha_descarga  timestamptz,
    correlation_id  text,
    json_s3_key     text,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT documento_observacion_objeto_uk UNIQUE NULLS NOT DISTINCT (s3_bucket, s3_key, s3_version_id)
);

CREATE INDEX documento_observacion_documento_idx ON documento_observacion (documento_id);

-- El primer objeto de cada documento ya existente pasa a ser su primera observación.
INSERT INTO documento_observacion (
    documento_id, gestora_codigo, tipo_documento, s3_bucket, s3_key, s3_version_id,
    url_origen, fecha_descarga, correlation_id, json_s3_key
)
SELECT id, gestora_codigo, tipo_documento, s3_bucket, s3_key, s3_version_id,
       url_origen, fecha_descarga, correlation_id, json_s3_key
FROM documento
ON CONFLICT ON CONSTRAINT documento_observacion_objeto_uk DO NOTHING;
