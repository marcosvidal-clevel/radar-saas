from django import forms
from core.models import Organizacion, Membresia
from .models import EntradaPendiente, Candidato
from .entradas_services import CAMPOS, ORIGEN


class EntradaForm(forms.ModelForm):
    fuente_revision = forms.CharField(
        label="Fuente de los datos o de la confirmación", widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Indique documento, página, resumen o confirmación explícita. No se deducen nombres desde correos.",
    )

    class Meta:
        model = EntradaPendiente
        fields = ("organizacion",) + ORIGEN + ("archivo",) + CAMPOS
        widgets = {f: forms.Textarea(attrs={"rows": 3}) for f in (
            "limitacion_lectura", "informacion_por_completar",
        )}
        help_texts = {
            "nombre": "Puede quedar vacío. No cree una identidad ficticia.",
            "email": "Solo marque disponible si fue confirmado como contacto personal; no copie correos genéricos de portales.",
            "region": "Opcional: no se exige domicilio completo.",
            "clave_documental": "Nombre de archivo completo, incluida extensión, dentro de la procedencia.",
        }

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        orgs = Organizacion.objects.filter(activa=True)
        if not usuario.is_superuser:
            orgs = orgs.filter(membresias__usuario=usuario, membresias__activa=True,
                               membresias__rol__in=[Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR])
        self.fields["organizacion"].queryset = orgs.distinct()
        self.fields["seguimiento"].choices = [c for c in EntradaPendiente.Seguimiento.choices if c[0] != "resuelto"]
        if self.instance.pk:
            for f in ("organizacion",) + ORIGEN:
                self.fields[f].disabled = True
            del self.fields["archivo"]


class ResolverEntradaForm(forms.Form):
    candidato = forms.ModelChoiceField(
        queryset=Candidato.objects.none(), required=False,
        label="Ficha existente (dejar vacío para crear una nueva)",
        help_text="Selección explícita tras revisar identidad y duplicados. Nunca se sobrescriben datos de una ficha existente.",
    )
    fuente = forms.CharField(label="Evidencia y fuente que confirman identidad y destino", widget=forms.Textarea)

    def __init__(self, *args, entrada, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["candidato"].queryset = Candidato.objects.filter(
            organizacion=entrada.organizacion, consolidado_en__isnull=True,
        ).order_by("nombre", "pk")
