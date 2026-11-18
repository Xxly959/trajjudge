import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


DEMO = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'samples/dataset_demo.py'))
write_demo = DEMO['write_demo']
write_rows = DEMO['write_rows']


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_dataset.py'


def run_dataset(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), *args],
                          capture_output=True, text=True)


def test_dataset_build_preserves_evidence_and_groups_tasks(tmp_path):
    outputs = write_demo(tmp_path)
    command = [sys.executable, str(SCRIPT), '--root', str(tmp_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    target = outputs / 'dataset'
    current = target / 'snapshots' / (target / 'CURRENT').read_text().strip()
    dataset = current / 'trajectories.jsonl'
    report = current / 'quality.json'
    first_bytes = dataset.read_bytes(), report.read_bytes()
    records = {row['trace_id']: row for row in map(json.loads, dataset.read_text().splitlines())}
    assert set(records) == {'a', 'b', 'c'}
    assert records['a']['split'] == records['b']['split'] != records['c']['split']
    assert records['a']['judgments']['human']['passed'] is False
    assert records['a']['judgments']['claw_eval']['passed'] is True
    assert records['a']['judgments']['openjudge'][0]['score'] == 1
    assert records['b']['judgments']['human'] is None
    assert records['c']['judgments']['openjudge'] == []
    assert b'B01' not in first_bytes[0]
    quality = json.loads(first_bytes[1])
    assert quality['human_coverage'] == {'labeled': 1, 'selected_unlabeled': 1, 'not_selected': 1}
    assert quality['excluded'][0]['reason'] == 'missing_trace_end'
    assert quality['human_claw_disagreements'] == 1
    assert quality['exact_message_duplicate_rows'] == 1
    subprocess.run(command, check=True, capture_output=True)
    assert first_bytes == (dataset.read_bytes(), report.read_bytes())
    source = outputs / 'traces/a.jsonl'
    source.write_bytes(source.read_bytes() + b'\n')
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'frozen annotation evidence changed' in result.stderr
    assert (target / 'CURRENT').read_text().strip() == current.name
    assert first_bytes == (dataset.read_bytes(), report.read_bytes())


@pytest.mark.parametrize('damage', ['trace_missing', 'sidecar_missing', 'bad_jsonl', 'id_removed',
                                    'id_superseded', 'id_duplicated', 'frozen_row_duplicated',
                                    'blind_key_duplicated', 'wrong_frozen_config'])
def test_bad_frozen_input_keeps_previous_export(tmp_path, damage):
    outputs = write_demo(tmp_path)
    result = run_dataset(tmp_path)
    assert result.returncode == 0, result.stderr
    target = outputs / 'dataset'
    # The fallback also runs against the old two-file exporter to reproduce the bug.
    before = current_files(target)
    source = outputs / 'traces/a.jsonl'
    manifest = outputs / 'claw_eval/p2/flash-think-off/manifest.jsonl'
    rows = list(map(json.loads, manifest.read_text().splitlines()))
    if damage == 'trace_missing':
        source.unlink()
    elif damage == 'sidecar_missing':
        source.with_suffix('.sidecar.jsonl').unlink()
    elif damage == 'bad_jsonl':
        source.write_bytes(b'{bad-json}\n')
    elif damage == 'id_removed':
        write_rows(manifest, rows[1:])
    elif damage == 'id_superseded':
        write_rows(manifest, [*rows, dict(rows[0], status='stopped')])
    elif damage == 'id_duplicated':
        duplicate = outputs / 'claw_eval/p2/flash-think-on/manifest.jsonl'
        write_rows(duplicate, [*map(json.loads, duplicate.read_text().splitlines()),
                              dict(rows[0], config='flash-think-on')])
    elif damage == 'frozen_row_duplicated':
        selection = outputs / 'p2/annotation_set.json'
        frozen = json.loads(selection.read_text())
        selection.write_text(json.dumps(frozen + frozen[:1]))
    elif damage == 'blind_key_duplicated':
        (outputs / 'annotation/key.json').write_text('{"a":"B01","a":"B02","b":"B01"}\n')
    else:
        metadata = outputs / 'p2/annotation_meta.json'
        doc = json.loads(metadata.read_text())
        doc['chosen'][0]['config'] = 'flash-think-on'
        metadata.write_text(json.dumps(doc))

    result = run_dataset(tmp_path)
    after = current_files(target)
    assert result.returncode == 1 and after == before, (
        f'exit={result.returncode}, changed={before != after}: {result.stdout} {result.stderr}'
    )
    assert 'frozen' in result.stderr.lower()


def current_files(target):
    pointer = target / 'CURRENT'
    if pointer.exists():
        current = target / 'snapshots' / pointer.read_text().strip()
        return {p.name: p.read_bytes() for p in current.iterdir()} | {'CURRENT': pointer.read_bytes()}
    return {name: (target / name).read_bytes() for name in ('quality.json', 'trajectories.jsonl')}


def test_snapshot_fingerprints_and_report_pairing(tmp_path):
    outputs = write_demo(tmp_path)
    target = outputs / 'dataset'
    assert run_dataset(tmp_path).returncode == 0
    assert run_dataset(tmp_path, '--check').returncode == 0
    before = current_files(target)
    assert run_dataset(tmp_path).returncode == 0
    assert current_files(target) == before
    quality = json.loads(before['quality.json'])
    assert quality['human_verdicts'] == {'pass': 0, 'fail': 1, 'missing': 2}
    assert quality['by_config']['flash-think-off']['human_verdicts'] == {'pass': 0, 'fail': 1, 'missing': 1}
    assert sum(split['human_verdicts']['fail'] for split in quality['by_split'].values()) == 1
    assert quality['excluded_without_split'] == {'missing_trace_end': 1}
    assert quality['input_files']['annotation/labels.csv'] == hashlib.sha256(
        (tmp_path / 'annotation/labels.csv').read_bytes()).hexdigest()

    # A changed input creates a distinct generation. Mixing it with the old
    # report is detectable, even if the filename is correct.
    labels = tmp_path / 'annotation/labels.csv'
    labels.write_text(labels.read_text().replace('fail,demo issue', 'pass,demo issue'))
    assert run_dataset(tmp_path).returncode == 0
    after = current_files(target)
    assert after['CURRENT'] != before['CURRENT']
    current = target / 'snapshots' / after['CURRENT'].decode().strip()
    (current / 'quality.json').write_bytes(before['quality.json'])
    result = run_dataset(tmp_path, '--check')
    assert result.returncode == 1
    assert 'quality.json' in result.stderr


def test_interrupted_publication_keeps_previous_snapshot(tmp_path, monkeypatch):
    outputs = write_demo(tmp_path)
    target = outputs / 'dataset'
    assert run_dataset(tmp_path).returncode == 0
    before = current_files(target)
    labels = tmp_path / 'annotation/labels.csv'
    labels.write_text(labels.read_text().replace('fail,demo issue', 'pass,demo issue'))
    ns = runpy.run_path(str(SCRIPT))
    original = ns['atomic_text']

    def interrupt(path, text):
        if path == target / 'CURRENT':
            raise OSError('simulated interruption before pointer switch')
        original(path, text)

    monkeypatch.setitem(ns['main'].__globals__, 'atomic_text', interrupt)
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--root', str(tmp_path)])
    with pytest.raises(SystemExit) as err:
        ns['main']()
    assert err.value.code == 1
    assert current_files(target) == before
    assert run_dataset(tmp_path, '--check').returncode == 0


def test_anomalous_openjudge_scores_stay_visible_but_do_not_count_as_comparisons(tmp_path):
    outputs = write_demo(tmp_path)
    write_rows(outputs / 'p2/p2-deepseek-flash.jsonl', [
        {'trace_id': 'a', 'job_id': 'out-of-range', 'grader': 'trajectory_accuracy',
         'score': 999, 'status': 'ok'},
        {'trace_id': 'a', 'job_id': 'error', 'grader': 'trajectory_accuracy',
         'score': None, 'status': 'error'},
    ])
    result = run_dataset(tmp_path)
    assert result.returncode == 0, result.stderr
    files = current_files(outputs / 'dataset')
    report = json.loads(files['quality.json'])
    assert report['openjudge_rows'] == 2
    assert report['invalid_openjudge_rows'] == 2
    assert report['by_config']['flash-think-off']['invalid_openjudge_rows'] == 2
    assert report['without_openjudge_rows'] == 2
    assert report['human_openjudge_comparisons'] == {}
    rows = [json.loads(line) for line in files['trajectories.jsonl'].splitlines()]
    record = next(row for row in rows if row['trace_id'] == 'a')
    assert [(x['status'], x['score']) for x in record['judgments']['openjudge']] == [('error', None), ('ok', 999)]
