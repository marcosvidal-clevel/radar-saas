
from pathlib import Path
from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db import IntegrityError
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from core.models import Membresia, Organizacion
from .forms import ActualizarPostulacionForm, CandidatoForm, CandidatoVacanteForm, DocumentoAntecedenteForm, EntrevistaForm, PostulacionForm, VacanteEdicionForm, VacanteForm
from .models import Candidato, DocumentoCandidato, Entrevista, HistorialEstadoPostulacion, Postulacion, Vacante, guardar_postulacion_con_historial
from .busqueda_asistida import (
    LIMITE_CONSULTA,
    aplicar_busqueda_asistida,
    evidencia_capacitacion,
    interpretar_consulta,
    resaltar_coincidencias,
    terminos_para_resaltado,
)


def _administrador_candidatos():
    return admin.site._registry[Candidato]


def _documentos_consultables(request, candidato):
    if not request.user.has_perm("talento.view_documentocandidato"):
        return DocumentoCandidato.objects.none()

    documentos = DocumentoCandidato.objects.filter(
        candidato=candidato,
    ).select_related("candidato")

    if request.user.is_superuser:
        return documentos

    membresia = Membresia.objects.filter(
        usuario=request.user,
        organizacion_id=candidato.organizacion_id,
        organizacion__activa=True,
        activa=True,
        rol__in=(
            Membresia.Rol.ADMINISTRADOR,
            Membresia.Rol.SUPERVISOR,
            Membresia.Rol.COLABORADOR,
        ),
    ).exists()

    if not membresia:
        return DocumentoCandidato.objects.none()

    documentos = documentos.exclude(tipo=DocumentoCandidato.Tipo.EVALUACION)
    puede_clasificar = (
        request.user.has_perm("talento.change_documentocandidato")
        and Membresia.objects.filter(
            usuario=request.user,
            organizacion_id=candidato.organizacion_id,
            organizacion__activa=True,
            activa=True,
            rol__in=(Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR),
        ).exists()
    )
    if not puede_clasificar:
        documentos = documentos.filter(pendiente_clasificacion=False)
    return documentos


def _organizaciones_gestion(request, administrador):
    return Organizacion.objects.filter(
        pk__in=Membresia.objects.filter(
            usuario=request.user,
            activa=True,
            organizacion__activa=True,
            rol__in=administrador.ROLES_GESTION,
        ).values("organizacion")
    )


def _guardar_cv_principal(candidato, archivo):
    documentos = candidato.documentos.filter(
        tipo=DocumentoCandidato.Tipo.CURRICULUM,
        vigente=True,
    ).order_by("-creado_en", "-pk")
    documento = documentos.filter(es_cv_principal=True).first()
    archivo_anterior = None

    for anterior in documentos:
        if anterior.pk != getattr(documento, "pk", None):
            anterior.vigente = False
            anterior.save(update_fields=("vigente", "actualizado_en"))

    if documento is None:
        documento = DocumentoCandidato(
            candidato=candidato,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre=f"CV de {candidato.nombre}",
            es_cv_principal=True,
            vigente=True,
        )
    elif documento.archivo:
        archivo_anterior = (
            documento.archivo.storage,
            documento.archivo.name,
        )

    documento.archivo = archivo
    documento.nombre = f"CV de {candidato.nombre}"
    documento.save()
    return documento, archivo_anterior


def _validar_permisos_cv(request, candidato, administrador_documentos):
    documentos_vigentes = candidato.documentos.filter(
        tipo=DocumentoCandidato.Tipo.CURRICULUM,
        vigente=True,
    ).order_by("-creado_en", "-pk")
    principal = documentos_vigentes.filter(es_cv_principal=True).first()

    if principal is None:
        if not administrador_documentos.has_add_permission(request):
            raise PermissionDenied(
                "No tienes permiso para agregar documentos de candidatos."
            )
    for documento in documentos_vigentes:
        if not administrador_documentos.has_change_permission(
            request,
            documento,
        ):
            raise PermissionDenied(
                "No tienes permiso para actualizar los documentos del candidato."
            )


def _puede_agregar_antecedente(request, candidato):
    return (
        request.user.is_staff
        and request.user.has_perm("talento.view_candidato")
        and request.user.has_perm("talento.add_documentocandidato")
        and Membresia.objects.filter(
            usuario=request.user,
            organizacion_id=candidato.organizacion_id,
            organizacion__activa=True,
            activa=True,
            rol__in=(Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR),
        ).exists()
    )


