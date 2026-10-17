"""Bounded additive-empty-table contracts; also embedded in the root controller.

Trust remains the existing authorized publisher and protected-main workflow.
Hashes bind the reviewed contract to SQL/commit; they are not human signatures.
Unsupported SQL, modes, versions or evidence fail closed.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

MIGRATION_POLICY_BASE = 21
MIGRATION_POLICY_LIMIT = 262144


def migration_policy_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate migration policy key')
        result[key] = value
    return result


def migration_policy_load(data):
    if len(data) > MIGRATION_POLICY_LIMIT: raise ValueError('Migration policy too large')
    return json.loads(data, object_pairs_hook=migration_policy_unique)


def migration_policy_sql_tables(data):
    """Conservative lexical reader, deliberately narrower than MySQL DDL."""
    text = data.decode('utf-8')
    if '\\' in text or '/*' in text or '*/' in text:
        raise ValueError('SQL escapes/block comments require specialist review')
    tokens = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == '#' or (text.startswith('--', i) and (i+2 == len(text) or text[i+2].isspace())):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end+1
            tokens.append(' ')
        elif char in "'\"`":
            quote = char
            start = i
            i += 1
            while i < len(text):
                if text[i] == quote:
                    if i+1 < len(text) and text[i+1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else: raise ValueError('Unclosed SQL quote')
            # Backticks are identifiers; quoted strings are not SQL keywords.
            tokens.append(text[start:i] if quote == '`' else "'literal'")
        else:
            tokens.append(char)
            i += 1
    clean = ''.join(tokens)
    statements = clean.split(';')
    if statements[-1].strip(): raise ValueError('Terminated CREATE TABLE statements required')
    tables = []
    for statement in statements[:-1]:
        statement = statement.strip()
        match = re.match(r'CREATE\s+TABLE\s+`?(prp_[a-z][a-z0-9_]{0,58})`?\s*\(', statement, re.I)
        if not match: raise ValueError('Only explicit CREATE TABLE prp_* is supported')
        table = match[1]
        if table != table.lower() or table in tables: raise ValueError('Duplicate/noncanonical new table')
        body_start = match.end()
        depth = 1
        pos = body_start
        quoted_identifier = False
        while pos < len(statement) and depth:
            char = statement[pos]
            if char == '`': quoted_identifier = not quoted_identifier
            if not quoted_identifier:
                if char == '(': depth += 1
                if char == ')': depth -= 1
            pos += 1
        if depth: raise ValueError('Unbalanced CREATE TABLE')
        body = statement[body_start:pos-1]
        if re.search(r'[A-Za-z_`]\w*`?\s*\.\s*`?[A-Za-z_]',body):
            raise ValueError('Cross-schema identifiers require specialist review')
        if re.search(r'\b(CHECK|GENERATED|VIRTUAL|STORED|PARTITION|TABLESPACE|SELECT|OUTFILE|INFILE|CALL)\b', body, re.I):
            raise ValueError('Advanced DDL requires specialist review')
        if re.search(r'\bDEFAULT\s*\(', body, re.I):
            raise ValueError('Expression defaults require specialist review')
        tail = statement[pos:].strip()
        if not re.fullmatch(r'ENGINE\s*=\s*InnoDB\s+(?:DEFAULT\s+)?CHARSET\s*=\s*utf8mb4(?:\s+COLLATE\s*=\s*utf8mb4_[a-z0-9_]+)?', tail, re.I):
            raise ValueError('Only InnoDB utf8mb4 tables with bounded options are supported')
        if not re.search(r'\bPRIMARY\s+KEY\b', body, re.I): raise ValueError('Primary key required')
        tables.append(table)
    if not tables or len(tables) > 64: raise ValueError('Bounded nonempty table list required')
    return tables


def migration_policy_validate(policy, migrations, commit=None):
    expected = {'schema_version', 'rules'} | ({'commit'} if commit is not None else set())
    if not isinstance(policy, dict) or set(policy) != expected or type(policy['schema_version']) is not int or policy['schema_version'] != 1:
        raise ValueError('Unsupported migration policy schema')
    if commit is not None and (not re.fullmatch('[a-f0-9]{40}', commit) or policy['commit'] != commit):
        raise ValueError('Migration policy commit mismatch')
    if not isinstance(policy['rules'], list) or len(policy['rules']) > 128: raise ValueError('Invalid migration rules')
    rules = {}
    seen_tables = set()
    for rule in policy['rules']:
        if not isinstance(rule, dict) or set(rule) != {'version','file','sha256','mode','tables'}:
            raise ValueError('Invalid migration rule fields')
        version = rule['version']
        if type(version) is not int or not MIGRATION_POLICY_BASE < version <= 1000 or version in rules:
            raise ValueError('Invalid/duplicate migration rule version')
        if rule['mode'] != 'create-empty': raise ValueError('Unsupported migration preservation mode')
        if version not in migrations: raise ValueError('Policy references missing SQL')
        name, data = migrations[version]
        if rule['file'] != name or hashlib.sha256(data).hexdigest() != rule['sha256']:
            raise ValueError('Policy SQL filename/digest mismatch')
        tables = migration_policy_sql_tables(data)
        if rule['tables'] != tables or seen_tables.intersection(tables): raise ValueError('Policy table declaration mismatch')
        seen_tables.update(tables)
        rules[version] = tables
    if set(rules) != {v for v in migrations if v > MIGRATION_POLICY_BASE}:
        raise ValueError('Every future migration requires an exact preservation rule')
    return rules


def migration_policy_for_release(release, meta, from_version):
    path = release / 'migration-policy.json'
    if not path.exists():
        if meta['schema_version'] > MIGRATION_POLICY_BASE: raise ValueError('Missing migration policy')
        return set()  # Legacy <=V21 artifacts retain all original hardcoded guards.
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MIGRATION_POLICY_LIMIT: raise ValueError('Invalid migration policy file')
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta['files'].get('migration-policy.json'):
        raise ValueError('Migration policy artifact digest mismatch')
    migrations = {}
    with zipfile.ZipFile(release/'backend.jar') as jar:
        for info in jar.infolist():
            match = re.fullmatch(r'BOOT-INF/classes/db/migration/(V(\d+)__[^/]+\.sql)', info.filename)
            if not match:
                if info.filename.startswith('BOOT-INF/classes/db/migration/') and not info.is_dir():
                    raise ValueError('Only declared versioned SQL resources are supported; Java/callback/repeatable migrations require specialist review')
                continue
            version = int(match[2])
            if version in migrations or info.file_size > 1048576: raise ValueError('Duplicate/oversize JAR migration')
            migrations[version] = (match[1], jar.read(info))
    if not migrations or max(migrations) != meta['schema_version']: raise ValueError('Policy/JAR schema mismatch')
    rules = migration_policy_validate(migration_policy_load(path.read_bytes()), migrations, meta['commit'])
    return {table for version, tables in rules.items() if from_version < version <= meta['schema_version'] for table in tables}
