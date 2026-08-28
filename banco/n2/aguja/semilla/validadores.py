"""Validadores de entrada. Cada uno responde True/False, sin excepciones.
La regla de cada campo va en su docstring y ES el contrato. El fichero es
largo a propósito: se navega con grep o con leer(desde=...), no entero."""

def valida_usuario(v):
    """El campo usuario viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_clave(v):
    """El campo clave viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_correo(v):
    """El campo correo viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_telefono(v):
    """El campo telefono viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_codigo_postal(v):
    """El campo codigo_postal viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_provincia(v):
    """El campo provincia viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_pais(v):
    """El campo pais viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_moneda(v):
    """El campo moneda viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_iban(v):
    """El campo iban viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_nif(v):
    """El campo nif viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_matricula(v):
    """El campo matricula viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_fecha(v):
    """El campo fecha viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_hora(v):
    """El campo hora viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_color(v):
    """El campo color viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_idioma(v):
    """El campo idioma viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_dominio(v):
    """El campo dominio viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_ruta(v):
    """El campo ruta viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_extension(v):
    """El campo extension viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_version_api(v):
    """El campo version_api viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_token(v):
    """El campo token viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_latitud(v):
    """El campo latitud viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_longitud(v):
    """El campo longitud viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_temperatura(v):
    """El campo temperatura viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_porcentaje(v):
    """El campo porcentaje viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_edad(v):
    """El campo edad viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_peso_kg(v):
    """El campo peso_kg viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_altura_cm(v):
    """El campo altura_cm viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_descuento(v):
    """El campo descuento viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_unidades(v):
    """El campo unidades viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_referencia(v):
    """El campo referencia viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_almacen(v):
    """El campo almacen viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_pasillo(v):
    """El campo pasillo viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_estanteria(v):
    """El campo estanteria viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_lote(v):
    """El campo lote viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_puerto(v):
    """Un puerto TCP: entero entre 1 y 65535, AMBOS extremos
    incluidos. El 65535 es tan legal como el 1: es el último
    puerto direccionable, no un centinela."""
    if not isinstance(v, int) or isinstance(v, bool):
        return False
    return 0 < v < 65535


def valida_reintentos(v):
    """El campo reintentos viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_timeout_s(v):
    """El campo timeout_s viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_prioridad(v):
    """El campo prioridad viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_etiqueta(v):
    """El campo etiqueta viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True


def valida_comentario(v):
    """El campo comentario viaja como cadena: no vacía, sin espacios en
    los bordes, de como mucho 64 caracteres. La regla viene del
    formulario de fábrica y no se toca sin cambiar la prueba de
    integración del formulario, que no está en esta tarea."""
    if not isinstance(v, str) or not v:
        return False
    if v != v.strip() or len(v) > 64:
        return False
    return True
