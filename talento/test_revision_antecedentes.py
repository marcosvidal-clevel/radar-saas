"""Pruebas del indicador informativo de antecedentes en administración."""
from django.contrib import admin
from django.core.files.base import ContentFile
from django.test import TestCase

from core.models import Organizacion
from talento.admin import CandidatoAdmin, RevisionCandidatoForm
from talento.models import Candidato, DocumentoCandidato


class RevisionAntecedentesTests(TestCase):
    def setUp(self):
        self.organizacion = Organizacion.objects.create(
            nombre="Organización revisión", slug="organizacion-revision"
        )
        self.candidato = Candidato.objects.create(
            organizacion=self.organizacion, nombre="Persona Ejemplo"
        )
        self.admin = CandidatoAdmin(Candidato, admin.site)

    def test_revision_documental_independiente_de_disponibilidad(self):
        self.assertEqual(
            self.candidato.revision_documental,
            Candidato.RevisionDocumental.PENDIENTE,
        )
        self.assertEqual(self.candidato.estado, Candidato.Estado.DISPONIBLE)
        self.candidato.revision_documental = Candidato.RevisionDocumental.RECHAZADO
        self.candidato.observaciones_revision = "Documento ilegible; solicitar copia."
        self.candidato.save(
            update_fields=["revision_documental", "observaciones_revision"]
        )
        self.candidato.refresh_from_db()
        self.assertEqual(
            self.candidato.revision_documental,
            Candidato.RevisionDocumental.RECHAZADO,
        )
        self.assertEqual(self.candidato.estado, Candidato.Estado.DISPONIBLE)
        self.assertTrue(self.candidato.activo)
        self.assertEqual(
            self.candidato.observaciones_revision,
            "Documento ilegible; solicitar copia.",
        )

    def test_rechazo_documental_exige_motivo(self):
        formulario = RevisionCandidatoForm(
            data={
                "organizacion": self.organizacion.pk,
                "nombre": "Persona Ejemplo",
                "revision_documental": Candidato.RevisionDocumental.RECHAZADO,
                "observaciones_revision": "   ",
            },
            instance=self.candidato,
        )
        self.assertFalse(formulario.is_valid())
        self.assertIn("observaciones_revision", formulario.errors)

    def test_rechazo_documental_con_motivo_es_valido(self):
        formulario = RevisionCandidatoForm(
            data={
                "organizacion": self.organizacion.pk,
                "nombre": "Persona Ejemplo",
                "revision_documental": Candidato.RevisionDocumental.RECHAZADO,
                "observaciones_revision": "Título ilegible.",
            },
            instance=self.candidato,
        )
        self.assertNotIn("observaciones_revision", formulario.errors)

    def test_aprobacion_documental_no_exige_observaciones(self):
        formulario = RevisionCandidatoForm(
            data={
                "organizacion": self.organizacion.pk,
                "nombre": "Persona Ejemplo",
                "revision_documental": Candidato.RevisionDocumental.APROBADO,
                "observaciones_revision": "",
            },
            instance=self.candidato,
        )
        self.assertNotIn("observaciones_revision", formulario.errors)

    def test_incompleto_se_informa_sin_rechazar_ficha(self):
        self.assertEqual(
            self.admin.revision_antecedentes(self.candidato),
            "Por revisar: RUT, CV, título",
        )
        self.assertTrue(Candidato.objects.filter(pk=self.candidato.pk).exists())

    def test_rut_y_documentos_completan_indicador(self):
        self.candidato.rut = "12345678-5"
        self.candidato.save(update_fields=["rut"])
        for tipo in (
            DocumentoCandidato.Tipo.CURRICULUM,
            DocumentoCandidato.Tipo.TITULO,
        ):
            DocumentoCandidato.objects.create(
                candidato=self.candidato, tipo=tipo,
                nombre=f"Documento {tipo}",
                archivo=ContentFile(b"%PDF-1.4\\n%%EOF", name=f"{tipo}.pdf"),
            )
        self.assertEqual(
            self.admin.revision_antecedentes(self.candidato), "Completo"
        )

    def test_titulo_no_vigente_no_completa_antecedentes(self):
        self.candidato.rut = "12345678-5"
        self.candidato.save(update_fields=["rut"])
        self.candidato.documentos.create(
            nombre="CV vigente", tipo=DocumentoCandidato.Tipo.CURRICULUM,
            vigente=True,
            archivo=ContentFile(b"%PDF-1.4\\n%%EOF", name="cv.pdf"),
        )
        self.candidato.documentos.create(
            nombre="Título antiguo", tipo=DocumentoCandidato.Tipo.TITULO,
            vigente=False,
            archivo=ContentFile(b"%PDF-1.4\\n%%EOF", name="documento.pdf"),
        )
        self.assertEqual(
            self.admin.revision_antecedentes(self.candidato),
            "Por revisar: título",
        )

    def test_documento_no_vigente_no_acredita_cv(self):
        self.candidato.documentos.create(
            nombre="CV antiguo", tipo=DocumentoCandidato.Tipo.CURRICULUM,
            vigente=False,
            archivo=ContentFile(b"%PDF-1.4\\n%%EOF", name="cv_antiguo.pdf"),
        )
        self.assertIn("CV", self.admin.revision_antecedentes(self.candidato))
