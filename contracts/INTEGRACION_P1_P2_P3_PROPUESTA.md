# Propuesta de integración P1, P2 y P3

**Estado:** propuesta provisional de P1 para avanzar en paralelo. La prioridad es localizar y reutilizar la infraestructura existente; las responsabilidades y raíces de abajo son alternativas si faltan piezas, no una decisión de crear recursos nuevos. No describe infraestructura ya desplegada ni autoriza modificar recursos existentes.

## Situación actual

- Ya hay raíces Terraform y estados separados para API, artefactos, registro frontend y servicio frontend en `infra/environments/dev/`; usan un backend S3 y bloqueo por lockfile.
- `infra/bootstrap/` define el rol OIDC de GitHub Actions y sus políticas actuales para API y frontend. No se debe asumir que estas cubren almacenamiento o ingesta.
- La frontera de permisos Lambda existente en `infra/bootstrap/lambda_boundary.tf` solo contempla logs de la API: no sirve sin cambios para las operaciones S3 de un scraper.
- El workflow de API filtra sus rutas y valida y despliega la API; no constituye CI/CD de P1. No se ha inspeccionado el estado AWS real.
- El 22 de noviembre se revisaron las ramas y PR disponibles en GitHub: `main` coincidía con el checkout y no se encontraron ramas o PR adicionales de ingesta. El 23 se comprobó una cuenta personal diferente y se creó en ella un bucket aislado para pruebas; esto no informa de los recursos que existan en la cuenta del compañero. Véase la [guía AWS](../documentacion/GUIA_AWS_CAPTURA.md).

## Responsabilidad propuesta

| Componente | Responsable de implementación | Propietario Terraform propuesto | Integración |
| --- | --- | --- | --- |
| Bucket de documentos, cifrado, acceso público y versionado | P1 | Raíz independiente `dev/storage` | P1 publica nombre, ARN y región; P2 los consume. El backend de Terraform y el bucket de artefactos son distintos del bucket de documentos. |
| ECR, Lambdas de scraping, roles de ejecución, Step Functions y Scheduler | P1 | Raíz independiente `dev/ingestion` | Recibe bucket y digest de imagen; publica ARN de la máquina de estados y demás identificadores útiles. |
| Cola PDF, su DLQ y permisos de consumo | P2 | Raíz de procesamiento de P2 | Publica ARN de cola y configura su política para permitir la fuente S3 correcta. |
| **Configuración completa de notificaciones del bucket** | P2, coordinado con P1 | Un único recurso y un único estado, inicialmente en la raíz de procesamiento de P2 | P2 recibe el bucket de P1 y configura todas las notificaciones del bucket conjuntamente. P1 no declara otro recurso de notificación para ese bucket. |
| Backend compartido, rol OIDC, permisos de despliegue y enlace de workflows | P3 con aportaciones de P1/P2 | `infra/bootstrap` y configuración compartida existentes | P1 y P2 proponen permisos concretos y claves de estado; P3 integra y revisa. Los permisos de despliegue son distintos de los roles de ejecución. |

La configuración de notificaciones S3 es compartida por bucket: se debe inventariar lo que ya exista e identificar su propietario actual, preservando las reglas necesarias. La asignación a P2 es una propuesta solo si todavía no existe dueño. Antes de aplicar, revisar también los filtros y las políticas de destino. Si se acuerda cambiar su ubicación, actualizar este documento y registrar el traslado de estado; nunca gestionarlo desde dos estados a la vez.

## Estados, entradas y salidas

Si no existen ya raíces y estados adecuados, estas son posibles rutas bajo el backend remoto existente; no crearlas hasta comprobarlo:

- `pipeline-fondos/dev/storage/terraform.tfstate`.
- `pipeline-fondos/dev/ingestion/terraform.tfstate`.
- El estado de procesamiento lo determina P2; su recurso de notificación consume el bucket publicado por `storage`.

Orden lógico: **storage → ECR e imagen → ingesta**; en paralelo después de storage, **cola y política de P2 → notificación del bucket**. Los consumidores reciben identificadores mediante outputs y entradas explícitas; el mecanismo concreto para pasarlos se elige al implementar. Si se usa `terraform_remote_state`, considerar que el permiso para leer el estado permite acceder a todo su contenido, no solo a los outputs. Evitar ciclos entre raíces.

Entradas iniciales: región, entorno, nombre del bucket de documentos, configuración de protección y retención, digest de la imagen, parámetros de Scheduler y nombres/etiquetas. Salidas iniciales: nombre y ARN del bucket, identificador del repositorio ECR, ARN de la máquina de estados y ARN de la cola de P2 donde corresponda. Refinar en código cuando existan los módulos; no guardar secretos en outputs ni en `tfvars` versionados.

## Despliegue y permisos

1. P1 prepara módulos, tests y un workflow de validación de ingesta que cubra sus rutas. Los PR ejecutan validaciones sin credenciales de despliegue cuando sea posible.
2. P1 proporciona a P3 el inventario de acciones y recursos necesarios para los nuevos estados, lockfiles, S3 de documentos, ECR, Lambda, IAM, Step Functions, Scheduler y logs. P2 hace lo propio para colas y notificaciones. Los permisos exactos se derivan y prueban con los planes y acciones reales, limitando recursos y `iam:PassRole` donde sea viable.
3. P3 integra las políticas OIDC y cualquier frontera de permisos adecuada para los nuevos roles; el equipo verifica que no se amplíe accidentalmente el alcance de los roles actuales. El rol de ejecución del scraper solo recibe los permisos necesarios para su tarea.
4. Tras integrar bootstrap, el flujo de despliegue publica una imagen identificada por digest y aplica los estados en el orden necesario. La cola y su política deben existir antes de configurar la notificación de S3. La activación del Scheduler y las pruebas reales se coordinan con P2 para que no se pierda el primer evento de integración.
5. El workflow no debe alterar estados de API o frontend. Revisar el plan de cada raíz, especialmente cambios destructivos o reemplazos, y registrar resultados y responsables.

## Bucket histórico y transición

El nombre `curso-miax-pipeline-fondos` aparece como destino histórico en el scraper. Antes de reutilizarlo hay que comprobar cuenta propietaria, región, configuración, notificaciones, contenido y estado Terraform existente. No crear un recurso Terraform para un bucket ya gestionado por otro estado ni importar o cambiar su configuración sin revisar el plan y acordar la propiedad. Si se decide uno nuevo, documentar cómo se conservan o migran los objetos antiguos y cómo se evita duplicar su procesamiento. El bucket aislado de la cuenta personal no sustituye esta comprobación en la cuenta del compañero.

## Criterios de cierre de 0.4

- [ ] Identificar los responsables existentes del bucket y de su configuración completa de notificaciones; consultar al equipo solo si no se puede determinar con la evidencia disponible.
- [ ] Se registran raíces, claves de estado, entradas/salidas, orden de despliegue y procedimiento para cambios compartidos.
- [ ] Se inventaría el bucket real y sus notificaciones sin modificarlo; se decide reutilización o creación y transición de datos.
- [ ] P1/P2 entregan a P3 la lista de permisos de despliegue y ejecución; P3 valida OIDC, lockfiles y fronteras necesarias.
- [ ] Se revisan planes Terraform y se valida una integración en dev sin cambios inesperados en recursos existentes.
