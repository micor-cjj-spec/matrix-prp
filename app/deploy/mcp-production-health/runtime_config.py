"""Production-shaped configuration, parameterized only for an independently verified owner.
No database credential, owner default or live key is embedded.
"""
from contract import CLIENT,FIRST_PARTY,FIRST_REDIRECT,ISSUER,JWKS,RESOURCE,SCOPES

def runtime_config(owner):
    if not isinstance(owner,int) or isinstance(owner,bool) or owner<=0:raise ValueError('VERIFIED_OWNER_REQUIRED')
    return {'spring':{'flyway':{'enabled':False},'ai':{'mcp':{'server':{'enabled':True}}}},
      'matrix-prp':{'mcp':{'enabled':True,'write-enabled':True,'production-wellness-only':True,
       'production-tasks-only':False,'expanded-user-ids':str(owner),'expanded-client-id':CLIENT,
       'allowed-origins':'https://micor.top','oauth':{'enabled':True,'issuer':ISSUER,
        'jwk-set-uri':ISSUER+'/protocol/openid-connect/certs','resource':RESOURCE,
        'advertised-scopes':','.join(SCOPES),'first-party-link':{'enabled':True,'client-id':FIRST_PARTY,'redirect-uri':FIRST_REDIRECT}}}}}
