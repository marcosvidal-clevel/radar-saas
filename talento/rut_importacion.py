"""Identificación y validación de RUT chileno desde texto extraído."""
import re

PATRON_RUT = re.compile(r"(?<![0-9])([0-9]{1,2}(?:\.[0-9]{3}){2}-?[0-9kK]|[0-9]{7,8}-[0-9kK])(?![0-9])")


def normalizar_rut(valor):
    limpio = re.sub(r"[^0-9kK]", "", str(valor or "")).upper()
    if len(limpio) < 2 or not limpio[:-1].isdigit():
        return ""
    cuerpo, verificador = limpio[:-1], limpio[-1]
    suma = sum(int(digito) * (2 + indice % 6) for indice, digito in enumerate(reversed(cuerpo)))
    resto = 11 - suma % 11
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    if esperado != verificador:
        return ""
    return f"{int(cuerpo)}-{verificador}"


def extraer_rut(texto):
    for candidato in PATRON_RUT.findall(str(texto or "")[:200000]):
        rut = normalizar_rut(candidato)
        if rut:
            return rut
    return ""
