from django import forms

from .models import Oportunidad


class SeguimientoOportunidadForm(forms.ModelForm):
    class Meta:
        model = Oportunidad
        fields = (
            "estado",
            "proxima_accion",
            "fecha_proxima_accion",
            "motivo_cierre",
        )
        labels = {
            "estado": "Estado",
            "proxima_accion": "Próxima acción",
            "fecha_proxima_accion": "Fecha de próxima acción",
            "motivo_cierre": "Motivo de cierre",
        }
        help_texts = {
            "proxima_accion": (
                "Indica qué harás para avanzar con esta oportunidad."
            ),
            "motivo_cierre": (
                "Obligatorio si la oportunidad queda perdida o descartada."
            ),
        }
        widgets = {
            "proxima_accion": forms.Textarea(
                attrs={"rows": 3}
            ),
            "fecha_proxima_accion": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "motivo_cierre": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_motivo_cierre(self):
        return self.cleaned_data.get("motivo_cierre", "").strip()