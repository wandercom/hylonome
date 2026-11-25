"""A design package is a directory. It may live in the library or anywhere else.

A package holds `working.json`, its immutable `versions/`, approved `assets/`, shared
`provenance/` and `approvals/`. A package saved outside the library also carries the
Vocabulary version it pins under `vocabulary/`, so it can be applied from any path.

Operations run against a staged library holding the package. Afterwards the working copy
and new or appended records are written back; nothing in the package is deleted.
"""
from contextlib import contextmanager
import filecmp
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from .storage import ID, identifier, inside, read_json

PACKAGE_FILE = 'working.json'
MUTABLE = (PACKAGE_FILE, 'revisions.json')  # working copy and its revision journal
APPENDABLE = ('approvals',)          # records that gain entries


def is_path(reference):
    """A package path, as opposed to a language id in the configured library."""
    if not isinstance(reference, str) or not reference:
        return False
    return os.sep in reference or reference.startswith(('.', '~')) or not ID.fullmatch(reference)


def read_package(directory):
    directory = Path(directory).expanduser().resolve()
    if not (directory / PACKAGE_FILE).is_file():
        raise ValueError('Not a design package (no working.json): ' + str(directory))
    document = read_json(directory / PACKAGE_FILE)
    if not isinstance(document, dict):
        raise ValueError('working.json must be a language object')
    identifier(document.get('id'))
    if not isinstance(document.get('vocabulary'), str):
        raise ValueError('working.json must pin a vocabulary version')
    identifier(document['vocabulary'])
    return directory, document


def vocabulary_source(library, directory, version):
    bundled = directory / 'vocabulary' / version
    if (bundled / 'vocabulary.json').is_file():
        return bundled
    installed = inside(library, 'vocabulary', version)
    if (installed / 'vocabulary.json').is_file():
        return installed
    raise ValueError(f'The package pins vocabulary {version}, which neither the package nor this installation holds')


def write_back(staged, original):
    """Copy the working copy, appended records and new files home; never delete."""
    for path in sorted(staged.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(staged)
        target = original / relative
        top = relative.parts[0]
        if top == 'vocabulary':
            continue
        if target.exists():
            if str(relative) in MUTABLE or top in APPENDABLE:
                if not filecmp.cmp(path, target, shallow=False):
                    shutil.copyfile(path, target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


@contextmanager
def opened(library, reference):
    """Yield (library, language id) for a library id or a package path."""
    if not is_path(reference):
        yield library, reference
        return
    directory, document = read_package(reference)
    language_id, version = document['id'], document['vocabulary']
    with TemporaryDirectory(prefix='hylonome-package-') as temporary:
        staged = Path(temporary)
        library_vocabulary = inside(library, 'vocabulary')
        if library_vocabulary.is_dir():
            shutil.copytree(library_vocabulary, staged / 'vocabulary')
        if not (staged / 'vocabulary' / version / 'vocabulary.json').is_file():
            shutil.copytree(vocabulary_source(library, directory, version), staged / 'vocabulary' / version, dirs_exist_ok=True)
        package = staged / 'languages' / language_id
        shutil.copytree(directory, package, ignore=shutil.ignore_patterns('vocabulary'))
        yield staged, language_id
        write_back(package, directory)


def bundle_vocabulary(library, directory, version):
    """Make a package portable: carry the exact Vocabulary version it pins."""
    source = vocabulary_source(library, directory, version)
    target = directory / 'vocabulary' / version
    if source.resolve() != target.resolve():
        shutil.copytree(source, target, dirs_exist_ok=True)
