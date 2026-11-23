# Captura de Cobas AM

Observación del 23 de noviembre de 2026. Las rutas y documentos pueden cambiar.

La página [Productos](https://www.cobasam.com/productos/) entrega HTML estático con enlaces de productos de inversión. Se identificaron siete páginas bajo `/productos/inversion-libre/`: cinco fondos ordinarios, un fondo de inversión libre y una SICAV. Se excluyen los planes de pensiones. `https://www.cobasam.com/robots.txt` devolvió HTTP 200 y, en el momento de la consulta, la regla general no indicaba rutas prohibidas.

Cada página contiene uno o varios bloques `section.with-docs`. Cada bloque reúne el nombre o clase, el ISIN y la documentación de esa clase. Cinco productos mostraban clases A–D; Renta y Value SICAV tenían un bloque sin clase visible. En cada bloque el enlace `PRIIP pdf` identifica el KID y `Ficha del fondo pdf` la ficha. Los PDFs observados están en un dominio S3 público enlazado por la propia web de Cobas. Se usa un selector de respaldo por bloque de ficha si cambia el contenedor principal.

`webscrapper/descargar_kids_cobas.py` mantiene una clave distinta por producto, clase y tipo, por ejemplo `raw/cobas/AAAAMMDD/cobas-seleccion-clase-a_kid.pdf`. Registra incidencias cuando no puede identificar una clase de forma única, faltan KID o hay varios enlaces distintos para el mismo tipo; no atribuye un documento de un bloque a otra clase.

## Prueba real en la cuenta personal

La ejecución `p1-aws-cobas-20261123-1` usó el bucket de pruebas versionado de P1. Identificó siete productos y **22 bloques de clase o producto**; subió 22 KID y 22 fichas y registró cero ausencias y cero fallos. Se leyeron las 44 versiones indicadas en el manifiesto y se comprobaron claves, firma PDF, tipo de contenido, SHA-256, metadatos de gestora y tipo, URL de origen y correlación.

Se extrajo texto de cada uno de los 22 KID desde su versión en S3 y en todos se encontró el ISIN mostrado en su bloque de la web. Esto comprueba la asociación observada en esta ejecución, no el resto de los datos de los KID ni la extracción que realizará P2. No se probaron eventos S3, deduplicación lógica ni ejecución automática.

Las pruebas locales usan HTML sintético basado en la estructura observada y cubren dos clases, fondo sin clase, selectores de respaldo, ISIN ambiguo, KID ausente, enlaces ambiguos, errores de página y el manifiesto con S3 simulado.
