"""Orquestación inicial: preparar, crear ficha y guardar adjuntos.

La ficha se conserva aunque algún adjunto falle. Los conectores de origen deben
entregar identificadores estables y bytes de documentos ya descargados.
"""
from .almacenamiento_importacion import guardar_adjuntos_importados
from .preparacion_importacion import preparar_importacion
from .servicio_importacion import registrar_candidato_importado


def importar_candidato(*, organizacion, origen, identificador, texto="", adjuntos=()):
    adjuntos = list(adjuntos or ())
    preparado = preparar_importacion(texto=texto, adjuntos=adjuntos)
    candidato, creado, observaciones = registrar_candidato_importado(
        organizacion=organizacion,
        datos=preparado["datos"],
        origen=origen,
        identificador=identificador,
    )
    resultados = guardar_adjuntos_importados(
        candidato=candidato,
        adjuntos=adjuntos,
        origen=origen,
    )
    errores = [item for item in resultados if item["estado"] == "error"]
    return {
        "candidato_id": candidato.pk,
        "creado": creado,
        "observaciones": observaciones,
        "documentos": resultados,
        "errores_documentos": len(errores),
    }
