# Captura de Azvalor

Observación del 23 de noviembre de 2026. Las rutas, documentos y nombres pueden cambiar.

La página [Fondos de inversión](https://www.azvalor.com/fondos-de-inversion/) entrega HTML que incluye en su menú enlaces a fondos españoles y a SICAV o clases. Se identificaron cinco fondos y seis páginas de SICAV o clases, sin necesidad de ejecutar JavaScript para descubrirlos. El intento de consulta de `https://www.azvalor.com/robots.txt` devolvió HTTP 418; por tanto, esta revisión no pudo determinar su contenido ni confirmar sus reglas. El scraper usa una pausa configurable, de un segundo por defecto.

Las cinco páginas de fondos enlazaban un **Folleto simplificado (DFP)**. Como comprobación de contenido, el DFP enlazado por Azvalor Internacional tenía el título «Documento de Datos Fundamentales del Producto», ISIN, riesgo y costes; por ello se clasifica como `kid`. Las páginas de SICAV enlazaban tanto un DFP como documentos llamados **Documento de datos fundamentales** según el producto. También se localizan enlaces a fichas con las etiquetas `Ficha del producto`, `Ficha de producto` o `Ficha producto`. `Folleto completo` no se confunde con un KID.

`webscrapper/descargar_kids_azvalor.py` identifica los productos desde el menú del encabezado, con un selector de respaldo para enlaces de la página; solo acepta páginas HTTPS del dominio `www.azvalor.com` con las rutas directas `/fondos-de-inversion/<slug>/` y `/sicavs/<slug>/`. En cada ficha busca primero el bloque de documentos y recurre al conjunto de enlaces si no encuentra un KID. Solo acepta destinos HTTPS terminados en `.pdf`. Si un mismo tipo tiene dos URLs distintas, registra una incidencia en vez de elegir una arbitrariamente.

Las clases de SICAV con sus propias páginas tienen claves separadas. Por ejemplo, Internacional Lux I y R tienen ISIN y KID diferentes, aunque enlazan la misma ficha: se conservan ambas referencias para no perder la relación con cada clase. La deduplicación lógica de contenidos compartidos sigue pendiente de P2.

## Prueba real en S3 personal

Se usó el bucket versionado de pruebas de P1, no la cuenta ni el despliegue Terraform del compañero. Una ejecución completa descubrió 11 productos y subió **11 KID y 10 fichas**. La única ausencia registrada fue la ficha de producto de Azvalor Capital FI; no hubo errores registrados.

Se leyeron de nuevo desde S3 las 21 versiones indicadas en el manifiesto `p1-aws-azvalor-20261123-1`, comprobando para cada una la clave, firma PDF, `Content-Type`, SHA-256 de los bytes frente a manifiesto y metadatos, gestora, tipo, URL de origen y `correlation-id`. Esta prueba no valida la extracción posterior del contenido, los eventos S3 ni la deduplicación lógica.

Las pruebas automatizadas usan HTML sintético basado en la estructura observada y cubren selectores, respaldo, diferencias entre clases, ausencias, enlaces duplicados o ambiguos, fallos de página y una ejecución con S3 simulado.
