"""Punto de entrada de la aplicación Streamlit."""

from dataclasses import dataclass
from math import ceil

import streamlit as st

from frontend.api_client import ClienteAPI, ErrorClienteAPI
from frontend.config import ConfiguracionFrontend

TAMANOS_PAGINA = (2, 5, 10, 20, 50, 100)
CLAVE_FILTROS = "filtros_fondos_aplicados"
CLAVE_PAGINA = "pagina_fondos"
CLAVES_WIDGETS_FILTROS = (
    "filtro_gestora",
    "filtro_isin",
    "filtro_nombre",
    "filtro_tamano_pagina",
)


@dataclass(frozen=True, slots=True)
class FiltrosFondosUI:
    """Filtros aplicados al listado de fondos."""

    gestora: str | None = None
    isin: str | None = None
    nombre: str | None = None
    tamano_pagina: int = 10


st.set_page_config(
    page_title="Consulta de fondos",
    page_icon="📊",
    layout="wide",
)


@st.cache_resource
def crear_cliente_api(base_url: str, timeout_segundos: float) -> ClienteAPI:
    """Mantiene un cliente HTTP reutilizable entre ejecuciones de Streamlit."""

    return ClienteAPI(base_url, timeout_segundos)


def mostrar_error_api(
    error: ErrorClienteAPI,
    *,
    prefijo: str | None = None,
    clave_reintento: str | None = None,
) -> None:
    """Muestra un error público y su identificador de trazabilidad."""

    mensaje = f"{prefijo}: {error}" if prefijo else str(error)
    st.error(mensaje, icon="🚨")
    if error.correlation_id:
        st.caption(f"Identificador de la petición: `{error.correlation_id}`")
    if clave_reintento and st.button(
        "Reintentar",
        key=clave_reintento,
        type="primary",
    ):
        st.rerun()


def mostrar_estado_api(cliente: ClienteAPI) -> bool:
    """Muestra la disponibilidad de la API e indica si se puede continuar."""

    st.subheader("Estado del servicio")
    try:
        with st.spinner("Comprobando la disponibilidad de la API..."):
            resultado = cliente.obtener_estado()
    except ErrorClienteAPI as error:
        mostrar_error_api(error, clave_reintento="reintentar_estado_api")
        return False

    st.success("La API está disponible.", icon="✅")
    servicio, version = st.columns(2)
    servicio.metric("Servicio", resultado.datos.servicio)
    version.metric("Versión", resultado.datos.version)
    st.caption(f"Identificador de la petición: `{resultado.correlation_id}`")
    return True


def inicializar_estado_listado() -> None:
    """Inicializa los filtros y la página conservados por Streamlit."""

    if CLAVE_FILTROS not in st.session_state:
        st.session_state[CLAVE_FILTROS] = FiltrosFondosUI()
    if CLAVE_PAGINA not in st.session_state:
        st.session_state[CLAVE_PAGINA] = 1


def mostrar_filtros(
    cliente: ClienteAPI,
    filtros_aplicados: FiltrosFondosUI,
) -> None:
    """Muestra el formulario y actualiza los filtros al enviarlo."""

    try:
        with st.spinner("Cargando gestoras..."):
            resultado_gestoras = cliente.listar_gestoras()
    except ErrorClienteAPI as error:
        mostrar_error_api(
            error,
            prefijo="No se han podido cargar las gestoras",
            clave_reintento="reintentar_gestoras",
        )
        return

    gestoras = resultado_gestoras.datos.datos
    if not gestoras:
        st.warning("No hay gestoras disponibles para utilizar como filtro.")
    codigos_gestora = [""] + [gestora.codigo for gestora in gestoras]
    nombres_gestora = {gestora.codigo: gestora.nombre for gestora in gestoras}
    nombres_gestora[""] = "Todas las gestoras"
    indice_gestora = (
        codigos_gestora.index(filtros_aplicados.gestora)
        if filtros_aplicados.gestora in codigos_gestora
        else 0
    )
    indice_tamano = TAMANOS_PAGINA.index(filtros_aplicados.tamano_pagina)

    with st.form("formulario_filtros_fondos"):
        gestora_columna, isin_columna = st.columns(2)
        gestora = gestora_columna.selectbox(
            "Gestora",
            codigos_gestora,
            index=indice_gestora,
            format_func=nombres_gestora.__getitem__,
            key="filtro_gestora",
        )
        isin = isin_columna.text_input(
            "ISIN exacto",
            value=filtros_aplicados.isin or "",
            max_chars=12,
            placeholder="ES0000000001",
            key="filtro_isin",
        )

        nombre_columna, tamano_columna = st.columns((3, 1))
        nombre = nombre_columna.text_input(
            "Nombre del fondo",
            value=filtros_aplicados.nombre or "",
            max_chars=200,
            key="filtro_nombre",
        )
        tamano_pagina = tamano_columna.selectbox(
            "Resultados por página",
            TAMANOS_PAGINA,
            index=indice_tamano,
            key="filtro_tamano_pagina",
        )
        buscar = st.form_submit_button("Buscar", type="primary")

    if st.button("Limpiar filtros"):
        for clave in CLAVES_WIDGETS_FILTROS:
            st.session_state.pop(clave, None)
        st.session_state[CLAVE_FILTROS] = FiltrosFondosUI()
        st.session_state[CLAVE_PAGINA] = 1
        st.rerun()

    if buscar:
        st.session_state[CLAVE_FILTROS] = FiltrosFondosUI(
            gestora=gestora or None,
            isin=isin.strip().upper() or None,
            nombre=nombre.strip() or None,
            tamano_pagina=tamano_pagina,
        )
        st.session_state[CLAVE_PAGINA] = 1
        st.rerun()


