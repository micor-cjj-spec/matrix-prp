# Uninstalled controller proposals

`private_backup_controller.py` preserves an older feature-line proposal that
opens dump files exclusively, mode 0600, without following symlinks. It is **not**
an approved controller, installer, deployment entry point or actual server
inventory. Do not execute it or copy it into `/usr/local/sbin`.

The approved fixture remains byte-identical to main's independently approved
`c329836e...` controller and its manifest is unchanged. Tests extract only this
proposal's `dump()` AST and use a synthetic in-memory writer; no database or
container is accessed. This retains the security proposal without relabeling
unapproved bytes as installed/approved merely to make CI green.

Activating the proposal would require independent installed-byte measurement,
exact diff/hash review, backup, isolated rehearsal and separate administrator
authorization. The publication hold remains in force. A passing proposal test
does not establish that production backups already have these stronger flags.
