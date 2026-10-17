from django import forms

from core.models import Membresia

from .models import Candidato


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
