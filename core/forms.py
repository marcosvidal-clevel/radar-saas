from django import forms

from .models import (
    Contacto,
    EmpresaProspectada,
    Membresia,
    Oportunidad,
    Organizacion,
    Senal,
)


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


class NuevaOportunidadForm(forms.ModelForm):
    class Meta:
        model = Oportunidad
        fields = (
            "organizacion",
            "titulo",
            "origen",
            "canal",
            "empresa",
            "contacto",
            "senal",
            "responsable",
            "nombre_consultante",
            "email_consultante",
            "telefono_consultante",
            "necesidad",
            "estado",
            "proxima_accion",
            "fecha_proxima_accion",
            "motivo_cierre",
            "notas",
        )
        labels = {
            "organizacion": "Organización",
            "titulo": "Título de la oportunidad",
            "origen": "Origen",
            "canal": "Canal",
            "empresa": "Empresa",
            "contacto": "Contacto asociado",
            "senal": "Señal asociada",
            "responsable": "Responsable",
            "nombre_consultante": "Nombre del consultante",
            "email_consultante": "Correo del consultante",
            "telefono_consultante": "Teléfono del consultante",
            "necesidad": "Necesidad comercial",
            "estado": "Estado",
            "proxima_accion": "Próxima acción",
            "fecha_proxima_accion": "Fecha de próxima acción",
            "motivo_cierre": "Motivo de cierre",
            "notas": "Notas",
        }
        help_texts = {
            "origen": (
                "Consulta entrante: alguien contactó a tu empresa. "
                "Prospección: tú detectaste la oportunidad."
            ),
            "empresa": (
                "Obligatoria para prospección. Debe pertenecer "
                "a la organización seleccionada."
            ),
            "contacto": (
                "Opcional. Debe pertenecer a la empresa seleccionada."
            ),
            "senal": (
                "Opcional. Debe estar validada y pertenecer "
                "a la empresa seleccionada."
            ),
            "responsable": (
                "Opcional. Debe tener una membresía activa "
                "en la organización seleccionada."
            ),
            "necesidad": (
                "Describe la consulta recibida o la necesidad detectada."
            ),
            "motivo_cierre": (
                "Obligatorio para una oportunidad perdida o descartada."
            ),
        }
        widgets = {
            "necesidad": forms.Textarea(attrs={"rows": 4}),
            "proxima_accion": forms.Textarea(attrs={"rows": 3}),
            "fecha_proxima_accion": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "motivo_cierre": forms.Textarea(attrs={"rows": 3}),
            "notas": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)

        organizaciones = Organizacion.objects.none()

        if usuario.is_active and usuario.is_staff:
            if usuario.is_superuser:
                organizaciones = Organizacion.objects.filter(
                    activa=True
                )
            elif usuario.has_perm("core.add_oportunidad"):
                membresias = Membresia.objects.filter(
                    usuario=usuario,
                    activa=True,
                    organizacion__activa=True,
                    rol__in=(
                        Membresia.Rol.ADMINISTRADOR,
                        Membresia.Rol.SUPERVISOR,
                    ),
                )
                organizaciones = Organizacion.objects.filter(
                    pk__in=membresias.values("organizacion_id")
                )

        self.fields["organizacion"].queryset = (
            organizaciones.order_by("nombre", "pk")
        )
        self.fields["empresa"].queryset = (
            EmpresaProspectada.objects.filter(
                organizacion__in=organizaciones,
                activa=True,
            ).select_related(
                "organizacion"
            ).order_by("nombre", "pk")
        )
        self.fields["contacto"].queryset = (
            Contacto.objects.filter(
                empresa__organizacion__in=organizaciones,
                empresa__activa=True,
                activo=True,
            ).select_related(
                "empresa"
            ).order_by("nombre", "pk")
        )
        self.fields["senal"].queryset = (
            Senal.objects.filter(
                empresa__organizacion__in=organizaciones,
                empresa__activa=True,
                estado=Senal.Estado.VALIDADA,
            ).select_related(
                "empresa"
            ).order_by("-creada_en", "-pk")
        )
        self.fields["responsable"].queryset = (
            Membresia.objects.filter(
                organizacion__in=organizaciones,
                activa=True,
                usuario__is_active=True,
            ).select_related(
                "usuario",
                "organizacion",
            ).order_by("usuario__username", "pk")
        )

        if not self.is_bound:
            opciones = list(organizaciones.order_by("pk")[:2])

            if len(opciones) == 1:
                self.initial.setdefault(
                    "organizacion",
                    opciones[0].pk,
                )

            self.initial.setdefault(
                "origen",
                Oportunidad.Origen.CONSULTA_ENTRANTE,
            )
            self.initial.setdefault(
                "estado",
                Oportunidad.Estado.NUEVA,
            )

    def clean_motivo_cierre(self):
        return self.cleaned_data.get("motivo_cierre", "").strip()