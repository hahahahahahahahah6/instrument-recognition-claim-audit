"""Offline prose matching and conservative module-level AST evidence."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys

from . import __version__
from .phrases import INSTRUMENT, NOINSTRUMENT

GENERIC = frozenset('''classify_instrument detect_instrument estimate_instrument get_instrument instrument_detect instrument_classify predict_instrument instrument_predict identify_instrument instrument_identify classify_musical_instrument detect_musical_instrument estimate_musical_instrument get_musical_instrument predict_musical_instrument identify_musical_instrument classify_song_instrument detect_song_instrument estimate_song_instrument predict_song_instrument identify_song_instrument analyze_instrument analyse_instrument instrument_analyze instrument_analyse classify_audio_instrument detect_audio_instrument predict_audio_instrument classify_track_instrument detect_track_instrument predict_track_instrument recognize_instrument recognise_instrument instrument_recognize instrument_recognise label_instrument instrument_label determine_instrument instrument_determine classify_instruments detect_instruments'''.split())


def prose(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            lines.append('')
        elif match:
            fence = match[1]
            lines.append('')
        else:
            lines.append(line)
    return '\n'.join(lines)


def claims(text):
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', prose(text)):
        normalized = ' '.join(paragraph.lower().replace("n't", ' not').replace('-', ' ').split())
        for phrase in sorted(NOINSTRUMENT, key=lambda p: (-len(p), p)):
            normalized, count = re.subn(r'\b' + re.escape(phrase) + r'\b', ' ', normalized)
            negative |= bool(count)
        for phrase in sorted(INSTRUMENT, key=lambda p: (-len(p), p)):
            normalized, count = re.subn(r'\b' + re.escape(phrase) + r'\b', ' ', normalized)
            positive |= bool(count)
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    local = {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    functions = {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    aliases = {}
    for n in nodes:
        if isinstance(n, ast.ImportFrom):
            for item in n.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(n, ast.Import):
            for item in n.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name

    def name(func):
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return aliases.get(func.id, func.id).split('.')[-1]
        return ''

    def constructor(call):
        if not isinstance(call, ast.Call):
            return False
        target = name(call.func)
        return (target.endswith('InstrumentClassifier') and target not in local
                and not (isinstance(call.func, ast.Name) and call.func.id in local))

    bindings = set()
    for n in nodes:
        if isinstance(n, (ast.Assign, ast.AnnAssign)) and constructor(n.value):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            bindings.update(t.id for t in targets if isinstance(t, ast.Name))
    for n in nodes:
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        target = name(f)
        if target in GENERIC and target not in functions:
            if isinstance(f, ast.Attribute) or (isinstance(f, ast.Name) and f.id in aliases and f.id not in functions):
                return True
        if isinstance(f, ast.Attribute) and f.attr == 'predict':
            if constructor(f.value) or (isinstance(f.value, ast.Name) and f.value.id in bindings):
                return True
    return False


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise OSError('Root must be a readable directory')
    ignored = [Path(p).as_posix().strip('/') for p in ignore]
    positive = negative = production = testing = False
    inspected = []
    def onerror(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        base = Path(directory)
        def excluded(path):
            rel = path.relative_to(root).as_posix()
            return path.is_symlink() or any(rel == p or rel.startswith(p + '/') for p in ignored)
        dirs[:] = sorted(d for d in dirs if not excluded(base / d))
        for filename in sorted(files):
            path = base / filename
            if excluded(path):
                continue
            rel = path.relative_to(root)
            parts = rel.parts
            doc = rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in parts[:-1])
            if doc:
                p, n = claims(path.read_text(encoding='utf-8'))
                positive |= p
                negative |= n
                inspected.append(rel.as_posix())
            if path.suffix == '.py' and not {'fixtures', 'docs', 'examples'}.intersection(parts[:-1]):
                found = evidence(path.read_text(encoding='utf-8'))
                test = 'tests' in parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
                testing |= found and test
                production |= found and not test
                inspected.append(rel.as_posix())
    findings = []
    if positive and not production:
        findings.append({'id': 'documented-instrument-recognition-claim-false', 'severity': 'MEDIUM' if testing else 'HIGH', 'message': 'Affirmative documentation lacks production call evidence.'})
    if negative and production:
        findings.append({'id': 'documented-no-instrument-recognition-claim-false', 'severity': 'HIGH', 'message': 'Negative documentation conflicts with production call evidence.'})
    return {'verdict': 'FAIL' if findings else 'PASS', 'findings': findings, 'production_evidence': production, 'test_evidence': testing, 'inspected': inspected}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=['LOW', 'MEDIUM', 'HIGH'], default='HIGH')
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore)
    except (OSError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{id} {severity}: {message}'.format(**finding))
        if args.verbose:
            print(json.dumps({k: v for k, v in result.items() if k not in ('verdict', 'findings')}))
    levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
    return 2 if any(levels[f['severity']] >= levels[args.fail_on] for f in result['findings']) else 0
