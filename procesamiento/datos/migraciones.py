"""Aplica las migraciones de `database/migrations/` en orden y una sola vez.

Uso:
    # Aurora (Data API), con credenciales AWS y los ARN que da Terraform:
    python -m procesamiento.datos.migraciones \
        --cluster-arn arn:aws:rds:... --secret-arn arn:aws:secretsmanager:... --base-datos fondos
    # PostgreSQL local:
    python -m procesamiento.datos.migraciones --dsn postgresql://localhost/fondos
"""

import argparse
import re
import sys
from pathlib import Path

from procesamiento.datos.ejecutor import EjecutorDataAPI, EjecutorPsycopg, EjecutorSQL

CARPETA = Path(__file__).resolve().parents[2] / "database" / "migrations"

SQL_TABLA_CONTROL = """
CREATE TABLE IF NOT EXISTS schema_migraciones (
    version    text        PRIMARY KEY,
    aplicada_en timestamptz NOT NULL DEFAULT now()
)
"""


def sentencias(sql: str) -> list[str]:
    """Separa un fichero en sentencias: cada una acaba en ';' al final de una línea."""
    sin_comentarios = "\n".join(
        linea for linea in sql.splitlines() if not linea.lstrip().startswith("--")
    )
    partes = re.split(r";\s*(?:\n|$)", sin_comentarios)
    return [p.strip() for p in partes if p.strip()]


def aplicar(ejecutor: EjecutorSQL, carpeta: Path = CARPETA) -> list[str]:
    ejecutor.ejecutar(SQL_TABLA_CONTROL)
    aplicadas = {
        f["version"]
        for f in ejecutor.ejecutar("SELECT version FROM schema_migraciones")
    }
    nuevas = []
    for fichero in sorted(carpeta.glob("*.sql")):
        version = fichero.stem
        if version in aplicadas:
            continue
        with ejecutor.transaccion():
            for sentencia in sentencias(fichero.read_text(encoding="utf-8")):
                ejecutor.ejecutar(sentencia)
            ejecutor.ejecutar(
                "INSERT INTO schema_migraciones (version) VALUES (:version)",
                {"version": version},
            )
        print(f"Aplicada {version}", file=sys.stderr)
        nuevas.append(version)
    if not nuevas:
        print("Sin migraciones pendientes", file=sys.stderr)
    return nuevas


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dsn")
    parser.add_argument("--cluster-arn")
    parser.add_argument("--secret-arn")
    parser.add_argument("--base-datos", default="fondos")
    args = parser.parse_args()

    if args.dsn:
        aplicar(EjecutorPsycopg(args.dsn))
    elif args.cluster_arn and args.secret_arn:
        aplicar(EjecutorDataAPI(args.cluster_arn, args.secret_arn, args.base_datos))
    else:
        parser.error("indica --dsn o --cluster-arn y --secret-arn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
