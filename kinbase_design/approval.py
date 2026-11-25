"""Sign-off of a design version by an approver this installation is configured to trust.

Which GitHub accounts may approve is local configuration, never a name in this system:
`.hylonome/config.toml` in the working directory (git-ignored), `~/.config/hylonome/config.toml`,
or the file named by HYLONOME_CONFIG:

    [approval]
    approvers = ["github-login", "another-login"]
    require = false   # when true, Apply refuses a version no configured approver signed off

The approver's identity is the account the local GitHub CLI is authenticated as. A record
names that account and the exact version hash; it is not a cryptographic signature. Its
trust comes from this configuration and from the history of the repository that holds it.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import tomllib
from . import __version__
from .language import validate
from .language.versions import digest, mint
from .storage import identifier, inside, load_language, read_json, write_json

APPROVAL_TIMEOUT_SECONDS = 15
LOGIN = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')


def config_path():
    if os.environ.get('HYLONOME_CONFIG'):
        return Path(os.environ['HYLONOME_CONFIG']).expanduser().resolve()
    for candidate in (Path.cwd() / '.hylonome' / 'config.toml', Path.home() / '.config' / 'hylonome' / 'config.toml'):
        if candidate.is_file():
            return candidate
    return None


def settings():
    path = config_path()
    values = tomllib.loads(path.read_text()).get('approval', {}) if path and path.is_file() else {}
    if not isinstance(values, dict) or set(values) - {'approvers', 'require'}:
        raise ValueError('approval configuration takes only approvers and require')
    approvers = values.get('approvers', [])
    if not isinstance(approvers, list) or any(not isinstance(v, str) or not LOGIN.fullmatch(v) for v in approvers):
        raise ValueError('approval.approvers must be a list of GitHub logins')
    require = values.get('require', False)
    if not isinstance(require, bool):
        raise ValueError('approval.require must be true or false')
    return {'config': str(path) if path else None, 'approvers': sorted({v.lower() for v in approvers}), 'require': require}


def github_login():
    """The account the local GitHub CLI is authenticated as; never a typed name."""
    try:
        result = subprocess.run(['gh', 'api', 'user', '--jq', '.login'], capture_output=True, text=True,
                                timeout=APPROVAL_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Cannot verify a GitHub identity: ' + str(exc)) from None
    login = result.stdout.strip()
    if result.returncode or not LOGIN.fullmatch(login):
        raise ValueError('Cannot verify a GitHub identity: ' + (result.stderr.strip() or 'gh returned no login')[:300])
    return login


def records_path(library, language_id, version):
    return inside(library, 'languages', identifier(language_id), 'approvals', identifier(version) + '.json')


def records(library, language_id, version):
    path = records_path(library, language_id, version)
    value = read_json(path) if path.is_file() else []
    if not isinstance(value, list):
        raise ValueError('Approval records must be a list')
    return value


def status(library, language_id, version=None, configured=None):
    configured = configured or settings()
    version = version or digest(load_language(library, language_id))
    entries = [{**entry, 'configured': str(entry.get('approver', '')).lower() in configured['approvers']}
               for entry in records(library, language_id, version)
               if isinstance(entry, dict) and entry.get('version') == version]
    approved = any(entry['configured'] for entry in entries)
    return {'language': language_id + '@' + version, 'approved': approved, 'required': configured['require'],
            'approvers': [entry['approver'] for entry in entries if entry['configured']],
            'records': entries, 'config': configured['config'],
            'label': ('approved by ' + ', '.join(e['approver'] for e in entries if e['configured'])) if approved else 'not approved'}


def approve(library, language_id, note=''):
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError('Approval note is too long')
    configured = settings()
    if not configured['approvers']:
        raise ValueError('No approvers are configured for this installation (see approval.approvers in .hylonome/config.toml)')
    result = validate(library, language_id)
    if not result['accepted']:
        raise ValueError('Only a version that passes validation can be approved')
    version = mint(library, language_id)['ref'].split('@', 1)[1]
    login = github_login()
    if login.lower() not in configured['approvers']:
        raise ValueError(f'GitHub account {login} is not a configured approver for this installation')
    entries = records(library, language_id, version)
    if not any(str(entry.get('approver', '')).lower() == login.lower() for entry in entries if isinstance(entry, dict)):
        entries.append({'version': version, 'language': language_id, 'approver': login, 'method': 'github-cli',
                        'approved_at': datetime.now(timezone.utc).isoformat(), 'note': note.strip(),
                        'tool': 'hylonome ' + __version__})
        write_json(records_path(library, language_id, version), entries)
    return status(library, language_id, version, configured)