def mostrar_paginacion(pagina: int, total_paginas: int) -> None:
    """Muestra los controles que modifican la página activa."""

    anterior, indicador, siguiente = st.columns((1, 2, 1))
    if anterior.button(
        "← Anterior",
        disabled=pagina <= 1,
        width="stretch",
    ):
        st.session_state[CLAVE_PAGINA] = pagina - 1
        st.rerun()

    indicador.markdown(
        f"<p style='text-align:center'>Página {pagina} de {total_paginas}</p>",
        unsafe_allow_html=True,
    )

    if siguiente.button(
        "Siguiente →",
        disabled=pagina >= total_paginas,
        width="stretch",
    ):
        st.session_state[CLAVE_PAGINA] = pagina + 1
        st.rerun()


def formatear_porcentaje(valor: float | None) -> str:
    """Formatea un porcentaje conservando la ausencia de datos."""

    return "No disponible" if valor is None else f"{valor:.2f} %".replace(".", ",")


def formatear_periodo(valor: float | None) -> str:
    """Formatea el periodo de mantenimiento recomendado."""

    if valor is None:
        return "No disponible"
    valor_formateado = f"{valor:g}".replace(".", ",")
    return f"{valor_formateado} años"


def mostrar_historico_kids(cliente: ClienteAPI, isin: str) -> None:
    """Muestra las versiones de KID asociadas a un fondo."""

    st.markdown("#### Histórico de versiones KID")
    try:
        with st.spinner("Cargando el histórico KID..."):
            resultado = cliente.listar_kids(isin=isin)
    except ErrorClienteAPI as error:
        mostrar_error_api(
            error,
            prefijo="No se ha podido cargar el histórico",
            clave_reintento=f"reintentar_historico_{isin}",
        )
        return

    respuesta = resultado.datos
    st.caption(
        f"{respuesta.paginacion.total} versiones encontradas · "
        f"Petición `{resultado.correlation_id}`"
    )
    if not respuesta.datos:
        st.info(
            "No hay versiones KID disponibles para este fondo.",
            icon="ℹ️",
        )
        return

    filas = [
        {
            "Fecha": kid.fecha_documento,
            "SRI": kid.sri,
            "Mantenimiento (años)": kid.periodo_mantenimiento_anios,
            "Gastos corrientes (%)": kid.gastos_corrientes_pct,
            "Entrada (%)": kid.costes_entrada_pct,
            "Salida (%)": kid.costes_salida_pct,
            "SHA-256": kid.documento_sha256,
        }
        for kid in respuesta.datos
    ]
    st.dataframe(
        filas,
        column_config={
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "SRI": st.column_config.NumberColumn("SRI", format="%d"),
            "Mantenimiento (años)": st.column_config.NumberColumn(
                "Mantenimiento (años)",
                format="%.2f",
            ),
            "Gastos corrientes (%)": st.column_config.NumberColumn(
                "Gastos corrientes (%)",
                format="%.2f",
            ),
            "Entrada (%)": st.column_config.NumberColumn(
                "Entrada (%)",
                format="%.2f",
            ),
            "Salida (%)": st.column_config.NumberColumn(
                "Salida (%)",
                format="%.2f",
            ),
            "SHA-256": st.column_config.TextColumn("SHA-256", width="large"),
        },
        hide_index=True,
        width="stretch",
    )

    mostradas = len(respuesta.datos)
    if mostradas < respuesta.paginacion.total:
        st.warning(
            f"Se muestran las {mostradas} versiones más recientes de "
            f"{respuesta.paginacion.total}."
        )


