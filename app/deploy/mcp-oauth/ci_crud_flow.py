"""Synthetic CRUD acceptance, called only inside the disposable CI PKCE runner."""
import json
import os
from datetime import date
from decimal import Decimal

SCOPES = ['prp.tasks.read', 'prp.wellness.read', 'prp.write.create', 'prp.write.status',
          'prp.write.confirm', 'prp.write.update', 'prp.write.delete']


def run(flow, opener, prp_jwt, password, login_password):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('MCP_E2E_CRUD') != 'true':
        raise RuntimeError('CRUD runner requires explicit disposable CI opt-in')
    if (os.environ.get('MCP_E2E_EXACT_CHATGPT') != 'true'
            or flow.CLIENT != 'https://chatgpt.com/oauth/client.json'
            or flow.ISSUER != 'https://auth-e2e.localhost/realms/prp-mcp'):
        raise RuntimeError('CRUD runner requires disposable exact-client authentication')
    base = 'https://prp-e2e.localhost'
    flow.json_response(flow.request(opener, base+'/api/mcp/clients', bearer=prp_jwt,
        data={'clientId':flow.CLIENT,'scopes':SCOPES,'password':password}), 'Synthetic CRUD grant')
    code, verifier = flow.code_pkce(opener, 'e2e-keycloak-owner', login_password,
                                     requested_scopes='openid '+' '.join(SCOPES))
    from pathlib import Path
    from ci_static_client_jwt import assertion, ASSERTION_TYPE
    key = os.environ.get('MCP_E2E_EXACT_CLIENT_KEY', '')
    runner_temp = os.environ.get('RUNNER_TEMP', '')
    if not runner_temp or not key or not Path(key).is_file() or not Path(key).resolve().is_relative_to(Path(runner_temp).resolve()):
        raise RuntimeError('CRUD requires a temporary synthetic client key')
    token_form = {'grant_type':'authorization_code','client_id':flow.CLIENT,
        'redirect_uri':flow.CALLBACK,'code':code,'code_verifier':verifier,'resource':flow.RESOURCE,
        'client_assertion_type':ASSERTION_TYPE,
        'client_assertion':assertion(Path(key), issuer=flow.CLIENT, subject=flow.CLIENT,
                                   aud=flow.ISSUER+'/protocol/openid-connect/token')}
    tokens = flow.json_response(flow.request(opener, flow.ISSUER+'/protocol/openid-connect/token',
        form=True, data=token_form),
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
    # Dedicated structured meal E2E. Synthetic owner and disposable database only:
    # a generic RECORD is deliberately NOT used for nutritional statistics.
    meal_date = date.today().isoformat()
    meal_input = {'mealDate': meal_date, 'mealType': 'LUNCH',
        'note': 'CI-only estimates; unknown macros must remain null',
        'items': [
            {'foodId': None, 'name': 'CI synthetic chicken', 'grams': 180, 'calories': 360.00},
            {'foodId': None, 'name': 'CI synthetic wontons', 'grams': 200, 'calories': 260.00}
        ]}
    call('prp_prepare_meal', {'mealDate': meal_date, 'mealType': 'LUNCH',
        'items': [{'foodId': None, 'name': 'Missing calories', 'grams': 180}]}, denied=True)
    before = call('prp_wellness_daily', {'date': meal_date})
    if before['mealCount'] != 0 or before['calories'] is not None:
        raise RuntimeError('MEAL_CI_EXPECTED_EMPTY_DISPOSABLE_DAY')
    proposal = call('prp_prepare_meal', meal_input)
    if proposal['kind'] != 'MEAL' or len(proposal['values']['items']) != 2:
        raise RuntimeError('MEAL_CI_TYPED_DRAFT_MISMATCH')
    call('prp_confirm_draft', {'draftId': proposal['draftId']}, denied=True)
    if call('prp_wellness_daily', {'date': meal_date})['mealCount'] != 0:
        raise RuntimeError('MEAL_CI_PREAPPROVAL_BUSINESS_WRITE')
    approve(proposal)
    saved_meal = call('prp_confirm_draft', {'draftId': proposal['draftId']})
    if saved_meal['kind'] != 'MEAL' or len(saved_meal['saved']['items']) != 2:
        raise RuntimeError('MEAL_CI_SAVED_ITEMS_MISMATCH')
    replay = call('prp_confirm_draft', {'draftId': proposal['draftId']})
    if replay['alreadySaved'] is not True or replay['saved']['id'] != saved_meal['saved']['id']:
        raise RuntimeError('MEAL_CI_NOT_IDEMPOTENT')
    daily = call('prp_wellness_daily', {'date': meal_date})
    if (daily['mealCount'] != 1 or Decimal(str(daily['calories'])) != Decimal('620.00')
            or daily.get('proteinG') is not None or daily.get('carbsG') is not None
            or daily.get('fatG') is not None):
        raise RuntimeError('MEAL_CI_DAILY_STRUCTURED_TOTAL_MISMATCH')
    duplicate = call('prp_prepare_meal', meal_input)
    approve(duplicate)
    call('prp_confirm_draft', {'draftId': duplicate['draftId']}, denied=True)
    if call('prp_wellness_daily', {'date': meal_date})['mealCount'] != 1:
        raise RuntimeError('MEAL_CI_DUPLICATE_LUNCH_WRITTEN')
    print('PASS E2E MEAL: real OAuth, typed draft, owner approval, 620 kcal daily, replay and duplicate denial.')

    flow.json_response(flow.request(opener,base+'/api/mcp/clients',bearer=prp_jwt,
        data={'clientId':flow.CLIENT,'scopes':['prp.tasks.read'],'password':password}), 'Reduce synthetic client scopes')
    call('prp_prepare_task',{'moduleCode':'work','title':'Must be denied'},denied=True)
    call('prp_prepare_meal', meal_input, denied=True)
    print('PASS E2E CRUD: real OAuth task create/read/update/delete, owner approval, replay and scope reduction.')
