# django__django-10914 Module Assignment Diagnostic

Date: 2026-06-08

Instance: `django__django-10914`

Critical file: `django/conf/global_settings.py`

## Current Snapshot

Latest isolated Django scan before the fix:

`3d5ac2f7-a479-47ae-95ab-a581dc80fbd3`

Current entities for `global_settings.py`:

- `file`: `django/conf/global_settings.py`
- `module`: `django.conf.global_settings`
- `function`: `django.conf.global_settings.gettext_noop`

Current chunks:

- `file_summary` for `django/conf/global_settings.py`
- `symbol` chunk for `django.conf.global_settings.gettext_noop`

`FILE_UPLOAD_PERMISSIONS` exists in the raw source file, but it does not appear in either current chunk.

## Search Diagnosis

Full issue query:

- `django/conf/global_settings.py` rank in top 100: not found

Single-token query `FILE_UPLOAD_PERMISSIONS`:

- general BM25 top 100: target file not found
- source-code BM25 top 100: target file not found

The single token still retrieves upload/permission-related files such as `django/core/files/storage.py`, so the lexical term is useful. The target file misses because the current indexed chunks do not expose the module-level setting assignment.

## Root Cause

Current Python parser extracts module, function, class, method, imports, calls, and inherits. It does not extract module-level static assignments.

Current Python chunker emits symbol chunks for functions, methods, classes, and routes. It does not emit symbol chunks for module-level settings assignments.

Therefore:

```python
FILE_UPLOAD_PERMISSIONS = 0o644
```

is present in source but absent from the FTS-searchable chunk set.

## Implementation Gate

All required facts are confirmed:

- `global_settings.py` is indexed.
- `FILE_UPLOAD_PERMISSIONS` exists in the original file.
- no `module_assignment` entity exists before the fix.
- no assignment chunk exists before the fix.
- the assignment token has localization value, but cannot hit the target while absent from chunks.
