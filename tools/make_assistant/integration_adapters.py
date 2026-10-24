"""Offline integration payloads. No network or credentials."""
from delivery_contracts import prepare_delivery

SHEET_COLUMNS = ('idempotency_key', 'email', 'name', 'source', 'consent')

def sheets_row(job, lead):
    delivery = prepare_delivery(job)
    if delivery.action != 'append_lead':
        raise ValueError('Sheets adapter requires append_lead')
    if lead.get('consent') is not True:
        raise ValueError('Explicit consent required')
    email = lead.get('email')
    if not isinstance(email, str) or '@' not in email:
        raise ValueError('Valid email required')
    return dict(zip(SHEET_COLUMNS, (delivery.idempotency_key, email.strip().lower(),
                                   str(lead.get('name') or '').strip(),
                                   str(lead.get('source') or 'web').strip(), True)))

def radar_opportunity(job, lead, organization_id):
    delivery = prepare_delivery(job)
    if delivery.action != 'append_lead':
        raise ValueError('RADAR requires persisted lead action')
    if not isinstance(organization_id, int) or isinstance(organization_id, bool) or organization_id <= 0:
        raise ValueError('Organization ID required')
    row = sheets_row(job, lead)
    return {'organization_id': organization_id,
            'external_key': delivery.idempotency_key,
            'origin': 'consulta_entrante', 'channel': 'web',
            'status': 'nueva', 'contact_email': row['email']}