@login_required(login_url="admin:login")
@require_GET
def candidatos(request):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Talento.")

    queryset = administrador.get_queryset(request).select_related("organizacion")
    incluir_pruebas = request.GET.get("incluir_pruebas") == "1"
    if not incluir_pruebas:
        queryset = queryset.filter(es_prueba=False, consolidado_en__isnull=True)
    opciones = {}
    for campo in ("profesion", "especialidad", "region", "estado"):
        opciones[campo] = list(
            queryset.exclude(**{campo: ""})
            .values_list(campo, flat=True)
            .distinct()
            .order_by(campo)
        )

    busqueda = request.GET.get("q", "").strip()
    modo_busqueda = request.GET.get("modo_busqueda", "normal")
    error_busqueda = ""
    interpretacion = None
    if len(busqueda) > LIMITE_CONSULTA:
        error_busqueda = f"La consulta no puede superar {LIMITE_CONSULTA} caracteres."
    elif busqueda and modo_busqueda == "asistida":
        interpretacion = interpretar_consulta(busqueda)
        if interpretacion["ambiguo"]:
            error_busqueda = "La consulta contiene una negación ambigua; reformúlala sin exclusiones implícitas."
        else:
            queryset = aplicar_busqueda_asistida(queryset, interpretacion)
            for ubicacion in interpretacion["ubicaciones"]:
                queryset = queryset.filter(
                    Q(ciudad__iexact=ubicacion) | Q(region__iexact=ubicacion)
                )
    elif busqueda:
        queryset, _ = administrador.get_search_results(request, queryset, busqueda)

    filtros = {}
    for campo in opciones:
        valor = request.GET.get(campo, "").strip()
        if valor in set(opciones[campo]):
            filtros[campo] = valor

    for campo, valor in filtros.items():
        queryset = queryset.filter(**{campo: valor})

    queryset = queryset.order_by("nombre", "pk").distinct()
    paginador = Paginator(queryset, 20)
    pagina = paginador.get_page(request.GET.get("pagina"))
    if interpretacion and any(
        criterio["evidencia"] == "capacitación por comprobar"
        for criterio in interpretacion["criterios"]
    ):
        terminos_formacion = [
            criterio["texto"]
            for criterio in interpretacion["criterios"]
            if criterio["evidencia"] == "capacitación por comprobar"
        ]
        for candidato in pagina.object_list:
            textos_cv = candidato.documentos.filter(
                tipo="curriculum", vigente=True
            ).values_list("texto_extraido", flat=True)
            candidato.capacitacion_evidencia = max(
                (
                    evidencia_capacitacion(texto, termino)
                    for texto in textos_cv
                    for termino in terminos_formacion
                ),
                default="capacitación por comprobar",
            )

    parametros = {"q": busqueda} if busqueda else {}
    if modo_busqueda == "asistida":
        parametros["modo_busqueda"] = "asistida"
    if incluir_pruebas:
        parametros["incluir_pruebas"] = "1"
    parametros.update(filtros)
    estados = dict(Candidato.Estado.choices)

    return render(
        request,
        "talento/candidatos.html",
        {
            "pagina_candidatos": pagina,
            "busqueda": busqueda,
            "puede_crear": administrador.has_add_permission(request),
            "opciones_profesion": opciones["profesion"],
            "opciones_especialidad": opciones["especialidad"],
            "opciones_region": opciones["region"],
            "opciones_estado": [
                (valor, estados[valor])
                for valor in opciones["estado"]
            ],
            "filtro_profesion": filtros.get("profesion", ""),
            "filtro_especialidad": filtros.get("especialidad", ""),
            "filtro_region": filtros.get("region", ""),
            "filtro_estado": filtros.get("estado", ""),
            "parametros_filtros": urlencode(parametros),
            "total_resultados": paginador.count,
            "modo_busqueda": modo_busqueda,
            "error_busqueda": error_busqueda,
            "interpretacion": interpretacion,
            "limite_consulta": LIMITE_CONSULTA,
            "hay_filtros": bool(parametros),
            "incluir_pruebas": incluir_pruebas,
        },
    )


