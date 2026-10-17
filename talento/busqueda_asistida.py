import re

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q


LIMITE_CONSULTA = 1000

# Equivalencias deliberadamente pequeñas: solo expresiones que nombran la
# misma profesión, no competencias cercanas ni industrias relacionadas.
SINONIMOS_PROFESIONALES = {
    "prevencionista": ("prevencionista", "prevención de riesgos"),
    "prevención de riesgos": ("prevencionista", "prevención de riesgos"),
}
MARCADORES_DESEABLES = {"idealmente", "preferentemente", "ojalá", "ojala", "deseable"}
MARCADORES_NEGACION = {"sin", "no", "excepto", "excluir", "excluyendo"}
MARCADORES_FORMACION = {"formación", "formacion", "estudios", "titulado", "titulada", "título", "titulo", "grado", "egresado", "egresada"}
MARCADORES_CAPACITACION = {"capacitación", "capacitacion", "curso", "cursos", "formación", "formacion"}
MARCADORES_PERSONA = {"persona", "candidato", "candidata", "nombre", "apellido"}
MARCADORES_PROFESION = {"profesión", "profesion", "profesional"}
MARCADORES_UBICACION = {"ubicación", "ubicacion", "lugar", "ciudad", "región", "region"}
MARCADORES_EMPRESA = {"empresa", "empleador", "empleadora", "compañía", "compania", "organización", "organizacion"}
MARCADORES_SECTOR = {"sector", "industria", "rubro", "área", "area"}
TIPOS_INSTITUCION = {
    "colegio": ("colegio",),
    "universidad": ("universidad",),
    "instituto": ("instituto",),
    "centro de formación": ("centro", "de", "formación"),
    "centro de formacion": ("centro", "de", "formacion"),
}
UNIDADES_EXPERIENCIA = {"año", "años", "ano", "anos", "mes", "meses"}

PALABRAS_CONVERSACIONALES = {
    "busco", "buscar", "necesito", "requiero", "quiero", "necesitamos",
    "un", "una", "uno", "con", "que", "tenga", "tienen", "para", "el",
    "la", "en", "de", "y", "quien", "persona", "perfil", "candidata",
    "candidato", "como", "del", "al", "a", "por", "tiene", "tienen", "es",
    "qué", "que", "quién", "quien", "existe", "existen", "alguien", "haya",
    "hayan", "alguno", "alguna", "algunos", "algunas", "trabajado", "trabajada", "trabajadas", "trabajados", "trabajó",
    "trabajo", "trabajaron",
    "cv", "curriculum", "currículum", "ha", "han", "hay", "estudiado", "estudiada", "estudió", "estudio", "menciona", "mencionado", "proyectos",
    "en", "el", "la", "los", "las", "del",
}
_TOKEN = re.compile(r'"([^"\n]+)"|([^\s]+)')


