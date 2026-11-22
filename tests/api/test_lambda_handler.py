"""Pruebas del adaptador de AWS Lambda para FastAPI."""

import json
import unittest
from typing import Any

from api.lambda_handler import handler


class ContextoLambdaPrueba:
    """Contexto mínimo suficiente para invocar Mangum localmente."""

    function_name = "api-fondos-prueba"
    aws_request_id = "lambda-request-id-prueba"


def crear_evento_http_v2(
    ruta: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Crea un evento equivalente al enviado por API Gateway HTTP API."""

    headers = {
        "host": "api.example.execute-api.eu-west-3.amazonaws.com",
        "user-agent": "unittest",
        "x-forwarded-proto": "https",
    }
    if correlation_id is not None:
        headers["x-correlation-id"] = correlation_id

    return {
        "version": "2.0",
        "routeKey": f"GET {ruta}",
        "rawPath": ruta,
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "api-prueba",
            "domainName": "api.example.execute-api.eu-west-3.amazonaws.com",
            "domainPrefix": "api-prueba",
            "http": {
                "method": "GET",
                "path": ruta,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "unittest",
            },
            "requestId": "api-gateway-request-id-prueba",
            "routeKey": f"GET {ruta}",
            "stage": "$default",
            "time": "21/Nov/2026:12:00:00 +0000",
            "timeEpoch": 1795262400000,
        },
        "isBase64Encoded": False,
    }


class TestLambdaHandler(unittest.TestCase):
    def test_adapta_un_evento_http_api_v2(self) -> None:
        correlation_id = "peticion-lambda-prueba"

        respuesta = handler(
            crear_evento_http_v2("/health", correlation_id),
            ContextoLambdaPrueba(),
        )

        self.assertEqual(respuesta["statusCode"], 200)
        self.assertEqual(
            json.loads(respuesta["body"]),
            {"estado": "ok", "servicio": "api-fondos", "version": "0.1.0"},
        )
        self.assertEqual(
            respuesta["headers"]["x-correlation-id"],
            correlation_id,
        )
        self.assertFalse(respuesta["isBase64Encoded"])


if __name__ == "__main__":
    unittest.main()
