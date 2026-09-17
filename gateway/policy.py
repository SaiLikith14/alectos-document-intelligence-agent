from fastapi import HTTPException


def trial_applies(enabled: bool, subject: str, admins: set[str]) -> bool:
    return enabled and subject not in admins


def check_allowance(consumed_or_reserved: int, allowance: int):
    if consumed_or_reserved >= allowance:
        raise HTTPException(403, {'code': 'trial_exhausted', 'message': 'You have used your free request for this agent.'})


def validate_owned_resources(records, document_ids, session_id):
    owned = {(r['kind'], str(r['resource_id'])): r for r in records}
    if session_id and ('session', str(session_id)) not in owned:
        raise HTTPException(404, 'Session not found')
    for doc_id in document_ids:
        document = owned.get(('document', str(doc_id)))
        if document is None:
            raise HTTPException(404, 'Document not found')
        if session_id and str(document['session_id']) != str(session_id):
            raise HTTPException(404, 'Document not available in this session')
