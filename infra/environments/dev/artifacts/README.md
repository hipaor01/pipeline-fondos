# Artefactos de dev

Este root module crea el bucket versionado en el que la pipeline publica los
ZIP de Lambda. Tiene estado separado de la API porque el bucket debe existir
antes de que pueda subirse el artefacto referenciado por `aws_lambda_function`.

La pipeline ejecuta este root antes de empaquetar la API. Los objetos bajo
`api/` caducan a los 30 días por defecto; Lambda conserva internamente el código
ya desplegado y no lee el ZIP de S3 durante cada invocación.
