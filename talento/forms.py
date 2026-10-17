from django import forms

from core.models import EmpresaProspectada, Membresia, Oportunidad, Organizacion

from .models import Candidato, DocumentoCandidato, Postulacion, Vacante


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
