import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from docx import Document

from core.models import Membresia, Organizacion
from talento.entradas_services import guardar_entrada
from talento.models import Candidato, DocumentoCandidato, EntradaPendiente, RevisionEntrada


class ImportacionPendientesTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        media = override_settings(MEDIA_ROOT=self.root / 'media')
        media.enable()
        self.addCleanup(media.disable)
        self.org = Organizacion.objects.create(nombre='Sintética', slug='sintetica')
        self.user = get_user_model().objects.create_user('synthetic', is_staff=True)
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='talento'))
        Membresia.objects.create(usuario=self.user, organizacion=self.org, rol='admin')
        doc = Document()
        doc.add_paragraph('CV sintético; titular declarado')
        doc.save(self.root / 'cv.docx')
        (self.root / 'unknown.png').write_bytes(b'synthetic unknown image')

    def pending(self, key='p', **extra):
        row = {'id_fila': key, 'origen_importacion': 'synthetic', 'identificador_origen': key,
               'documentos': [{'archivo': 'cv.docx', 'identificador_origen': 'cv.docx', 'tipo': 'curriculum'}],
               'pendiente': {'motivo': 'Identidad por corroborar', 'fuente': 'Resumen sintético',
                             'datos': {'nombre': 'Nombre propuesto', 'identidad_estado': 'confirmado'}},
               'contexto_recepcion': {'asunto': 'Recepción sintética'}}
        row.update(extra)
        return row

    def run_batch(self, rows, write=False):
        (self.root / 'manifest.json').write_text(json.dumps({'organizacion': self.org.pk,
            'usuario_ejecutor': self.user.username, 'registros': rows}))
        out = io.StringIO()
        call_command('importar_cvs', str(self.root), 'manifest.json', importar=write, stdout=out)
        return out.getvalue()

    def test_preview_and_receipt_are_idempotent_without_extraction(self):
        row = self.pending()
        with patch.object(DocumentoCandidato, 'extraer_texto') as extract:
            preview = self.run_batch([row])
            self.assertIn('total=1 listos=0 pendientes=1', preview)
            self.assertFalse(EntradaPendiente.objects.exists())
            self.run_batch([row], True)
            self.run_batch([row], True)
        extract.assert_not_called()
        entry = EntradaPendiente.objects.get()
        self.assertEqual(entry.tipo_documento, 'curriculum')
        self.assertEqual(entry.identidad_estado, 'no_confirmado')
        self.assertEqual(entry.contexto_recepcion, row['contexto_recepcion'])
        self.assertEqual(entry.motivo_pendiente, 'Identidad por corroborar')
        self.assertEqual(RevisionEntrada.objects.count(), 1)
        self.assertFalse(Candidato.objects.exists())
        self.assertFalse(DocumentoCandidato.objects.exists())
        with entry.archivo.open('rb') as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), entry.sha256)

    def test_independent_equal_hash_receipts_and_conflicting_reception(self):
        self.run_batch([self.pending('a'), self.pending('b')], True)
        self.assertEqual(EntradaPendiente.objects.count(), 2)
        (self.root / 'cv.docx').write_bytes(b'changed original')
        out = self.run_batch([self.pending('a')], True)
        self.assertIn('conflicto', out)
        self.assertEqual(EntradaPendiente.objects.count(), 2)
        self.assertEqual(RevisionEntrada.objects.count(), 2)

    def test_mixed_batch_continues_and_counts_missing_document(self):
        clear = {'nombre': 'Persona clara', 'origen_importacion': 'synthetic',
                 'identificador_origen': 'clear', 'archivo': 'cv.docx'}
        bad = self.pending('missing', documentos=[{'archivo': 'absent.pdf', 'identificador_origen': 'absent.pdf', 'tipo': 'curriculum'}])
        result = self.run_batch([clear, self.pending(), bad], True)
        self.assertIn('total=3 listos=1 pendientes=1 existentes=0 conflictos=1', result)
        self.assertEqual(Candidato.objects.count(), 1)
        self.assertEqual(DocumentoCandidato.objects.count(), 1)
        self.assertEqual(EntradaPendiente.objects.count(), 1)

    def test_unknown_for_known_candidate_is_context_not_ownership(self):
        person = Candidato.objects.create(organizacion=self.org, nombre='Titular conocido',
            origen_importacion='synthetic', identificador_origen='known')
        row = {'origen_importacion': 'synthetic', 'identificador_origen': 'known', 'nombre': person.nombre,
               'documentos': [{'archivo': 'unknown.png', 'identificador_origen': 'unknown.png'}]}
        self.run_batch([row], True)
        entry = EntradaPendiente.objects.get()
        self.assertEqual(entry.tipo_documento, 'otro')
        self.assertFalse(entry.clasificacion_confirmada)
        self.assertIsNone(entry.candidato_id)
        self.assertEqual(entry.contexto_recepcion['procedencia_candidato_contexto']['identificador_origen'], 'known')
        self.assertFalse(DocumentoCandidato.objects.exists())
        # Collaborators cannot enumerate or download unclassified originals.
        membership = Membresia.objects.get(usuario=self.user)
        membership.rol = 'colaborador'
        membership.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('entrada_descargar', args=[entry.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('entradas_pendientes')), 'unknown.png')

    def test_known_evaluation_cannot_enter_as_unknown_or_other(self):
        person = Candidato.objects.create(organizacion=self.org, nombre='Sintético')
        DocumentoCandidato.objects.create(candidato=person, tipo='evaluacion', nombre='Restringido',
            archivo=SimpleUploadedFile('evaluation.docx', (self.root / 'cv.docx').read_bytes()))
        for tipo in [None, 'otro', 'evaluacion']:
            row = self.pending()
            row['documentos'][0]['tipo'] = tipo
            self.assertIn('conflicto', self.run_batch([row], True))
        self.assertFalse(EntradaPendiente.objects.exists())

    def test_receipt_failure_cleans_file_and_does_not_block_next(self):
        from talento import entradas_services
        real = entradas_services.auditar

        def fail_first(entry, *args):
            if entry.identificador_origen == 'bad':
                raise ValidationError('synthetic audit failure')
            return real(entry, *args)

        with patch('talento.entradas_services.auditar', side_effect=fail_first):
            result = self.run_batch([self.pending('bad'), self.pending('good')], True)
        self.assertIn('error_recepcion', result)
        self.assertEqual(list(EntradaPendiente.objects.values_list('identificador_origen', flat=True)), ['good'])
        self.assertEqual(len(list((self.root / 'media').rglob('*.docx'))), 1)

    def test_review_records_changes_and_preserves_original_context(self):
        self.run_batch([self.pending()], True)
        entry = EntradaPendiente.objects.get()
        name = entry.archivo.name
        guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk,
            datos={'nombre': 'Nombre revisado', 'motivo_pendiente': 'Falta confirmar ubicación'}, fuente='Página 1 revisada')
        entry.refresh_from_db()
        revision = entry.revisiones.last()
        self.assertEqual(revision.datos['cambios']['nombre']['antes'], 'Nombre propuesto')
        self.assertEqual(revision.datos['cambios']['nombre']['despues'], 'Nombre revisado')
        self.assertEqual(revision.usuario, self.user)
        self.assertIsNotNone(revision.fecha)
        self.assertEqual(entry.archivo.name, name)
        with self.assertRaises(ValidationError):
            guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk,
                datos={'contexto_recepcion': {}}, fuente='Intento de cambiar recepción')
        # Replay does not overwrite the manual review or append duplicate revisions.
        self.run_batch([self.pending()], True)
        entry.refresh_from_db()
        self.assertEqual(entry.nombre, 'Nombre revisado')
        self.assertEqual(entry.revisiones.count(), 2)

    def test_pending_requires_permission_and_source(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='add_entradapendiente'))
        with self.assertRaises(PermissionDenied):
            self.run_batch([self.pending()])
        self.user.user_permissions.add(Permission.objects.get(codename='add_entradapendiente'))
        row = self.pending()
        row['pendiente']['fuente'] = ''
        self.assertIn('conflicto', self.run_batch([row], True))
        self.assertFalse(EntradaPendiente.objects.exists())

    def test_portal_contact_rejected_but_lack_of_profession_does_not_exclude(self):
        row = self.pending()
        row['pendiente']['datos'].update(email='noreply@chiletrabajos.cl', email_estado='disponible')
        self.assertIn('conflicto', self.run_batch([row]))
        self.assertFalse(EntradaPendiente.objects.exists())

    def test_mixed_unknown_replay_preserves_stable_context(self):
        row = {'nombre': 'Persona explícita', 'origen_importacion': 'synthetic', 'identificador_origen': 'mixed',
               'documentos': [{'archivo': 'cv.docx', 'identificador_origen': 'cv.docx', 'tipo': 'curriculum'},
                              {'archivo': 'unknown.png', 'identificador_origen': 'unknown.png'}]}
        self.run_batch([row], True)
        second = self.run_batch([row], True)
        self.assertIn('total=2 listos=0 pendientes=0 existentes=2 conflictos=0', second)
        self.assertEqual((Candidato.objects.count(), DocumentoCandidato.objects.count(),
                          EntradaPendiente.objects.count(), RevisionEntrada.objects.count()), (1, 1, 1, 1))

    def test_receipt_duplicates_in_manifest_are_counted_once_as_new(self):
        row = self.pending()
        result = self.run_batch([row, row], True)
        self.assertIn('total=2 listos=0 pendientes=1 existentes=1 conflictos=0', result)
        self.assertEqual(EntradaPendiente.objects.count(), 1)
        self.assertEqual(RevisionEntrada.objects.count(), 1)

    def test_pending_document_failure_does_not_drop_sibling(self):
        row = self.pending(documentos=[{'archivo': 'absent.pdf', 'identificador_origen': 'absent.pdf', 'tipo': 'curriculum'},
                                      {'archivo': 'cv.docx', 'identificador_origen': 'cv.docx', 'tipo': 'curriculum'}])
        result = self.run_batch([row], True)
        self.assertIn('total=2 listos=0 pendientes=1 existentes=0 conflictos=1', result)
        self.assertEqual(EntradaPendiente.objects.count(), 1)

    def test_paths_and_cross_organization_context_rejected_without_writes(self):
        other = Organizacion.objects.create(nombre='Ajena', slug='ajena')
        person = Candidato.objects.create(organizacion=other, nombre='Ajeno')
        row = self.pending(contexto_recepcion={'candidato_contexto_id': person.pk})
        self.assertIn('conflicto', self.run_batch([row], True))
        row = self.pending(documentos=[{'archivo': '../escape.pdf', 'identificador_origen': 'escape.pdf', 'tipo': 'curriculum'}])
        self.assertIn('conflicto', self.run_batch([row], True))
        (self.root / 'alias.docx').symlink_to(self.root / 'cv.docx')
        row['documentos'][0]['archivo'] = 'alias.docx'
        self.assertIn('enlace_simbolico', self.run_batch([row], True))
        self.assertFalse(EntradaPendiente.objects.exists())

    def test_pending_only_does_not_require_candidate_creation_permission(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='add_candidato'),
                                          Permission.objects.get(codename='add_documentocandidato'))
        self.run_batch([self.pending()], True)
        self.assertEqual(EntradaPendiente.objects.count(), 1)
        self.assertFalse(Candidato.objects.exists())

    def test_clear_flow_cannot_bypass_pending_or_evaluation(self):
        self.run_batch([self.pending()], True)
        clear = {'nombre': 'No atribuir automáticamente', 'origen_importacion': 'synthetic',
                 'identificador_origen': 'other', 'archivo': 'cv.docx'}
        self.assertIn('recepcion_pendiente_requiere_resolucion', self.run_batch([clear], True))
        self.assertFalse(Candidato.objects.exists())
        person = Candidato.objects.create(organizacion=self.org, nombre='Sintético')
        DocumentoCandidato.objects.create(candidato=person, tipo='evaluacion', nombre='Restringido',
            archivo=SimpleUploadedFile('evaluation.docx', (self.root / 'cv.docx').read_bytes()))
        self.assertIn('evaluacion_restringida', self.run_batch([clear], True))
        self.assertEqual(Candidato.objects.count(), 1)

    def test_invalid_empty_row_does_not_invent_documents(self):
        result = self.run_batch([self.pending(documentos=[]), {}], True)
        self.assertIn('total=0 listos=0 pendientes=0 existentes=0 conflictos=0', result)
        self.assertFalse(EntradaPendiente.objects.exists())
        self.assertFalse(Candidato.objects.exists())