def interpretar_consulta(consulta):
    criterios = []
    deseables = []
    no_interpretado = []
    ambiguo = []
    obligatorios = []
    ubicaciones = []
    pendientes = []
    modo_deseable = False
    modo_tipo = None
    modo_capacitacion = False
    tokens = _TOKEN.findall(consulta)
    palabras = [(frase or palabra).strip(" ,.;:!?¿¡") for frase, palabra in tokens]
    palabras = _agrupar_instituciones(palabras)
    combinadas = []
    i = 0
    while i < len(palabras):
        triple = " ".join(palabras[i:i + 3]).casefold()
        if triple in SINONIMOS_PROFESIONALES:
            combinadas.append(" ".join(palabras[i:i + 3]))
            i += 3
        else:
            combinadas.append(palabras[i])
            i += 1
    palabras = combinadas
    i = 0
    while i < len(palabras):
        termino = palabras[i]
        if not termino:
            i += 1
            continue
        normalizado = termino.casefold()
        if normalizado in {"sería", "seria", "es"} and i + 1 < len(palabras) and palabras[i + 1].casefold() in MARCADORES_DESEABLES:
            if obligatorios:
                deseables.append(obligatorios.pop())
            i += 2
            continue
        if normalizado in MARCADORES_DESEABLES:
            modo_deseable = True
            i += 1
            continue
        if normalizado in {"capacitación", "capacitacion", "curso", "cursos"}:
            modo_tipo = "formación"
            modo_capacitacion = True
            i += 1
            continue
        if normalizado in {"formación", "formacion"}:
            modo_tipo = "formación"
            siguiente_formacion = next(
                (palabras[j].casefold() for j in range(i + 1, len(palabras))
                 if palabras[j].casefold() not in {"en", "de"}),
                "",
            )
            modo_capacitacion = siguiente_formacion not in {
                "ingeniería", "ingenieria", "universidad", "instituto",
                "colegio", "__institucion__:",
            }
            i += 1
            continue
        if normalizado.startswith("__institucion__:"):
            item = ("formación", termino.split(":", 1)[1])
            (deseables if modo_deseable else obligatorios).append(item[1])
            criterios.append({
                "tipo": "deseable" if modo_deseable else "formación",
                "categoria": "formación",
                "texto": item[1],
                "evidencia": "capacitación por comprobar" if modo_capacitacion else "coincidencia textual",
            })
            modo_deseable = False
            modo_tipo = None
            i += 1
            continue
        if normalizado in MARCADORES_PERSONA:
            modo_tipo = "persona"
            i += 1
            continue
        if normalizado in MARCADORES_PROFESION:
            modo_tipo = "profesión"
            i += 1
            continue
        if normalizado in MARCADORES_UBICACION:
            modo_tipo = "ubicación"
            i += 1
            continue
        if normalizado in MARCADORES_EMPRESA:
            modo_tipo = "empresa"
            i += 1
            continue
        if normalizado in MARCADORES_SECTOR:
            modo_tipo = "sector"
            i += 1
            continue
        if normalizado in MARCADORES_NEGACION:
            ambiguo.append(termino)
            modo_deseable = False
            i += 1
            continue
        if normalizado in PALABRAS_CONVERSACIONALES:
            i += 1
            continue
        siguiente = palabras[i + 1].casefold() if i + 1 < len(palabras) else ""
        if normalizado.isdigit() and siguiente in UNIDADES_EXPERIENCIA:
            item = ("experiencia", f"{termino} {palabras[i + 1]}")
            pendientes.append(f"{item[1]} (requiere comprobación)")
            i += 2
        elif normalizado in UNIDADES_EXPERIENCIA and i and palabras[i - 1].isdigit():
            i += 1
            continue
        elif normalizado in {"santiago", "region metropolitana", "región metropolitana"}:
            item = ("ubicación estructurada", termino)
        elif normalizado in SINONIMOS_PROFESIONALES:
            item = ("profesión", termino)
        elif len(termino) >= 3:
            item = (modo_tipo or "texto", termino)
        else:
            no_interpretado.append(termino)
            i += 1
            continue
        if item[0] == "ubicación estructurada":
            ubicaciones.append(termino)
        else:
            (deseables if modo_deseable else obligatorios).append(item[1])
        categoria = "ubicación" if item[0] == "ubicación estructurada" else item[0]
        criterios.append({
            "tipo": "deseable" if modo_deseable else item[0],
            "categoria": categoria,
            "texto": item[1],
            "evidencia": (
                "antecedente confirmado por campo estructurado"
                if item[0] == "ubicación estructurada"
                else "requiere comprobación"
                if item[0] == "experiencia"
                else "capacitación por comprobar"
                if item[0] == "formación" and modo_capacitacion
                else "coincidencia textual"
            ),
        })
        modo_deseable = False
        modo_tipo = None
        modo_capacitacion = False
        i += 1
    return {
        "obligatorios": obligatorios,
        "deseables": deseables,
        "criterios": criterios,
        "no_interpretado": no_interpretado,
        "ambiguo": ambiguo,
        "ubicaciones": ubicaciones,
        "pendientes": pendientes + [f"{termino} (requiere aclaración)" for termino in no_interpretado],
        "criterios_por_tipo": {
            tipo: [criterio for criterio in criterios if criterio["categoria"] == tipo]
            for tipo in {criterio["categoria"] for criterio in criterios}
        },
        "obligatorios_busqueda": [
            criterio["texto"] for criterio in criterios
            if criterio["tipo"] != "deseable"
            if criterio["categoria"] in {"persona", "profesión", "formación", "empresa", "sector", "texto"}
            and criterio["texto"] not in no_interpretado
        ],
    }


