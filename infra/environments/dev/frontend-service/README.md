# Servicio frontend de dev

Este root module despliega la imagen inmutable del frontend en ECS Express Mode.
El registro ECR permanece en el root `dev/frontend`, porque debe existir antes
de construir la imagen que recibe este servicio.

La configuración utiliza:

- Linux ARM64 sobre AWS Graviton;
- 0,5 vCPU y 1 GiB de memoria por tarea;
- entre 1 y 2 tareas según el uso medio de CPU;
- puerto `8501` y health check `/_stcore/health`;
- endpoint HTTPS público administrado por ECS Express;
- logs en CloudWatch con 14 días de retención;
- el endpoint de la API leído desde el estado remoto del root `dev`.

La pipeline proporciona `frontend_image` con el digest publicado en ECR. Para
un plan manual hay que indicar también una imagen existente:

```bash
terraform -chdir=infra/environments/dev/frontend-service init \
  -backend-config="bucket=pipeline-fondos-terraform-state-065451207233"
terraform -chdir=infra/environments/dev/frontend-service plan \
  -var='frontend_image=065451207233.dkr.ecr.eu-west-3.amazonaws.com/pipeline-fondos-dev-frontend@sha256:REPLACE_DIGEST'
```