def mostrar_detalle_fondo(cliente: ClienteAPI, isin: str) -> None:
    """Consulta y muestra los datos ampliados de un fondo."""

    try:
        with st.spinner("Cargando el detalle del fondo..."):
            resultado = cliente.obtener_fondo(isin)
    except ErrorClienteAPI as error:
        mostrar_error_api(
            error,
            prefijo="No se ha podido cargar el detalle",
            clave_reintento=f"reintentar_detalle_{isin}",
        )
        return

    fondo = resultado.datos
    with st.container(border=True):
        st.subheader(fondo.nombre_producto)
        st.caption(
            f"Detalle del fondo · Petición `{resultado.correlation_id}`"
        )

        isin_columna, clase_columna, gestora_columna = st.columns(3)
        isin_columna.metric("ISIN", fondo.isin)
        clase_columna.metric("Clase", fondo.nombre_clase or "Sin clase")
        gestora_columna.metric("Gestora", fondo.gestora.nombre)

        fecha_ultimo_kid = (
            fondo.fecha_ultimo_kid.strftime("%d/%m/%Y")
            if fondo.fecha_ultimo_kid
            else "No disponible"
        )
        riesgo, fecha, periodo = st.columns(3)
        riesgo.metric(
            "Riesgo (SRI)",
            f"{fondo.sri} / 7" if fondo.sri is not None else "No disponible",
        )
        fecha.metric("Último KID", fecha_ultimo_kid)
        periodo.metric(
            "Mantenimiento recomendado",
            formatear_periodo(fondo.periodo_mantenimiento_anios),
        )

        st.markdown("**Costes**")
        corrientes, entrada, salida = st.columns(3)
        corrientes.metric(
            "Gastos corrientes",
            formatear_porcentaje(fondo.gastos_corrientes_pct),
        )
        entrada.metric(
            "Costes de entrada",
            formatear_porcentaje(fondo.costes_entrada_pct),
        )
        salida.metric(
            "Costes de salida",
            formatear_porcentaje(fondo.costes_salida_pct),
        )

        st.divider()
        mostrar_historico_kids(cliente, fondo.isin)


def mostrar_listado_fondos(cliente: ClienteAPI) -> None:
    """Muestra los filtros, resultados y controles de paginación."""

    st.header("Fondos")
    inicializar_estado_listado()
    filtros: FiltrosFondosUI = st.session_state[CLAVE_FILTROS]
    mostrar_filtros(cliente, filtros)

    pagina: int = st.session_state[CLAVE_PAGINA]
    try:
        with st.spinner("Cargando fondos..."):
            resultado = cliente.listar_fondos(
                pagina=pagina,
                tamano_pagina=filtros.tamano_pagina,
                gestora=filtros.gestora,
                isin=filtros.isin,
                nombre=filtros.nombre,
            )
    except ErrorClienteAPI as error:
        mostrar_error_api(error, clave_reintento="reintentar_listado_fondos")
        return

    respuesta = resultado.datos
    total_paginas = max(1, ceil(respuesta.paginacion.total / filtros.tamano_pagina))
    if pagina > total_paginas:
        st.session_state[CLAVE_PAGINA] = total_paginas
        st.rerun()

    st.caption(
        f"{respuesta.paginacion.total} fondos encontrados · "
        f"Petición `{resultado.correlation_id}`"
    )
    isin_seleccionado: str | None = None
    if not respuesta.datos:
        st.info(
            "No hay fondos que coincidan con los filtros seleccionados. "
            "Prueba a retirar alguno de ellos.",
            icon="ℹ️",
        )
    else:
        st.caption("Selecciona una fila para consultar el detalle del fondo.")
        filas = [
            {
                "ISIN": fondo.isin,
                "Fondo": fondo.nombre_producto,
                "Clase": fondo.nombre_clase or "—",
                "Gestora": fondo.gestora.nombre,
                "SRI": fondo.sri,
                "Último KID": fondo.fecha_ultimo_kid,
            }
            for fondo in respuesta.datos
        ]
        evento_tabla = st.dataframe(
            filas,
            column_config={
                "SRI": st.column_config.NumberColumn(
                    "Riesgo (SRI)",
                    help="Indicador de riesgo entre 1 y 7.",
                    format="%d",
                ),
                "Último KID": st.column_config.DateColumn(
                    "Último KID",
                    format="DD/MM/YYYY",
                ),
            },
            hide_index=True,
            key=f"tabla_fondos_{pagina}_{hash(filtros)}",
            on_select="rerun",
            selection_mode="single-row",
            width="stretch",
        )
        if evento_tabla.selection.rows:
            indice_seleccionado = evento_tabla.selection.rows[0]
            if 0 <= indice_seleccionado < len(respuesta.datos):
                isin_seleccionado = respuesta.datos[indice_seleccionado].isin

    mostrar_paginacion(pagina, total_paginas)
    if isin_seleccionado:
        st.divider()
        mostrar_detalle_fondo(cliente, isin_seleccionado)


def main() -> None:
    """Construye la página inicial de la aplicación."""

    st.title("Consulta de fondos de inversión")
    st.write(
        "Consulta los fondos y las versiones de sus documentos KID "
        "procesados por el pipeline."
    )

    try:
        configuracion = ConfiguracionFrontend.desde_entorno()
    except ValueError as error:
        st.error(f"Configuración no válida: {error}", icon="🚨")
        st.stop()

    cliente = crear_cliente_api(
        configuracion.api_base_url,
        configuracion.api_timeout_segundos,
    )
    if not mostrar_estado_api(cliente):
        st.stop()

    st.divider()
    mostrar_listado_fondos(cliente)


if __name__ == "__main__":
    main()
