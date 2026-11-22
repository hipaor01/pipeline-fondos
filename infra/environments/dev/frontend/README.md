# Frontend de dev

Este root module crea el repositorio privado de ECR utilizado por el frontend
Streamlit. Tiene un estado separado del servicio de la API para que la pipeline
pueda aprovisionar el registro antes de construir y publicar la imagen.

El repositorio utiliza etiquetas inmutables, cifrado AES-256, escaneo básico al
publicar y una política que conserva las 30 imágenes más recientes por defecto.
La pipeline etiqueta cada imagen con el SHA completo del commit.

La primera ejecución requiere aplicar previamente `infra/bootstrap`, porque el
rol OIDC necesita permisos sobre este estado y sobre el repositorio de ECR.

```bash
TF_STATE_BUCKET=$(terraform -chdir=infra/bootstrap output -raw state_bucket_name)

terraform -chdir=infra/environments/dev/frontend init \
  -backend-config="bucket=${TF_STATE_BUCKET}"
terraform -chdir=infra/environments/dev/frontend plan
terraform -chdir=infra/environments/dev/frontend apply
```
