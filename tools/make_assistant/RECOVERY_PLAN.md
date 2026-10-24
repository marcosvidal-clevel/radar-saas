# Recuperación y confirmación: revisión de seguridad

Estado: diseño offline. No hay worker real ni conectores activos.

## Hallazgos
1. `Outbox.mark_success(job_id)` admite confirmación sin recibo externo. Un integrador debe bloquear esa ruta o exigir `verify_receipt` antes de reconocer entrega.
2. `eligible_jobs` lee trabajos pendientes sin reserva exclusiva: dos workers podrían tomar el mismo trabajo. Requiere claim atómico con lease, vencimiento y token de propietario.
3. `mark_failure` reintenta inmediatamente, sin backoff; incorporar `next_attempt_at`, retraso exponencial, jitter y límites.
4. Si Sheets acepta una fila pero se corta la conexión antes del acuse, puede duplicarse en reintento. Exigir reconciliación por clave externa antes de repetir.
5. `notify_internal` se bloquea si no se confirma `append_lead`; conservar esta dependencia en el worker final.
6. `Outbox` almacena payload de lead en texto claro. No procesar datos reales sin controles de cifrado, retención, acceso y borrado.

## Puertas antes de producción
- Tests integrados completos ejecutados con datos sintéticos.
- Contrato de RADAR validado contra modelos y permisos multiempresa.
- Adaptador Sheets con verificación por clave externa y registro de recibos.
- Worker con lease y reintentos; alertas y recuperación de dead letters.
- API Make de solo lectura configurada en gestor de secretos.
- Aprobación específica antes de escritura, activación de escenarios o publicación web.

No confundir pruebas unitarias con entrega real o funcionamiento autónomo.
