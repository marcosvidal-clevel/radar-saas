import unicodedata

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Membresia, Organizacion

from .busqueda_asistida import interpretar_consulta
from .models import Candidato, DocumentoCandidato


@override_settings(MEDIA_ROOT="/tmp/radar-busqueda-asistida-tests")
class BusquedaAsistidaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organizacion.objects.create(nombre="Búsqueda sintética", slug="busqueda-sintetica")
        cls.other = Organizacion.objects.create(nombre="Otra organización", slug="otra-busqueda")
        cls.user = get_user_model().objects.create_user(username="buscador-asistido", is_staff=True)
        perms = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=("view_candidato", "view_documentocandidato"),
        )
        cls.user.user_permissions.add(*perms)
        Membresia.objects.create(organizacion=cls.org, usuario=cls.user, rol=Membresia.Rol.SUPERVISOR)
        cls.candidato = Candidato.objects.create(
            organizacion=cls.org, nombre="Candidata sintética", profesion="Prevencionista",
            ciudad="Santiago",
        )
        cls.ajeno = Candidato.objects.create(organizacion=cls.other, nombre="Ajeno sintético")
        cls.evaluacion = DocumentoCandidato.objects.create(
            candidato=cls.candidato, tipo=DocumentoCandidato.Tipo.EVALUACION,
            nombre="evaluacion.pdf", archivo=SimpleUploadedFile("evaluacion.pdf", b"x"),
        )
        cls.cv = DocumentoCandidato.objects.create(
            candidato=cls.candidato, tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="cv.pdf", archivo=SimpleUploadedFile("cv.pdf", b"x"),
        )
        DocumentoCandidato.objects.filter(pk=cls.cv.pk).update(
            texto_extraido="Prevencionista con experiencia en transporte"
        )
        cls.pendiente = DocumentoCandidato.objects.create(
            candidato=cls.candidato, tipo=DocumentoCandidato.Tipo.OTRO,
            pendiente_clasificacion=True, nombre="pendiente.pdf",
            archivo=SimpleUploadedFile("pendiente.pdf", b"contenido confidencial Prevencionista"),
        )
        cls.cv_ajeno = DocumentoCandidato.objects.create(
            candidato=cls.ajeno, tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="cv-ajeno.pdf", archivo=SimpleUploadedFile("cv-ajeno.pdf", b"x"),
        )
        DocumentoCandidato.objects.filter(pk=cls.cv_ajeno.pk).update(
            texto_extraido="Prevencionista transporte Santiago"
        )
        cls.civil = Candidato.objects.create(
            organizacion=cls.org, nombre="Ingeniero civil sintético", profesion="Ingeniero civil",
        )
        cls.cv_civil = DocumentoCandidato.objects.create(
            candidato=cls.civil, tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="cv-civil.pdf", archivo=SimpleUploadedFile("cv-civil.pdf", b"x"),
        )
        DocumentoCandidato.objects.filter(pk=cls.cv_civil.pk).update(
            texto_extraido="Ingeniero civil titulado en Universidad Diego Portales"
        )
        cls.jose = Candidato.objects.create(
            organizacion=cls.org, nombre="José Venegas", profesion="Analista",
        )
        cls.cv_jose = DocumentoCandidato.objects.create(
            candidato=cls.jose, tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="cv-jose.pdf", archivo=SimpleUploadedFile("cv-jose.pdf", b"x"),
        )
        DocumentoCandidato.objects.filter(pk=cls.cv_jose.pk).update(
            texto_extraido="José Venegas Analista"
        )
        cls.enami = Candidato.objects.create(
            organizacion=cls.org, nombre="Candidato ENAMI sintético", profesion="Ingeniero",
        )
        cls.cv_enami = DocumentoCandidato.objects.create(
            candidato=cls.enami, tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="cv-enami.pdf", archivo=SimpleUploadedFile("cv-enami.pdf", b"x"),
        )
        DocumentoCandidato.objects.filter(pk=cls.cv_enami.pk).update(
            texto_extraido="Experiencia profesional mencionada en proyectos para ENAMI"
        )

    def test_interpreta_conversacion_frase_y_deseable(self):
        resultado = interpretar_consulta(
            'Busco un "prevencionista" con experiencia en transporte, idealmente minería'
        )
        self.assertIn("prevencionista", resultado["obligatorios"])
        self.assertIn("transporte", resultado["obligatorios"])
        self.assertIn("minería", resultado["deseables"])
        self.assertFalse(resultado["ambiguo"])

    def test_formulaciones_equivalentes_conservan_los_mismos_criterios(self):
        consultas = (
            'Busco un "prevencionista" con experiencia en transporte, idealmente minería',
            'Minería sería deseable; transporte y "prevención de riesgos": 5 años',
            'Necesito transporte, prevencionista y 5 años de experiencia; preferentemente minería',
        )
        resultados = [interpretar_consulta(consulta) for consulta in consultas]
        for resultado in resultados:
            self.assertIn("transporte", [item.casefold() for item in resultado["obligatorios"]])
            self.assertIn("minería", [item.casefold() for item in resultado["deseables"]])
            self.assertFalse(resultado["ambiguo"])
        self.assertIn("prevención de riesgos", resultados[1]["obligatorios"])
        self.assertIn("5 años", resultados[1]["obligatorios"])

    def test_terminos_directos_no_requieren_prefijo(self):
        resultado = interpretar_consulta("transporte prevencionista Santiago")
        self.assertEqual(resultado["obligatorios"], ["transporte", "prevencionista"])
        self.assertEqual(resultado["ubicaciones"], ["Santiago"])

    def test_busqueda_no_indexa_documentos_pendientes_de_clasificacion(self):
        self.client.force_login(self.user)
        respuesta = self.client.get(
            reverse("talento_candidatos"), {"q": "confidencial"}
        )
        self.assertNotContains(respuesta, self.candidato.nombre)

    def test_conectores_no_quedan_como_pendientes_y_nombres_se_conservan(self):
        resultado = interpretar_consulta("busco a jose venegas")
        self.assertEqual(resultado["obligatorios"], ["jose", "venegas"])
        self.assertNotIn("a", resultado["no_interpretado"])

    def test_formulaciones_equivalentes_por_nombre(self):
        consultas = (
            "busco a jose venegas",
            "jose venegas",
            'necesito el candidato "José Venegas"',
        )
        interpretaciones = [interpretar_consulta(consulta) for consulta in consultas]
        for resultado in interpretaciones:
            texto = unicodedata.normalize("NFKD", " ".join(resultado["obligatorios"]).casefold()).encode("ascii", "ignore").decode()
            self.assertEqual(
                {token.strip(".,;:") for token in texto.split()},
                {"jose", "venegas"},
            )
            self.assertFalse(resultado["no_interpretado"])

    def test_pregunta_estudios_reconoce_institucion_completa_y_no_deja_pendientes(self):
        resultado = interpretar_consulta(
            "hay un cv de alguien que hay estudiado en el colegio diego portales?"
        )
        self.assertEqual(resultado["obligatorios"], ["colegio diego portales"])
        self.assertEqual(resultado["no_interpretado"], [])
        self.assertEqual(resultado["pendientes"], [])
        self.assertEqual(resultado["criterios"][0]["categoria"], "formación")
        self.assertEqual(resultado["criterios"][0]["texto"], "colegio diego portales")
        self.assertEqual(resultado["criterios"][0]["evidencia"], "coincidencia textual")

    def test_formacion_reconoce_tipos_de_institucion_y_conserva_el_tipo(self):
        consultas = (
            ("estudió en el Colegio Diego Portales", "Colegio Diego Portales"),
            ("estudió en la Universidad Diego Portales", "Universidad Diego Portales"),
            ("estudió en el Instituto Profesional AIEP", "Instituto Profesional AIEP"),
            ("estudió en el Centro de Formación Técnica INACAP", "Centro de Formación Técnica INACAP"),
        )
        for consulta, institucion in consultas:
            resultado = interpretar_consulta(consulta)
            self.assertEqual(resultado["obligatorios"][0].casefold(), institucion.casefold())
            self.assertEqual(resultado["criterios"][0]["categoria"], "formación")
            self.assertNotIn("requiere aclaración", " ".join(resultado["pendientes"]))

    def test_mencion_textual_de_institucion_no_confirma_formacion(self):
        resultado = interpretar_consulta(
            "el CV menciona proyectos con la Universidad Diego Portales"
        )
        self.assertEqual(resultado["obligatorios"][0].casefold(), "Universidad Diego Portales".casefold())
        self.assertEqual(resultado["criterios"][0]["categoria"], "formación")
        self.assertEqual(resultado["criterios"][0]["evidencia"], "coincidencia textual")
        self.assertNotIn("antecedente confirmado por campo estructurado", resultado["criterios"][0]["evidencia"])

    def test_empresa_en_pregunta_es_coincidencia_textual_sin_relacion_confirmada(self):
        resultado = interpretar_consulta("¿Existe alguien que haya trabajado en ENAMI?")
        self.assertEqual(resultado["obligatorios"], ["ENAMI"])
        self.assertEqual(resultado["no_interpretado"], [])
        self.assertEqual(resultado["pendientes"], [])
        self.assertEqual(resultado["criterios"][0]["categoria"], "texto")
        self.assertEqual(resultado["criterios"][0]["evidencia"], "coincidencia textual")

    def test_http_exacta_pregunta_empresa_encuentra_sin_confirmar_relacion(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("talento_candidatos"),
            {"q": "¿Existe alguien que haya trabajado en ENAMI?", "modo_busqueda": "asistida"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {c.nombre for c in response.context["pagina_candidatos"].object_list},
            {"Candidato ENAMI sintético"},
        )
        self.assertContains(response, "coincidencia textual")
        self.assertNotContains(response, "relación laboral confirmada")

    def test_variantes_empresa_mayusculas_puntuacion_y_empresa_distinta(self):
        self.client.force_login(self.user)
        consultas = (
            "¿existe alguien que haya trabajado en enami?",
            "Existe alguien que haya trabajado en ENAMI.",
            "¿Quién trabajó en CODELCO?",
        )
        resultados = []
        for consulta in consultas:
            resultado = interpretar_consulta(consulta)
            resultados.append((resultado["obligatorios"], resultado["no_interpretado"]))
        self.assertEqual(resultados[0], (["enami"], []))
        self.assertEqual(resultados[1], (["ENAMI"], []))
        self.assertEqual(resultados[2], (["CODELCO"], []))

    def test_organiza_criterios_por_categoria_y_evidencia(self):
        resultado = interpretar_consulta(
            "¿Qué persona tiene profesión prevencionista, formación ingeniería, empresa Acme, sector minería y ubicación Santiago?"
        )
        self.assertIn("profesión", resultado["criterios_por_tipo"])
        self.assertIn("formación", resultado["criterios_por_tipo"])
        self.assertIn("empresa", resultado["criterios_por_tipo"])
        self.assertIn("sector", resultado["criterios_por_tipo"])
        self.assertIn("ubicación", resultado["criterios_por_tipo"])
        self.assertEqual(
            resultado["criterios_por_tipo"]["ubicación"][0]["evidencia"],
            "antecedente confirmado por campo estructurado",
        )
        self.assertTrue(all(c["evidencia"] == "coincidencia textual" for c in resultado["criterios"] if c["categoria"] != "ubicación"))

    def test_preguntas_y_orden_distinto_conservan_obligatorios_y_deseables(self):
        consultas = (
            "¿Necesitas una persona prevencionista en transporte, idealmente minería?",
            "Minería es deseable; para transporte necesito una persona que sea prevencionista",
        )
        for consulta in consultas:
            resultado = interpretar_consulta(consulta)
            self.assertIn("transporte", [x.casefold() for x in resultado["obligatorios"]])
            self.assertIn("minería", [x.casefold() for x in resultado["deseables"]])
            self.assertFalse(resultado["ambiguo"])

    def test_http_formulaciones_equivalentes_por_nombre(self):
        self.client.force_login(self.user)
        nombres = []
        for consulta in ("busco a jose venegas", "jose venegas", '"José Venegas"'):
            response = self.client.get(reverse("talento_candidatos"), {"q": consulta, "modo_busqueda": "asistida"})
            self.assertEqual(response.status_code, 200)
            nombres.append({c.nombre for c in response.context["pagina_candidatos"].object_list})
        self.assertEqual(nombres[0], nombres[1])
        self.assertEqual(nombres[1], nombres[2])
        self.assertEqual(nombres[0], {"José Venegas"})

    def test_negaciones_se_reportan_y_no_se_aplican_como_filtro(self):
        resultado = interpretar_consulta("prevencionista no minería")
        self.assertEqual(resultado["ambiguo"], ["no"])
        self.assertIn("minería", resultado["obligatorios"])

    def test_experiencia_queda_pendiente_y_no_filtra_por_numeros(self):
        resultado = interpretar_consulta("prevencionista con 5 años de experiencia")
        self.assertIn("5 años", resultado["obligatorios"])
        self.assertIn("5 años (requiere comprobación)", resultado["pendientes"])
        self.assertNotIn("5 años", resultado["obligatorios_busqueda"])

    def test_http_formulaciones_equivalentes_devuelven_los_mismos_candidatos(self):
        self.client.force_login(self.user)
        consultas = (
            '"prevencionista" transporte',
            'transporte prevención de riesgos',
        )
        nombres = []
        for consulta in consultas:
            response = self.client.get(reverse("talento_candidatos"), {"q": consulta, "modo_busqueda": "asistida"})
            self.assertEqual(response.status_code, 200)
            nombres.append({c.nombre for c in response.context["pagina_candidatos"].object_list})
        self.assertEqual(nombres[0], nombres[1])
        self.assertEqual(nombres[0], {"Candidata sintética"})

    def test_http_profesion_y_universidad_aislan_resultado(self):
        self.client.force_login(self.user)
        consultas = (
            'ingeniero civil "Universidad Diego Portales"',
            '"Universidad Diego Portales" ingeniero civil',
        )
        nombres = []
        for consulta in consultas:
            response = self.client.get(reverse("talento_candidatos"), {"q": consulta, "modo_busqueda": "asistida"})
            nombres.append({c.nombre for c in response.context["pagina_candidatos"].object_list})
        self.assertEqual(nombres[0], nombres[1])
        self.assertEqual(nombres[0], {"Ingeniero civil sintético"})

    def test_http_muestra_pendientes_sin_presentar_cumplimiento_total(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("talento_candidatos"), {"q": "prevencionista 5 años", "modo_busqueda": "asistida"})
        self.assertContains(response, "requiere comprobación")
        self.assertContains(response, "no confirman toda la consulta")

    def test_limite_no_trunca_ni_busca(self):
        self.client.force_login(self.user)
        consulta = "x" * 1001
        response = self.client.get(reverse("talento_candidatos"), {"q": consulta, "modo_busqueda": "asistida"})
        self.assertContains(response, "no puede superar 1000")
        self.assertEqual(response.context["busqueda"], consulta)

    def test_negacion_ambigua_no_excluye(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("talento_candidatos"), {"q": "prevencionista sin minería", "modo_busqueda": "asistida"})
        self.assertContains(response, "negación ambigua")
        self.assertContains(response, "Candidata sintética")

    def test_ubicacion_se_confirma_por_campo_estructurado(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("talento_candidatos"), {"q": "prevencionista Santiago", "modo_busqueda": "asistida"})
        self.assertContains(response, "Candidata sintética")
        self.assertContains(response, "Ubicación confirmada solo por campos estructurados")

    def test_fts_aisla_organizacion_y_excluye_evaluacion(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("talento_candidatos"), {"q": "prevencionista transporte", "modo_busqueda": "asistida"})
        self.assertContains(response, "Candidata sintética")
        self.assertNotContains(response, "Ajeno sintético")
        self.assertNotContains(response, "evaluacion.pdf")