def evidencia_capacitacion(texto, termino):
    """Distingue evidencia explícita de formación de una mera mención textual."""
    texto = (texto or "").casefold()
    termino = re.escape(termino.casefold())
    patron = re.compile(
        rf"(?:curso|capacitación|capacitacion|formación|formacion|certificad[oa])"
        rf"[^.\n]{{0,100}}{termino}|{termino}[^.\n]{{0,100}}"
        rf"(?:curso|capacitación|capacitacion|formación|formacion|certificad[oa])"
    )
    if patron.search(texto):
        return "capacitación explícita"
    return "capacitación por comprobar"


def _agrupar_instituciones(palabras):
    """Agrupa tipo y nombre de institución para no perder su identidad."""
    agrupadas = []
    i = 0
    stop = {
        "y", "o", "para", "con", "que", "quien", "quién", "en", "de",
    }
    while i < len(palabras):
        normalizado = palabras[i].casefold()
        tipo = None
        longitud_tipo = 1
        for nombre, partes in TIPOS_INSTITUCION.items():
            if [p.casefold() for p in palabras[i:i + len(partes)]] == list(partes):
                tipo = nombre
                longitud_tipo = len(partes)
                break
        if tipo is None:
            agrupadas.append(palabras[i])
            i += 1
            continue
        j = i + longitud_tipo
        nombre = list(palabras[i:j])
        while j < len(palabras) and len(nombre) < longitud_tipo + 5:
            siguiente = palabras[j]
            if siguiente.casefold() in stop:
                break
            nombre.append(siguiente)
            j += 1
        if len(nombre) == longitud_tipo:
            agrupadas.extend(palabras[i:j])
            i = j
            continue
        agrupadas.append("__institucion__:" + " ".join(nombre))
        i = j
    return agrupadas


def _vector():
    return SearchVector(
        "nombre", "profesion", "especialidad", "experiencia", "competencias",
        "documentos__texto_extraido",
        config="spanish",
        weight="A",
    )


def _terminos_busqueda(termino):
    normalizado = termino.casefold()
    return SINONIMOS_PROFESIONALES.get(normalizado, (termino,))


def aplicar_busqueda_asistida(queryset, interpretacion):
    vector = _vector()
    queryset = queryset.filter(
        documentos__tipo="curriculum", documentos__vigente=True
    ).annotate(texto_busqueda=vector)
    for termino in interpretacion.get("obligatorios_busqueda", interpretacion["obligatorios"]):
        alternativas = _terminos_busqueda(termino)
        condicion = Q()
        for alternativa in alternativas:
            condicion |= Q(texto_busqueda=SearchQuery(alternativa, config="spanish", search_type="phrase"))
        queryset = queryset.filter(condicion)
    if interpretacion["deseables"]:
        deseable_query = Q()
        for termino in interpretacion["deseables"]:
            for alternativa in _terminos_busqueda(termino):
                deseable_query |= Q(texto_busqueda=SearchQuery(alternativa, config="spanish"))
        queryset = queryset.annotate(
            rank_deseables=SearchRank(vector, SearchQuery(" ".join(interpretacion["deseables"]), config="spanish"))
        ).order_by("-rank_deseables", "nombre", "pk")
    return queryset.distinct()