@login_required(login_url="admin:login")
@require_GET
def coincidencias_candidato(request, pk):
    administrador = _administrador_candidatos()
    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Talento.")
    candidato = get_object_or_404(
        administrador.get_queryset(request).select_related("organizacion"),
        pk=pk,
    )
    if not administrador.has_view_permission(request, candidato):
        raise PermissionDenied("No tienes acceso a este candidato.")

    consulta = request.GET.get("q", "").strip()[:LIMITE_CONSULTA]
    modo = request.GET.get("modo_busqueda", "normal")
    interpretacion = (
        interpretar_consulta(consulta) if modo == "asistida" and consulta else None
    )
    terminos = terminos_para_resaltado(consulta, modo, interpretacion)
    documentos = _documentos_consultables(request, candidato).filter(
        tipo=DocumentoCandidato.Tipo.CURRICULUM,
        vigente=True,
    ).order_by("nombre", "pk")
    documentos_con_texto = []
    for documento in documentos:
        if documento.texto_extraido:
            documento.texto_resaltado = resaltar_coincidencias(
                documento.texto_extraido,
                [termino for termino in terminos if termino.casefold() in documento.texto_extraido.casefold()],
            )
        else:
            documento.texto_resaltado = ""
        documentos_con_texto.append(documento)
    return render(
        request,
        "talento/coincidencias_candidato.html",
        {
            "candidato": candidato,
            "documentos": documentos_con_texto,
            "consulta": consulta,
            "terminos": [
                termino for termino in terminos
                if any(termino.casefold() in (documento.texto_extraido or "").casefold() for documento in documentos_con_texto)
            ],
            "interpretacion": interpretacion,
        },
    )


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def nuevo_candidato(request):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_add_permission(request):
        raise PermissionDenied("No tienes permiso para crear candidatos.")

    formulario = CandidatoForm(
        request.POST or None,
        request.FILES or None,
        organizaciones=_organizaciones_gestion(request, administrador),
    )

    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data.pop("cv", None)
        if archivo and not admin.site._registry[
            DocumentoCandidato
        ].has_add_permission(request):
            raise PermissionDenied(
                "No tienes permiso para agregar documentos de candidatos."
            )
        try:
            with transaction.atomic():
                candidato = formulario.save()
                if archivo:
                    DocumentoCandidato.objects.create(
                        candidato=candidato,
                        tipo=DocumentoCandidato.Tipo.CURRICULUM,
                        nombre=f"CV de {candidato.nombre}",
                        archivo=archivo,
                        es_cv_principal=True,
                        vigente=True,
                    )
        except Exception as error:
            if hasattr(error, "message_dict"):
                for campo, errores in error.message_dict.items():
                    for mensaje in errores:
                        formulario.add_error(campo, mensaje)
            else:
                formulario.add_error(
                    "cv" if archivo else None,
                    "No se pudo guardar el candidato o su CV.",
                )
        else:
            messages.success(request, "Candidato creado correctamente.")
            return redirect("talento_detalle_candidato", pk=candidato.pk)

    return render(
        request,
        "talento/nuevo_candidato.html",
        {"formulario": formulario},
    )


@login_required(login_url="admin:login")
@require_GET
def detalle_candidato(request, pk):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Talento.")

    candidatos_permitidos = administrador.get_queryset(request).select_related(
        "organizacion",
    )
    candidato = get_object_or_404(candidatos_permitidos, pk=pk)

    if not administrador.has_view_permission(request, candidato):
        raise PermissionDenied("No tienes acceso a este candidato.")

    puede_editar = administrador.has_change_permission(request, candidato)
    puede_agregar_antecedente = _puede_agregar_antecedente(request, candidato)

    return render(
        request,
        "talento/detalle_candidato.html",
        {
            "candidato": candidato,
            "documentos": _documentos_consultables(request, candidato).filter(
                vigente=True,
            ),
            "documentos_historicos": _documentos_consultables(
                request,
                candidato,
            ).filter(vigente=False),
            "puede_editar": puede_editar,
            "puede_agregar_antecedente": puede_agregar_antecedente,
        },
    )


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def agregar_antecedente(request, pk):
    administrador_candidatos = _administrador_candidatos()
    administrador_documentos = admin.site._registry[DocumentoCandidato]

    if not request.user.is_staff or not administrador_candidatos.has_view_permission(request):
        raise PermissionDenied("No tienes permiso para consultar candidatos.")
    candidato = get_object_or_404(
        administrador_candidatos.get_queryset(request).select_related("organizacion"),
        pk=pk,
    )
    if not administrador_candidatos.has_view_permission(request, candidato):
        raise PermissionDenied("No tienes permiso para consultar este candidato.")
    if not administrador_documentos.has_add_permission(request):
        raise PermissionDenied("No tienes permiso para agregar documentos de candidatos.")
    if not _puede_agregar_antecedente(request, candidato):
        raise PermissionDenied("No tienes un rol de gestión activo en esta organización.")

    formulario = DocumentoAntecedenteForm(
        request.POST or None,
        request.FILES or None,
        candidato=candidato,
    )
    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data["archivo"]
        documento = formulario.save(commit=False)
        documento.candidato = candidato
        documento.agregado_por = request.user
        documento.es_cv_principal = False
        documento.vigente = True
        documento.pendiente_clasificacion = False
        archivos_nuevos = []
        try:
            with transaction.atomic():
                documento.save()
                archivos_nuevos.append(
                    (documento.archivo.storage, documento.archivo.name)
                )
        except Exception as error:
            for storage, nombre in archivos_nuevos:
                storage.delete(nombre)
            if hasattr(error, "message_dict"):
                for campo, errores in error.message_dict.items():
                    for mensaje in errores:
                        formulario.add_error(campo, mensaje)
            else:
                formulario.add_error(None, "No se pudo guardar el antecedente.")
        else:
            messages.success(request, "Antecedente agregado correctamente.")
            return redirect("talento_detalle_candidato", pk=candidato.pk)

    return render(
        request,
        "talento/agregar_antecedente.html",
        {"formulario": formulario, "candidato": candidato},
    )


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def editar_candidato(request, pk):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Talento.")

    candidato = get_object_or_404(
        administrador.get_queryset(request).select_related("organizacion"),
        pk=pk,
    )
    if not administrador.has_change_permission(request, candidato):
        raise PermissionDenied("No tienes permiso para editar este candidato.")

    formulario = CandidatoForm(
        request.POST or None,
        request.FILES or None,
        instance=candidato,
        organizaciones=_organizaciones_gestion(request, administrador),
    )
    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data.pop("cv", None)
        archivos_nuevos = []
        archivos_anteriores = []
        if archivo:
            _validar_permisos_cv(
                request,
                candidato,
                admin.site._registry[DocumentoCandidato],
            )
        try:
            with transaction.atomic():
                candidato = formulario.save()
                if archivo:
                    documento, anterior = _guardar_cv_principal(
                        candidato,
                        archivo,
                    )
                    archivos_nuevos.append(
                        (documento.archivo.storage, documento.archivo.name)
                    )
                    if anterior:
                        archivos_anteriores.append(anterior)
                        transaction.on_commit(
                            lambda storage=anterior[0], nombre=anterior[1]:
                            storage.delete(nombre)
                        )
        except Exception as error:
            for storage, nombre in archivos_nuevos:
                storage.delete(nombre)
            if hasattr(error, "message_dict"):
                for campo, errores in error.message_dict.items():
                    for mensaje in errores:
                        formulario.add_error(campo, mensaje)
            else:
                formulario.add_error(
                    "cv" if archivo else None,
                    "No se pudo actualizar el candidato o su CV.",
                )
        else:
            messages.success(request, "Candidato actualizado correctamente.")
            return redirect("talento_detalle_candidato", pk=candidato.pk)

    return render(
        request,
        "talento/nuevo_candidato.html",
        {"formulario": formulario, "candidato": candidato},
    )


