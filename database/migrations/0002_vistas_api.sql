-- Vistas de lectura para la API (contrato C4). La API consulta estas vistas y no
-- las tablas, así el esquema físico puede cambiar sin romper el repositorio de P3.
-- Las columnas coinciden con los modelos api/models/kid.py y api/models/fondo.py.

CREATE OR REPLACE VIEW api_kid_version AS
SELECT
    k.isin,
    k.nombre_producto,
    k.nombre_clase,
    g.codigo                                          AS gestora_codigo,
    g.nombre                                          AS gestora_nombre,
    k.fecha_documento,
    k.sri,
    CAST(k.periodo_mantenimiento_anios AS double precision) AS periodo_mantenimiento_anios,
    CAST(k.gastos_corrientes_pct AS double precision)       AS gastos_corrientes_pct,
    CAST(k.costes_entrada_pct AS double precision)          AS costes_entrada_pct,
    CAST(k.costes_salida_pct AS double precision)           AS costes_salida_pct,
    d.sha256                                          AS documento_sha256
FROM kid_version k
JOIN documento d   ON d.id = k.documento_id
JOIN clase_fondo c ON c.isin = k.isin
JOIN fondo f       ON f.id = c.fondo_id
JOIN gestora g     ON g.codigo = f.gestora_codigo;

-- Un fondo (clase, por ISIN) con los datos de su KID más reciente.
-- Desempate determinista por sha256 si dos KID tienen la misma fecha.
CREATE OR REPLACE VIEW api_fondo AS
SELECT DISTINCT ON (isin)
    isin,
    nombre_producto,
    nombre_clase,
    gestora_codigo,
    gestora_nombre,
    fecha_documento AS fecha_ultimo_kid,
    sri,
    periodo_mantenimiento_anios,
    gastos_corrientes_pct,
    costes_entrada_pct,
    costes_salida_pct
FROM api_kid_version
ORDER BY isin, fecha_documento DESC NULLS LAST, documento_sha256;
