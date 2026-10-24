"""Django model proposal only; not installed or migrated.

A unique key per organization prevents duplicate external lead imports.
The RADAR application must validate membership/permissions at its API boundary.
"""
from django.db import models

class OportunidadExterna(models.Model):
    organizacion = models.ForeignKey("core.Organizacion", on_delete=models.PROTECT)
    oportunidad = models.ForeignKey("core.Oportunidad", on_delete=models.PROTECT)
    clave_externa = models.CharField(max_length=200)
    origen_integracion = models.CharField(max_length=40, default="make")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organizacion", "origen_integracion", "clave_externa"],
                name="uq_oportunidad_externa_org_origen_clave",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.oportunidad_id and self.organizacion_id:
            if self.oportunidad.organizacion_id != self.organizacion_id:
                raise ValidationError("La oportunidad debe pertenecer a la misma organización.")
