"""Offline mapping to actual core.Oportunidad model fields (verified 2026-10-24)."""
from delivery_contracts import prepare_delivery

def opportunity_fields(job, lead, organization_id):
    d=prepare_delivery(job)
    if d.action!='append_lead': raise ValueError('Only append_lead can create opportunity')
    if type(organization_id) is not int or organization_id<=0: raise ValueError('Valid organization required')
    if lead.get('consent') is not True: raise ValueError('Consent required')
    email=lead.get('email')
    if not isinstance(email,str) or '@' not in email: raise ValueError('Email required')
    email=email.strip().lower()
    name=str(lead.get('name') or '').strip()[:200]
    need=str(lead.get('need') or 'Consulta recibida desde formulario web').strip()
    if not need: raise ValueError('Need required')
    return {
        'organizacion_id':organization_id,
        'titulo':('Consulta web - '+(name or email))[:250],
        'origen':'consulta_entrante',
        'canal':'web',
        'nombre_consultante':name,
        'email_consultante':email,
        'telefono_consultante':str(lead.get('phone') or '')[:50],
        'necesidad':need,
        'estado':'nueva'
    }

def external_reference(job):
    """Idempotency reference for a separate mapping ledger, NOT Oportunidad field."""
    return prepare_delivery(job).idempotency_key