@login_required
@require_GET
def descargar_documento_candidato(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied(
            "No tienes autorización para descargar documentos."
        )

    if not request.user.has_perm(
        "talento.view_documentocandidato"
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar documentos."
        )

    documento = get_object_or_404(
        DocumentoCandidato.objects.select_related(
            "candidato__organizacion"
        ),
        pk=pk,
    )

    if not request.user.is_superuser:
        membresia = Membresia.objects.filter(
            usuario=request.user,
            organizacion_id=documento.candidato.organizacion_id,
            organizacion__activa=True,
            activa=True,
            rol__in=(
                Membresia.Rol.ADMINISTRADOR,
                Membresia.Rol.SUPERVISOR,
                Membresia.Rol.COLABORADOR,
            ),
        ).exists()

        if not membresia:
            raise PermissionDenied(
                "No tienes acceso a documentos de esta organización."
            )

        if documento.tipo == DocumentoCandidato.Tipo.EVALUACION:
            raise PermissionDenied(
                "Este documento tiene acceso restringido."
            )

        puede_clasificar = (
            documento.pendiente_clasificacion
            and request.user.has_perm("talento.change_documentocandidato")
            and Membresia.objects.filter(
                usuario=request.user,
                organizacion_id=documento.candidato.organizacion_id,
                organizacion__activa=True,
                activa=True,
                rol__in=(Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR),
            ).exists()
        )
        if documento.pendiente_clasificacion and not puede_clasificar:
            raise PermissionDenied("Este documento requiere clasificación autorizada.")

    if not documento.archivo:
        raise Http404("El documento no tiene archivo asociado.")

    try:
        archivo = documento.archivo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("El archivo solicitado no está disponible.")

    nombre_descarga = (
        Path(documento.archivo.name).name
    )

    return FileResponse(
        archivo,
        as_attachment=True,
        filename=nombre_descarga,
    )


def _administrador_seleccion(modelo):
    return admin.site._registry[modelo]


def _entrevistas_autorizadas(request):
    administrador = _administrador_seleccion(Entrevista)
    if not request.user.has_perm("talento.view_entrevista") or not administrador.has_view_permission(request):
        return Entrevista.objects.none()
    return administrador.get_queryset(request).select_related("postulacion__candidato", "postulacion__vacante")


def _vacantes_autorizadas(request):
    administrador = _administrador_seleccion(Vacante)
    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Selección.")
    return administrador.get_queryset(request).select_related(
        "organizacion", "empresa", "oportunidad",
    )


def _candidatos_postulables(request, vacante):
    administrador = _administrador_candidatos()
    if not request.user.has_perm("talento.view_candidato"):
        return Candidato.objects.none()
    return administrador.get_queryset(request).filter(
        organizacion_id=vacante.organizacion_id,
    )


@login_required(login_url="admin:login")
@require_GET
def inicio_seleccion(request):
    administrador_vacantes = _administrador_seleccion(Vacante)
    administrador_postulaciones = _administrador_seleccion(Postulacion)
    administrador_entrevistas = _administrador_seleccion(Entrevista)

    puede_ver_vacantes = (
        request.user.has_perm("talento.view_vacante")
        and administrador_vacantes.has_view_permission(request)
    )
    puede_ver_postulaciones = (
        request.user.has_perm("talento.view_postulacion")
        and administrador_postulaciones.has_view_permission(request)
    )
    puede_ver_entrevistas = (
        request.user.has_perm("talento.view_entrevista")
        and administrador_entrevistas.has_view_permission(request)
    )
    if not (puede_ver_vacantes or puede_ver_postulaciones or puede_ver_entrevistas):
        raise PermissionDenied("No tienes acceso a Selección.")

    vacantes_abiertas = []
    if puede_ver_vacantes:
        vacantes_abiertas = list(
            administrador_vacantes.get_queryset(request)
            .filter(estado=Vacante.Estado.ABIERTA, activa=True)
            .select_related("organizacion")
            .order_by("-creada_en", "-pk")[:10]
        )

    conteos_postulaciones = {}
    if puede_ver_postulaciones:
        conteos_postulaciones = {
            fila["estado"]: fila["total"]
            for fila in administrador_postulaciones.get_queryset(request)
            .values("estado")
            .annotate(total=Count("pk"))
        }
    resumen_etapas = [
        {"valor": valor, "etiqueta": etiqueta, "total": conteos_postulaciones.get(valor, 0)}
        for valor, etiqueta in Postulacion.Estado.choices
    ]

    entrevistas_programadas = []
    entrevistas_pendientes = []
    if puede_ver_entrevistas:
        entrevistas_autorizadas = administrador_entrevistas.get_queryset(request).select_related(
            "postulacion__candidato", "postulacion__vacante",
        )
        ahora = timezone.now()
        entrevistas_programadas = list(
            entrevistas_autorizadas
            .filter(estado=Entrevista.Estado.PROGRAMADA, fecha_hora__gte=ahora)
            .order_by("fecha_hora", "pk")[:10]
        )
        entrevistas_pendientes = list(
            entrevistas_autorizadas
            .filter(estado=Entrevista.Estado.REALIZADA)
            .filter(
                Q(resultado__isnull=True)
                | Q(resultado="")
                | Q(resultado__regex=r"^\s*$")
                | Q(recomendacion__isnull=True)
                | Q(recomendacion="")
                | ~Q(recomendacion__in=(
                    Entrevista.Recomendacion.CONTINUAR,
                    Entrevista.Recomendacion.NO_CONTINUAR,
                    Entrevista.Recomendacion.RESERVA,
                ))
            )
            .order_by("-fecha_hora", "-pk")[:10]
        )

    return render(request, "talento/inicio_seleccion.html", {
        "puede_ver_vacantes": puede_ver_vacantes,
        "puede_ver_postulaciones": puede_ver_postulaciones,
        "puede_ver_entrevistas": puede_ver_entrevistas,
        "vacantes_abiertas": vacantes_abiertas,
        "resumen_etapas": resumen_etapas,
        "entrevistas_programadas": entrevistas_programadas,
        "entrevistas_pendientes": entrevistas_pendientes,
    })


@login_required(login_url="admin:login")
@require_GET
def vacantes(request):
    queryset = _vacantes_autorizadas(request)
    busqueda = request.GET.get("q", "").strip()[:200]
    estado = request.GET.get("estado", "").strip()
    estados = {valor for valor, _ in Vacante.Estado.choices}
    if busqueda:
        queryset = queryset.filter(titulo__icontains=busqueda)
    if estado in estados:
        queryset = queryset.filter(estado=estado)
    queryset = queryset.order_by("-creada_en", "-pk")
    paginador = Paginator(queryset, 20)
    pagina = paginador.get_page(request.GET.get("pagina"))
    return render(request, "talento/vacantes.html", {
        "pagina_vacantes": pagina,
        "busqueda": busqueda,
        "filtro_estado": estado if estado in estados else "",
        "estados": Vacante.Estado.choices,
        "puede_crear": _administrador_seleccion(Vacante).has_add_permission(request),
        "total_resultados": paginador.count,
        "parametros": urlencode({"q": busqueda, "estado": estado} if busqueda or estado in estados else {}),
    })


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def nueva_vacante(request):
    administrador = _administrador_seleccion(Vacante)
    if not request.user.is_staff or not administrador.has_add_permission(request):
        raise PermissionDenied("No tienes permiso para crear vacantes.")
    formulario = VacanteForm(
        request.POST or None,
        organizaciones=Organizacion.objects.filter(
            pk__in=administrador.organizaciones_permitidas(request, administrador.ROLES_GESTION),
            activa=True,
        ),
    )
    if request.method == "POST" and formulario.is_valid():
        vacante = formulario.save()
        return redirect("seleccion_detalle_vacante", pk=vacante.pk)
    return render(request, "talento/nueva_vacante.html", {"formulario": formulario})


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def editar_vacante(request, pk):
    administrador = _administrador_seleccion(Vacante)
    if not request.user.is_staff or not request.user.has_perm("talento.view_vacante"):
        raise PermissionDenied("No tienes acceso a esta vacante.")
    vacante = get_object_or_404(_vacantes_autorizadas(request), pk=pk)
    if not administrador.has_view_permission(request, vacante):
        raise PermissionDenied("No tienes acceso a esta vacante.")
    if not request.user.has_perm("talento.change_vacante") or not administrador.has_change_permission(request, vacante):
        raise PermissionDenied("No tienes permiso para editar esta vacante.")
    formulario = VacanteEdicionForm(request.POST or None, instance=vacante)
    if request.method == "POST" and formulario.is_valid():
        try:
            with transaction.atomic():
                vacante = formulario.save()
        except ValidationError as error:
            for campo, errores in error.message_dict.items():
                for mensaje in errores:
                    formulario.add_error(campo if campo != "__all__" else None, mensaje)
        else:
            messages.success(request, "Vacante actualizada correctamente.")
            return redirect("seleccion_detalle_vacante", pk=vacante.pk)
    return render(request, "talento/nueva_vacante.html", {
        "formulario": formulario, "vacante": vacante, "edicion": True,
    })


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def nuevo_candidato_vacante(request, pk):
    vacante = get_object_or_404(_vacantes_autorizadas(request), pk=pk)
    administrador_candidatos = _administrador_candidatos()
    administrador_documentos = _administrador_seleccion(DocumentoCandidato)
    administrador_postulaciones = _administrador_seleccion(Postulacion)
    if not (
        request.user.has_perm("talento.add_candidato")
        and request.user.has_perm("talento.add_documentocandidato")
        and request.user.has_perm("talento.add_postulacion")
        and administrador_candidatos.has_add_permission(request)
        and administrador_documentos.has_add_permission(request)
        and administrador_postulaciones.has_add_permission(request)
    ):
        raise PermissionDenied("No tienes permiso para agregar candidatos a esta vacante.")

    formulario = CandidatoVacanteForm(request.POST or None, request.FILES or None)
    coincidencias = Candidato.objects.none()
    if request.method == "POST":
        candidato_existente = request.POST.get("candidato_existente")
        if candidato_existente:
            candidato_preexistente = get_object_or_404(
                administrador_candidatos.get_queryset(request).filter(
                    organizacion_id=vacante.organizacion_id,
                ),
                pk=candidato_existente,
            )
            datos = request.POST.copy()
            datos["nombre"] = candidato_preexistente.nombre
            formulario = CandidatoVacanteForm(datos, request.FILES or None)
        if formulario.is_valid():
            email = formulario.cleaned_data.get("email", "").strip()
            coincidencias = administrador_candidatos.get_queryset(request).filter(
                organizacion_id=vacante.organizacion_id,
                email__iexact=email,
            ) if email else Candidato.objects.none()
            if coincidencias.exists() and not candidato_existente:
                return render(request, "talento/nuevo_candidato_vacante.html", {
                    "vacante": vacante, "formulario": formulario,
                    "coincidencias": coincidencias,
                })
            candidato = None
            archivos_nuevos = []
            try:
                with transaction.atomic():
                    if candidato_existente:
                        candidato = get_object_or_404(coincidencias, pk=candidato_existente)
                    else:
                        candidato = formulario.save(commit=False)
                        candidato.organizacion = vacante.organizacion
                        candidato.save()
                    archivo = formulario.cleaned_data.get("cv")
                    documento = None
                    if archivo:
                        documento = DocumentoCandidato.objects.create(
                            candidato=candidato,
                            tipo=DocumentoCandidato.Tipo.CURRICULUM,
                            nombre=f"CV de {candidato.nombre}",
                            archivo=archivo,
                            es_cv_principal=not candidato_existente,
                            vigente=True,
                        )
                        archivos_nuevos.append((documento.archivo.storage, documento.archivo.name))
                    Postulacion.objects.create(
                        vacante=vacante, candidato=candidato, documento_cv=documento,
                        fuente=Postulacion.Fuente.MANUAL,
                    )
            except Exception as error:
                for storage, nombre in archivos_nuevos:
                    storage.delete(nombre)
                formulario.add_error(None, "No se pudo guardar el candidato, su CV o la postulación.")
            else:
                messages.success(request, "Candidato y postulación creados correctamente.")
                return redirect("seleccion_detalle_vacante", pk=vacante.pk)
    return render(request, "talento/nuevo_candidato_vacante.html", {
        "vacante": vacante, "formulario": formulario, "coincidencias": coincidencias,
    })


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def nueva_entrevista(request, pk):
    postulacion = get_object_or_404(
        _administrador_seleccion(Postulacion).get_queryset(request).select_related("vacante", "candidato"), pk=pk,
    )
    administrador = _administrador_seleccion(Entrevista)
    if not (request.user.has_perm("talento.view_postulacion") and request.user.has_perm("talento.add_entrevista") and request.user.has_perm("talento.view_entrevista") and _administrador_seleccion(Postulacion).has_view_permission(request, postulacion) and administrador.has_add_permission(request)):
        raise PermissionDenied("No tienes permiso para crear entrevistas.")
    formulario = EntrevistaForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        entrevista = formulario.save(commit=False)
        entrevista.postulacion = postulacion
        entrevista.creado_por = request.user
        entrevista.save()
        messages.success(request, "Entrevista creada correctamente.")
        return redirect("seleccion_detalle_vacante", pk=postulacion.vacante_id)
    return render(request, "talento/nueva_entrevista.html", {"formulario": formulario, "postulacion": postulacion})


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def editar_entrevista(request, pk):
    entrevista = get_object_or_404(_entrevistas_autorizadas(request), pk=pk)
    administrador = _administrador_seleccion(Entrevista)
    if not request.user.has_perm("talento.change_entrevista") or not administrador.has_change_permission(request, entrevista):
        raise PermissionDenied("No tienes permiso para editar entrevistas.")
    formulario = EntrevistaForm(request.POST or None, instance=entrevista)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Entrevista actualizada correctamente.")
        return redirect("seleccion_detalle_vacante", pk=entrevista.postulacion.vacante_id)
    return render(request, "talento/nueva_entrevista.html", {"formulario": formulario, "postulacion": entrevista.postulacion, "entrevista": entrevista})


@login_required(login_url="admin:login")
@require_GET
def agenda_entrevistas(request):
    administrador = _administrador_seleccion(Entrevista)
    if not request.user.has_perm("talento.view_entrevista") or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes permiso para consultar entrevistas.")
    entrevistas = administrador.get_queryset(request).select_related(
        "postulacion__candidato", "postulacion__vacante",
    )
    estado = request.GET.get("estado", "")
    estados = {valor for valor, _ in Entrevista.Estado.choices}
    if estado in estados:
        entrevistas = entrevistas.filter(estado=estado)
    else:
        estado = ""
    fecha_desde = request.GET.get("desde", "")
    fecha_hasta = request.GET.get("hasta", "")
    if fecha_desde:
        entrevistas = entrevistas.filter(fecha_hora__date__gte=fecha_desde)
    if fecha_hasta:
        entrevistas = entrevistas.filter(fecha_hora__date__lte=fecha_hasta)
    paginator = Paginator(entrevistas.order_by("fecha_hora", "pk"), 20)
    return render(request, "talento/agenda_entrevistas.html", {"pagina_entrevistas": paginator.get_page(request.GET.get("pagina")), "estado": estado, "desde": fecha_desde, "hasta": fecha_hasta, "estados": Entrevista.Estado.choices})


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def detalle_vacante(request, pk):
    vacante = get_object_or_404(_vacantes_autorizadas(request), pk=pk)
    administrador_vacantes = _administrador_seleccion(Vacante)
    administrador_postulaciones = _administrador_seleccion(Postulacion)
    postulaciones = Postulacion.objects.none()
    puede_postular = False
    puede_crear_entrevista = False
    formulario = None
    estados_postulacion = Postulacion.Estado.choices
    etapa = request.GET.get("etapa", request.POST.get("etapa", ""))
    if etapa not in {valor for valor, _ in estados_postulacion}:
        etapa = ""
    resumen_postulaciones = {}
    total_postulaciones = None
    puede_editar_vacante = (
        request.user.has_perm("talento.view_vacante")
        and request.user.has_perm("talento.change_vacante")
        and administrador_vacantes.has_view_permission(request, vacante)
        and administrador_vacantes.has_change_permission(request, vacante)
    )
    formularios_actualizacion = {}
    puede_consultar_postulaciones = (
        request.user.has_perm("talento.view_postulacion")
        and administrador_postulaciones.has_view_permission(request)
    )
    if puede_consultar_postulaciones:
        postulaciones_autorizadas = administrador_postulaciones.get_queryset(request).filter(
            vacante=vacante,
        )
        total_postulaciones = postulaciones_autorizadas.count()
        resumen_postulaciones = {
            fila["estado"]: fila["total"]
            for fila in postulaciones_autorizadas.values("estado").annotate(total=Count("pk"))
        }
        postulaciones = postulaciones_autorizadas.filter(
            estado=etapa,
        ).select_related("candidato", "documento_cv") if etapa else postulaciones_autorizadas.select_related("candidato", "documento_cv")
        postulaciones = postulaciones.prefetch_related("historial_estados__usuario", "entrevistas")
        puede_postular = administrador_postulaciones.has_add_permission(request) and request.user.has_perm("talento.view_candidato")
        administrador_entrevistas = _administrador_seleccion(Entrevista)
        puede_crear_entrevista = (
            request.user.has_perm("talento.view_entrevista")
            and request.user.has_perm("talento.add_entrevista")
            and administrador_entrevistas.has_add_permission(request)
        )
        for postulacion in postulaciones:
            if administrador_postulaciones.has_view_permission(request, postulacion):
                formulario_actualizacion = ActualizarPostulacionForm(instance=postulacion)
                formularios_actualizacion[postulacion.pk] = formulario_actualizacion
                postulacion.formulario_actualizacion = formulario_actualizacion
    if request.method == "POST":
        if request.POST.get("accion") == "actualizar_postulacion":
            if not puede_consultar_postulaciones:
                raise PermissionDenied("No tienes permiso para consultar postulaciones.")
            postulacion = get_object_or_404(postulaciones, pk=request.POST.get("postulacion"))
            if not request.user.has_perm("talento.change_postulacion") or not administrador_postulaciones.has_change_permission(request, postulacion):
                raise PermissionDenied("No tienes permiso para actualizar esta postulación.")
            formulario_actualizacion = ActualizarPostulacionForm(request.POST, instance=postulacion)
            formularios_actualizacion[postulacion.pk] = formulario_actualizacion
            postulacion.formulario_actualizacion = formulario_actualizacion
            if formulario_actualizacion.is_valid():
                postulacion = formulario_actualizacion.save(commit=False)
                guardar_postulacion_con_historial(postulacion, request.user)
                messages.success(request, "Postulación actualizada correctamente.")
                destino = reverse("seleccion_detalle_vacante", args=[vacante.pk])
                if etapa:
                    destino = f"{destino}?{urlencode({'etapa': etapa})}"
                return redirect(destino)
        else:
            if not puede_postular:
                raise PermissionDenied("No tienes permiso para vincular candidatos.")
            candidatos = _candidatos_postulables(request, vacante)
            documentos = DocumentoCandidato.objects.filter(
                candidato__in=candidatos,
                tipo=DocumentoCandidato.Tipo.CURRICULUM,
                vigente=True,
            ).exclude(tipo=DocumentoCandidato.Tipo.EVALUACION)
            formulario = PostulacionForm(request.POST, candidatos=candidatos, documentos=documentos)
        if formulario is not None and formulario.is_valid():
            try:
                with transaction.atomic():
                    postulacion = formulario.save(commit=False)
                    postulacion.vacante = vacante
                    postulacion.save()
            except ValidationError as error:
                mensajes = error.message_dict.get(
                    "__all__",
                    error.messages,
                )
                for mensaje in mensajes:
                    formulario.add_error(
                        None,
                        mensaje,
                    )
            except IntegrityError:
                formulario.add_error(
                    None,
                    "Este candidato ya está vinculado a la vacante.",
                )
            else:
                return redirect("seleccion_detalle_vacante", pk=vacante.pk)
    elif puede_postular:
        candidatos = _candidatos_postulables(request, vacante)
        documentos = DocumentoCandidato.objects.filter(
            candidato__in=candidatos,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            vigente=True,
        )
        formulario = PostulacionForm(candidatos=candidatos, documentos=documentos)
    return render(request, "talento/detalle_vacante.html", {
        "vacante": vacante,
        "postulaciones": postulaciones,
        "formulario": formulario,
        "formularios_actualizacion": formularios_actualizacion,
        "puede_postular": puede_postular,
        "puede_consultar_postulaciones": puede_consultar_postulaciones,
        "puede_crear_entrevista": puede_crear_entrevista,
        "puede_editar_vacante": puede_editar_vacante,
        "estados_postulacion": estados_postulacion,
        "etapa_postulacion": etapa,
        "resumen_postulaciones": resumen_postulaciones,
        "total_postulaciones": total_postulaciones,
    })
