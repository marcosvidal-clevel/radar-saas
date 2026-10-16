
import re
from pathlib import Path

from pypdf import PdfReader
from docx import Document


class ErrorExtraccionCV(Exception):
    """Error al procesar un currículum."""


def normalizar_texto_pdf(texto):
    """
    Corrige secuencias largas de letras separadas
    artificialmente por espacios.
    """
    lineas = []

    for linea in texto.split("\n"):
        partes = re.split(r"(\s{2,})", linea)
        partes_normalizadas = []

        for parte in partes:
            if not parte or parte.isspace():
                partes_normalizadas.append(parte)
                continue

            patron = r"(?<!\S)(?:[^\W\d_]\s){3,}[^\W\d_](?!\S)"

            parte = re.sub(
                patron,
                lambda coincidencia: re.sub(
                    r"\s+",
                    "",
                    coincidencia.group(0),
                ),
                parte,
                flags=re.UNICODE,
            )

            partes_normalizadas.append(parte)

        lineas.append("".join(partes_normalizadas))

    return "\n".join(lineas)


def extraer_texto_pdf(archivo):
    """Extrae texto de PDF usando preferentemente su disposición visual."""
    lector = PdfReader(archivo, strict=False)
    paginas = []

    for pagina in lector.pages:
        try:
            texto = pagina.extract_text(extraction_mode="layout") or ""
        except (ValueError, TypeError, NotImplementedError):
            texto = pagina.extract_text() or ""

        if texto.strip():
            paginas.append(
                normalizar_texto_pdf(texto.strip())
            )

    return "\n\n".join(paginas)


def extraer_texto_docx(archivo):
    """Extrae párrafos y tablas de un DOCX."""
    documento = Document(archivo)
    textos = []

    for parrafo in documento.paragraphs:
        if parrafo.text.strip():
            textos.append(parrafo.text.strip())

    for tabla in documento.tables:
        for fila in tabla.rows:
            for celda in fila.cells:
                if celda.text.strip():
                    textos.append(celda.text.strip())

    return "\n\n".join(textos)


def extraer_texto_cv(archivo, nombre_archivo):
    """Selecciona el lector según la extensión del archivo."""
    extension = Path(nombre_archivo).suffix.lower()

    if extension not in (".pdf", ".docx"):
        raise ErrorExtraccionCV(
            "Formato no compatible con la extracción automática."
        )

    try:
        if extension == ".pdf":
            return extraer_texto_pdf(archivo)

        return extraer_texto_docx(archivo)

    except Exception as error:
        raise ErrorExtraccionCV(
            "No fue posible extraer el texto del currículum."
        ) from error
