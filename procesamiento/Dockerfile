# syntax=docker/dockerfile:1.7
#
# Imagen común de las Lambdas de procesamiento (P2). Se usa imagen y no ZIP porque
# pymupdf4llm 2.1 arrastra pymupdf + onnxruntime + numpy: ~252 MB sin comprimir,
# por encima del límite de 250 MB de un ZIP de Lambda.
#
# Una imagen, dos funciones: cada Lambda elige su handler con image_config.command.
#   procesamiento.markdown.handler    PDF -> Markdown
#   procesamiento.extraccion.handler  Markdown -> Bedrock -> Aurora
#
# Construir desde la raíz del repositorio:
#   docker buildx build --platform linux/arm64 -f procesamiento/Dockerfile -t procesamiento .

ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.13.7

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock /tmp/build/

RUN uv export \
        --quiet \
        --directory /tmp/build \
        --only-group lambda-procesamiento \
        --no-emit-project \
        --locked \
        --output-file /tmp/build/requirements.txt \
    && uv pip install \
        --quiet \
        --no-cache \
        --compile-bytecode \
        --python /var/lang/bin/python3 \
        --target "${LAMBDA_TASK_ROOT}" \
        --requirements /tmp/build/requirements.txt \
    && rm -rf /tmp/build /usr/local/bin/uv

COPY procesamiento "${LAMBDA_TASK_ROOT}/procesamiento"
COPY database "${LAMBDA_TASK_ROOT}/database"

CMD ["procesamiento.markdown.handler"]
