"""Synthetic CRUD acceptance, called only inside the disposable CI PKCE runner."""
import json
import os

SCOPES = ['prp.tasks.read', 'prp.write.create', 'prp.write.status',
          'prp.write.confirm', 'prp.write.update', 'prp.write.delete']


def run(flow, opener, prp_jwt, password, login_password):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('MCP_E2E_CRUD') != 'true':
        raise RuntimeError('CRUD runner requires explicit disposable CI opt-in')
    base = 'https://prp-e2e.localhost'
    flow.json_response(flow.request(opener, base+'/api/mcp/clients', bearer=prp_jwt,
        data={'clientId':flow.CLIENT,'scopes':SCOPES,'password':password}), 'Synthetic CRUD grant')
    code, verifier = flow.code_pkce(opener, 'e2e-keycloak-owner', login_password,
                                     requested_scopes='openid '+' '.join(SCOPES))
    tokens = flow.json_response(flow.request(opener, flow.ISSUER+'/protocol/openid-connect/token',
        form=True, data={'grant_type':'authorization_code','client_id':flow.CLIENT,
        'redirect_uri':flow.CALLBACK,'code':code,'code_verifier':verifier,'resource':flow.RESOURCE}),
        'Synthetic CRUD PKCE exchange')
    token = tokens['access_token']

    def call(name, arguments, denied=False):
        status, body = flow.jsonrpc(opener, token, 100, 'tools/call', {'name':name,'arguments':arguments})
        result = body.get('result', {})
        failed = bool(body.get('error') or result.get('isError'))
        if denied:
            if status != 200 or not failed:raise RuntimeError('CRUD rejection contract failed')
            return None
        if status != 200 or failed:raise RuntimeError('CRUD tool failed: '+name)
        structured = result.get('structuredContent')
        if isinstance(structured, dict):return structured
        text = ''.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')
        return json.loads(text)

    def approve(draft):
        outcome=flow.json_response(flow.request(opener,base+'/api/mcp/approval/drafts/'+draft['draftId']+'/approve',
            bearer=prp_jwt,data={'password':password}), 'Synthetic owner approval')
        if outcome.get('data',{}).get('status')!='APPROVED':raise RuntimeError('CRUD approval failed')

    created=call('prp_prepare_task',{'moduleCode':'work','title':'Synthetic CRUD before','priority':'low'})
    call('prp_confirm_draft',{'draftId':created['draftId']},denied=True)
    approve(created)
    saved=call('prp_confirm_draft',{'draftId':created['draftId']})
    task_id=saved['saved']['id']
    if call('prp_task_get',{'taskId':task_id})['title']!='Synthetic CRUD before':
        raise RuntimeError('CRUD create/read mismatch')
    changed=call('prp_prepare_task_update',{'taskId':task_id,'moduleCode':'work',
        'title':'Synthetic CRUD after','priority':'high','status':'done'})
    approve(changed);call('prp_confirm_draft',{'draftId':changed['draftId']})
    row=call('prp_task_get',{'taskId':task_id})
    if row['title']!='Synthetic CRUD after' or row['status']!='done':raise RuntimeError('CRUD update mismatch')
    removed=call('prp_prepare_task_delete',{'taskId':task_id})
    approve(removed);call('prp_confirm_draft',{'draftId':removed['draftId']})
    if call('prp_confirm_draft',{'draftId':removed['draftId']})['alreadySaved'] is not True:
        raise RuntimeError('CRUD deletion replay was not idempotent')
    call('prp_task_get',{'taskId':task_id},denied=True)
    flow.json_response(flow.request(opener,base+'/api/mcp/clients',bearer=prp_jwt,
        data={'clientId':flow.CLIENT,'scopes':['prp.tasks.read'],'password':password}), 'Reduce synthetic client scopes')
    call('prp_prepare_task',{'moduleCode':'work','title':'Must be denied'},denied=True)
    print('PASS E2E CRUD: real OAuth task create/read/update/delete, owner approval, replay and scope reduction.')
