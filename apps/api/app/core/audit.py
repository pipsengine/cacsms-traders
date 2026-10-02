import json,uuid
from .security import iso

def write_audit(c,tenant_id,user_id,action,entity_type=None,entity_id=None,before=None,after=None,reason=None,correlation_id=None):
    c.execute('INSERT INTO audit_events(id,tenant_id,user_id,action,entity_type,entity_id,previous_json,new_json,reason,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(
        str(uuid.uuid4()),tenant_id,user_id,action,entity_type,entity_id,json.dumps(before) if before is not None else None,json.dumps(after) if after is not None else None,reason,correlation_id or str(uuid.uuid4()),iso()))
