"""Bounded response-header buffers for EACH OAuth reverse-proxy hop.

This module only renders reviewed configuration. It never installs or reloads.
Large OAuth state can enlarge Keycloak's restart cookie even with buffering off.
"""

def render_oauth_header_buffers(indent='    '):
    if indent not in ('', '    ', '        '):
        raise ValueError('Fixed indentation required')
    return '\n'.join(indent + line for line in (
        'proxy_buffer_size 16k;',
        'proxy_buffers 4 16k;',
        'proxy_busy_buffers_size 32k;',
    ))
