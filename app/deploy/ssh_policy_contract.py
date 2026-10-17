"""Public shape of candidate evidence, not an approved policy or acceptance rule."""
BASELINE_FIELDS={'gateway_sha256','authorized_keys_sha256','effective_sshd_sha256','policy_files_sha256',
                 'attestor_sha256','deployment_key_fingerprint','subsystem_command','forced_command','behavior'}
PROOF_FIELDS={'schema_version','challenge','observed_utc','baseline','connection_bound','loaded_policy_verified','trusted_paths'}
GATEWAY='/usr/local/bin/prp-deploy-gateway'
SUBSYSTEM='/usr/lib/openssh/sftp-server'
BEHAVIOR='openssh-10.0-subsystem-stderr-ignore'
