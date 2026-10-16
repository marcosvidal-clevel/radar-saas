
from pathlib import Path

from pypdf import PdfReader
from docx import Document


class ErrorExtraccionCV(Exception):
    """Error al procesar un currículum."""


def extraer_texto_pdf(archivo):
    """Extrae texto seleccionable de un PDF."""
    lector = PdfReader(archivo, strict=False)
    paginas = []

    for pagina in lector.pages:
        texto = pagina.extract_text() or ""

        if texto.strip():
            paginas.append(texto.strip())

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
