"""Pruebas del indicador informativo de antecedentes en administración."""
from django.contrib import admin
from django.test import TestCase

from core.models import Organizacion
from talento.admin import CandidatoAdmin
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
        )
        self.candidato.documentos.create(
            nombre="Título antiguo", tipo=DocumentoCandidato.Tipo.TITULO,
            vigente=False,
        )
        self.assertEqual(
            self.admin.revision_antecedentes(self.candidato),
            "Por revisar: título",
        )

    def test_documento_no_vigente_no_acredita_cv(self):
        self.candidato.documentos.create(
            nombre="CV antiguo", tipo=DocumentoCandidato.Tipo.CURRICULUM,
            vigente=False,
        )
        self.assertIn("CV", self.admin.revision_antecedentes(self.candidato))
