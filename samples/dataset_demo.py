"""Create and build an entirely synthetic TrajJudge P2 dataset example."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def write_demo(root, same_task='same'):
    outputs = root / 'outputs'
    for config, runs in {'flash-think-off': [(same_task, 'a'), ('other', 'c')],
                         'flash-think-on': [(same_task, 'b'), ('broken', 'd')]}.items():
        manifest = []
        for task, trace in runs:
            source = outputs / 'traces' / f'{trace}.jsonl'
            sidecar = source.with_suffix('.sidecar.jsonl')
            write_rows(source, [
                {'type': 'trace_start', 'task_id': task, 'trace_id': trace, 'model': 'demo'},
                {'type': 'message', 'trace_id': trace, 'message': {'role': 'user', 'content': 'Summarize demo events.'}},
                {'type': 'grading_result', 'task_id': task, 'trace_id': trace, 'passed': True, 'task_score': 1},
                *([] if trace == 'd' else [{'type': 'trace_end', 'trace_id': trace}]),
            ])
            write_rows(sidecar, [])
            manifest.append({'task_id': task, 'status': 'complete', 'config': config,
                             'trace': str(source.relative_to(root)), 'sidecar': str(sidecar.relative_to(root)),
                             'config_sha256': 'demo'})
        write_rows(outputs / 'claw_eval/p2' / config / 'manifest.jsonl', manifest)

    selected = [{'trace_id': 'a', 'task_id': same_task, 'config': 'flash-think-off'},
                {'trace_id': 'b', 'task_id': same_task, 'config': 'flash-think-on'}]
    p2 = outputs / 'p2'
    write_rows(p2 / 'annotation_meta.json', [{'chosen': selected, 'all_candidates': selected}])
    frozen = []
    for trace in ('a', 'b'):
        source = outputs / 'traces' / f'{trace}.jsonl'
        frozen.append({'trace_id': trace, 'trace_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                       'sidecar_sha256': hashlib.sha256(source.with_suffix('.sidecar.jsonl').read_bytes()).hexdigest()})
    (p2 / 'annotation_set.json').write_text(json.dumps(frozen))
    write_rows(outputs / 'annotation/key.json', [{'a': 'B01', 'b': 'B02'}])
    labels = root / 'annotation/labels.csv'
    labels.parent.mkdir()
    labels.write_text('blind_id,label,reason,annotated_at,round\nB01,fail,demo issue,,1\nB02,,,,1\n')
    write_rows(p2 / 'p2-deepseek-flash.jsonl', [
        {'trace_id': 'a', 'job_id': 'job-a', 'grader': 'trajectory_accuracy', 'score': 1, 'status': 'ok'},
    ])

    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="new directory for the synthetic evidence and snapshot")
    root = parser.parse_args().root.resolve()
    try:
        root.mkdir()
    except OSError as exc:
        parser.exit(1, f"cannot create demo root: {exc}\n")
    write_demo(root)
    script = Path(__file__).resolve().parents[1] / "scripts/build_dataset.py"
    return subprocess.run([sys.executable, str(script), "--root", str(root)]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
