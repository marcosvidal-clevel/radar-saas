import hashlib

from django import forms

from core.models import EmpresaProspectada, Membresia, Oportunidad, Organizacion

from .models import Candidato, DocumentoCandidato, Entrevista, Postulacion, Vacante


class CandidatoForm(forms.ModelForm):
    cv = forms.FileField(
        required=False,
        label="CV opcional",
        help_text="PDF, DOC o DOCX. Máximo 10 MB.",
    )

    class Meta:
        model = Candidato
        fields = (
            "organizacion",
            "nombre",
            "email",
            "telefono",
            "linkedin",
            "profesion",
            "especialidad",
            "region",
            "ciudad",
            "anos_experiencia",
            "pretension_renta",
            "experiencia",
            "competencias",
            "fuente",
            "estado",
            "notas",
            "activo",
            "es_prueba",
            "cv",
        )
        widgets = {
            "experiencia": forms.Textarea(attrs={"rows": 4}),
            "competencias": forms.Textarea(attrs={"rows": 4}),
            "notas": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, organizaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organizaciones is None:
            organizaciones = Membresia.objects.none()
        self.fields["organizacion"].queryset = organizaciones.filter(
            activa=True,
        )
        if self.instance and self.instance.pk:
            self.fields["organizacion"].disabled = True
            self.fields["cv"].label = "Reemplazar CV principal (opcional)"

    def clean_organizacion(self):
        organizacion = self.cleaned_data["organizacion"]
        if (
            self.instance
            and self.instance.pk
            and organizacion.pk != self.instance.organizacion_id
        ):
            raise forms.ValidationError(
                "La organización del candidato no se puede cambiar."
            )
        return organizacion

    def clean_cv(self):
        archivo = self.cleaned_data.get("cv")
        if not archivo:
            return archivo

        extension = archivo.name.rsplit(".", 1)[-1].lower()
        if extension not in {"pdf", "doc", "docx"}:
            raise forms.ValidationError(
                "El CV debe ser un archivo PDF, DOC o DOCX."
            )
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError(
                "El CV no puede superar los 10 MB."
            )
        return archivo


class CandidatoVacanteForm(forms.ModelForm):
    cv = forms.FileField(required=False, label="CV opcional")

    class Meta:
        model = Candidato
        fields = (
            "nombre", "email", "telefono", "profesion", "especialidad",
            "region", "ciudad", "cv",
        )
        widgets = {"cv": forms.ClearableFileInput(attrs={"accept": ".pdf,.doc,.docx"})}

    def clean_cv(self):
        archivo = self.cleaned_data.get("cv")
        if archivo:
            extension = archivo.name.rsplit(".", 1)[-1].lower()
            if extension not in {"pdf", "doc", "docx"}:
                raise forms.ValidationError("El CV debe ser un archivo PDF, DOC o DOCX.")
            if archivo.size > 10 * 1024 * 1024:
                raise forms.ValidationError("El CV no puede superar los 10 MB.")
        return archivo


class DocumentoAntecedenteForm(forms.ModelForm):
    class Meta:
        model = DocumentoCandidato
        fields = ("nombre", "tipo", "archivo", "observaciones")
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "nombre": "Nombre del documento",
            "tipo": "Clasificación",
            "archivo": "Archivo",
            "observaciones": "Observaciones",
        }

    TIPOS_ANTECEDENTE = {
        DocumentoCandidato.Tipo.TITULO,
        DocumentoCandidato.Tipo.CAPACITACION,
        DocumentoCandidato.Tipo.CERTIFICACION,
        DocumentoCandidato.Tipo.RECOMENDACION,
        DocumentoCandidato.Tipo.EXPERIENCIA,
        DocumentoCandidato.Tipo.OTRO,
    }

    def __init__(self, *args, candidato=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.candidato = candidato
        self.fields["tipo"].choices = [
            choice for choice in self.fields["tipo"].choices
            if choice[0] in self.TIPOS_ANTECEDENTE
        ]

    def clean_tipo(self):
        tipo = self.cleaned_data["tipo"]
        if tipo not in self.TIPOS_ANTECEDENTE:
            raise forms.ValidationError(
                "Selecciona una clasificación de antecedente válida."
            )
        return tipo

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        extension = archivo.name.rsplit(".", 1)[-1].lower()
        if extension not in {"pdf", "doc", "docx"}:
            raise forms.ValidationError(
                "El archivo debe ser PDF, DOC o DOCX."
            )
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError(
                "El archivo no puede superar los 10 MB."
            )
        digest = hashlib.sha256()
        for chunk in archivo.chunks():
            digest.update(chunk)
        archivo.seek(0)
        if self.candidato and self.candidato.documentos.filter(
            sha256=digest.hexdigest(),
        ).exists():
            raise forms.ValidationError(
                "Este archivo ya existe en el expediente del candidato."
            )
        return archivo


class VacanteForm(forms.ModelForm):
    class Meta:
        model = Vacante
        fields = (
            "organizacion", "empresa", "oportunidad", "titulo",
            "descripcion", "requisitos", "region", "ciudad", "estado",
            "publicar_web", "activa",
        )
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "requisitos": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, organizaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organizacion"].queryset = organizaciones or Organizacion.objects.none()
        self.fields["empresa"].queryset = EmpresaProspectada.objects.none()
        self.fields["oportunidad"].queryset = Oportunidad.objects.none()
        organizacion_id = self.data.get("organizacion") or getattr(self.instance, "organizacion_id", None)
        if organizacion_id:
            self.fields["empresa"].queryset = EmpresaProspectada.objects.filter(organizacion_id=organizacion_id, activa=True)
            self.fields["oportunidad"].queryset = Oportunidad.objects.filter(organizacion_id=organizacion_id)
        if self.instance and self.instance.pk:
            self.fields["organizacion"].disabled = True

    def clean(self):
        datos = super().clean()
        organizacion = datos.get("organizacion")
        for campo in ("empresa", "oportunidad"):
            objeto = datos.get(campo)
            if objeto and organizacion and objeto.organizacion_id != organizacion.pk:
                self.add_error(campo, "Debe pertenecer a la organización de la vacante.")
        return datos


class VacanteEdicionForm(forms.ModelForm):
    class Meta:
        model = Vacante
        fields = (
            "empresa", "oportunidad", "titulo", "descripcion", "requisitos",
            "region", "ciudad", "estado", "activa",
        )
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "requisitos": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organizacion_id = self.instance.organizacion_id
        self.fields["empresa"].queryset = EmpresaProspectada.objects.filter(
            organizacion_id=organizacion_id, activa=True,
        )
        self.fields["oportunidad"].queryset = Oportunidad.objects.filter(
            organizacion_id=organizacion_id,
        )

    def clean(self):
        datos = super().clean()
        organizacion_id = self.instance.organizacion_id
        empresa = datos.get("empresa")
        oportunidad = datos.get("oportunidad")
        if empresa and empresa.organizacion_id != organizacion_id:
            self.add_error("empresa", "Debe pertenecer a la organización de la vacante.")
        if oportunidad and oportunidad.organizacion_id != organizacion_id:
            self.add_error("oportunidad", "Debe pertenecer a la organización de la vacante.")
        if empresa and oportunidad and oportunidad.empresa_id and oportunidad.empresa_id != empresa.pk:
            self.add_error("oportunidad", "La oportunidad debe corresponder a la empresa indicada.")
        return datos


class PostulacionForm(forms.ModelForm):
    class Meta:
        model = Postulacion
        fields = ("candidato", "documento_cv", "fuente", "observaciones")
        widgets = {"observaciones": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, candidatos=None, documentos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["candidato"].queryset = candidatos or Candidato.objects.none()
        self.fields["documento_cv"].queryset = documentos or DocumentoCandidato.objects.none()

    def clean(self):
        datos = super().clean()
        candidato = datos.get("candidato")
        documento = datos.get("documento_cv")
        if documento and candidato and documento.candidato_id != candidato.pk:
            self.add_error("documento_cv", "El CV debe pertenecer al candidato.")
        if documento and (not documento.vigente or documento.tipo != DocumentoCandidato.Tipo.CURRICULUM):
            self.add_error("documento_cv", "Solo puedes asociar un CV vigente.")
        return datos


class ActualizarPostulacionForm(forms.ModelForm):
    class Meta:
        model = Postulacion
        fields = ("estado", "observaciones")
        widgets = {"observaciones": forms.Textarea(attrs={"rows": 4})}


class EntrevistaForm(forms.ModelForm):
    motivo = forms.CharField(
        required=True,
        label="Motivo de la entrevista",
        help_text="Ejemplo: entrevista inicial, técnica, por competencias o con el cliente",
        error_messages={"required": "El motivo de la entrevista es obligatorio."},
    )

    class Meta:
        model = Entrevista
        fields = ("fecha_hora", "motivo", "entrevistador", "modalidad", "lugar_enlace", "observaciones", "estado", "resultado", "recomendacion")
        widgets = {
            "fecha_hora": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "observaciones": forms.Textarea(attrs={"rows": 4}),
            "resultado": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {"resultado": "Resumen del resultado", "recomendacion": "Recomendación"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_hora"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]

    def clean_motivo(self):
        motivo = self.cleaned_data.get("motivo", "")
        if not motivo.strip():
            raise forms.ValidationError("El motivo de la entrevista es obligatorio.")
        return motivo.strip()

    def clean(self):
        datos = super().clean()
        if datos.get("estado") == Entrevista.Estado.REALIZADA:
            if not datos.get("resultado", "").strip():
                self.add_error("resultado", "El resumen del resultado es obligatorio al marcar la entrevista como realizada.")
            if datos.get("recomendacion") in (None, "", Entrevista.Recomendacion.PENDIENTE):
                self.add_error("recomendacion", "Selecciona una recomendación distinta de Pendiente al marcar la entrevista como realizada.")
        return datos
