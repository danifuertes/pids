#!/usr/bin/env python
"""
Create a dataset split into train, val and test sets from the sequences of a RoboMaster dataset.

    <output>/
        train/PIDS<year>_GR<group>_<index>/     whole sequence folders copied from the dataset
        val/...
        test/...
        sets.json                               sequences of each set and the options used

Every sequence is copied entirely into a single set, never divided between sets: the frames of a recording
are almost identical, so splitting a sequence would put near-copies of the training images in val/test.
The dataset is not modified. Sequences whose name is not
PIDS<year>_GR<group>_<index>, and sequences without labels or images, are left out (see check_data.py).

Choose how the sequences are organised with --strategy (listed below), --ratios and --balance. Specific
sequences or groups can be sent to a set with --train/--val/--test (the strategy splits the rest, taking
them into account for the ratios) or left out with --exclude. The split is listed and must be confirmed
before anything is created (--dry-run only lists it).

Usage:
    python split_data.py path/to/dataset path/to/sets                 # show a random 70/15/15 split, ask, copy
    python split_data.py path/to/dataset path/to/sets --dry-run       # only show the split
    python split_data.py path/to/dataset path/to/sets --ratios 80 10 10 --seed 3
    python split_data.py path/to/dataset path/to/sets -s per-group --test 'PIDS2025_*' --exclude PIDS2024_GR01
    python split_data.py path/to/dataset path/to/sets -s manual --train 'PIDS2023_*,PIDS2024_*' --val PIDS2025_GR01 --test PIDS2025_GR02
"""
import os
import sys
import json
import shlex
import random
import shutil
import argparse
import textwrap
from collections import defaultdict
from datetime import datetime
from fnmatch import fnmatchcase
from typing import Callable, Dict, List, NamedTuple, Tuple

from tqdm import tqdm

from check_data import ERROR, INFO, IMAGE_EXTENSIONS, SEQUENCE_PATTERN, WARNING, Painter

SETS = ('train', 'val', 'test')
SET_STYLES = {'train': 'green', 'val': WARNING, 'test': INFO}

STRATEGIES = {
    'random':    'shuffle all the sequences together, regardless of their group and year, and split them by '
                 '--ratios (default)',
    'per-group': 'split the sequences of each group by --ratios, so every group is in every set '
                 '(if it has enough sequences)',
    'by-group':  'put each whole group in a single set, split by --ratios (val/test then measure how the '
                 'model works on recordings it has never seen, but the shares are less exact)',
    'manual':    'only use the sequences chosen with --train/--val/--test; the rest are left out',
}

# Reasons to leave a sequence out, in the order they are listed
BAD_NAME, NO_LABELS, NO_IMAGES = 'name not PIDS<year>_GR<group>_<index>', 'no labels', 'labels but no images'
EXCLUDED, NOT_CHOSEN = '--exclude', 'not in --train/--val/--test'
REASONS = (BAD_NAME, NO_LABELS, NO_IMAGES, EXCLUDED, NOT_CHOSEN)

MAX_SHARE_DEVIATION = 0.05       # warn when a set is further than this from its ratio


class Sequence(NamedTuple):
    name: str
    group: str       # PIDS<year>_GR<group>
    images: int
    labels: int
    size: int        # bytes of the whole folder


# ======================================================================== scan

def scan_sequence(path: str) -> Tuple[int, int, int]:
    """(images, labels, bytes) of a sequence folder; labels are the .xml files the week2 loader reads."""
    images = labels = size = 0
    for folder, _, files in os.walk(path):
        rel = os.path.relpath(folder, path)
        for name in files:
            size += os.lstat(os.path.join(folder, name)).st_size
            extension = os.path.splitext(name)[1].lower()
            if rel == 'images' and extension in IMAGE_EXTENSIONS:
                images += 1
            elif rel == 'labels' and extension == '.xml':
                labels += 1
    return images, labels, size


def scan_dataset(root: str) -> Tuple[List[Sequence], Dict[str, List[str]]]:
    """Usable sequences, and the names of the ones left out by reason."""
    sequences, left_out = [], defaultdict(list)
    names = sorted(n for n in os.listdir(root) if not n.startswith('.') and os.path.isdir(os.path.join(root, n)))
    for name in tqdm(names, desc='Scanning', file=sys.stderr, leave=False):
        match = SEQUENCE_PATTERN.match(name)
        if match is None:
            left_out[BAD_NAME].append(name)
            continue
        images, labels, size = scan_sequence(os.path.join(root, name))
        if not labels:
            left_out[NO_LABELS].append(name)
        elif not images:
            left_out[NO_IMAGES].append(name)
        else:
            sequences.append(Sequence(name, f'PIDS{match.group(1)}_GR{match.group(2)}', images, labels, size))
    return sequences, left_out


def select(sequences: List[Sequence], patterns: List[str], option: str, problems: List[str]) -> List[Sequence]:
    """Sequences whose name or group matches any of the patterns."""
    selected = {}
    for pattern in patterns:
        matched = [s for s in sequences if fnmatchcase(s.name, pattern) or fnmatchcase(s.group, pattern)]
        if not matched:
            problems.append(f'{option} {pattern} matches no usable sequence')
        selected.update((s.name, s) for s in matched)
    return list(selected.values())


# ======================================================================== split

def split_sequences(sequences: List[Sequence], strategy: str, ratios: List[float], weight: Callable[[Sequence], int],
                    pinned: Dict[str, str], seed: int) -> Dict[str, str]:
    """Sequence name -> set: the pinned sequences, then the rest as the strategy says."""
    assignment = dict(pinned)
    if strategy == 'manual':
        return assignment

    rng = random.Random(seed)
    groups = sorted({s.group for s in sequences})
    # per-group splits each group on its own; the other strategies split the whole dataset at once
    batches = [[s for s in sequences if s.group == g] for g in groups] if strategy == 'per-group' else [sequences]
    for batch in batches:
        totals = [sum(weight(s) for s in batch if assignment.get(s.name) == set_name) for set_name in SETS]
        free = [s for s in batch if s.name not in assignment]
        if strategy == 'by-group':
            units = [[s for s in free if s.group == g] for g in groups if any(s.group == g for s in free)]
        else:
            units = [[s] for s in free]

        rng.shuffle(units)
        for unit in units:
            unit_weight = sum(weight(s) for s in unit)
            grand_total = sum(totals) + unit_weight
            # the set that would be furthest below its share once the unit is added (the first one on ties)
            index = max(range(len(SETS)), key=lambda i: (ratios[i] * grand_total - totals[i], -i))
            totals[index] += unit_weight
            assignment.update((s.name, SETS[index]) for s in unit)
    return assignment


# ======================================================================== output

def format_size(size: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            break
        size /= 1024
    else:
        unit = 'TB'
    return f'{size:.0f} {unit}' if unit in ('B', 'KB') else f'{size:.1f} {unit}'


def format_indices(indices: List[str]) -> str:
    """['0000', '0001', '0002', '0005'] -> '0000-0002 0005' (runs of three or more become ranges)."""
    runs: List[List[str]] = []
    for index in sorted(indices):
        if runs and int(index) == int(runs[-1][-1]) + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return ' '.join(f'{run[0]}-{run[-1]}' if len(run) > 2 else ' '.join(run) for run in runs)


def format_names(names: List[str]) -> str:
    """'PIDS2025_GR05 0000-0003; bad_name' (indices grouped by their group)."""
    groups, others = defaultdict(list), []
    for name in sorted(names):
        if SEQUENCE_PATTERN.match(name):
            groups[name[:-5]].append(name[-4:])
        else:
            others.append(name)
    return '; '.join([f'{group} {format_indices(indices)}' for group, indices in groups.items()] + others)


def print_left_out(left_out: Dict[str, List[str]], paint: Painter) -> None:
    if not any(left_out.values()):
        return
    print('\n' + paint('Left out', 'bold'))
    width = max(len(reason) for reason in left_out if left_out[reason])
    for reason in REASONS:
        if left_out.get(reason):
            print(f'  {reason:<{width}} {len(left_out[reason]):>4}  {format_names(left_out[reason])}')


def print_split(sequences: List[Sequence], assignment: Dict[str, str], pinned: Dict[str, str], args: argparse.Namespace,
                ratios: List[float], weight: Callable[[Sequence], int], problems: List[str], paint: Painter) -> None:
    manual = args.strategy == 'manual'
    title = f"{args.strategy}" if manual else \
        f"{args.strategy}, {' / '.join(f'{r:.0%}' for r in ratios)} of the {args.balance}, seed {args.seed}"
    print('\n' + paint('Split', 'bold') + '  ' + title)

    # Sequence indices of each group in each set
    cells = defaultdict(lambda: {set_name: [] for set_name in SETS})
    for s in sequences:
        if s.name in assignment:
            cells[s.group][assignment[s.name]].append(s.name[-4:])
    texts = {group: [format_indices(cells[group][set_name]) or '-' for set_name in SETS] for group in sorted(cells)}
    widths = [max([len(set_name)] + [len(t[i]) for t in texts.values()]) for i, set_name in enumerate(SETS)]
    widths[-1] = 0                                           # no padding after the last column
    group_width = max([len('Group')] + [len(group) for group in texts])
    print('  ' + paint(f"{'Group':<{group_width}}", 'dim') + ''.join(
        '  ' + paint(f'{set_name:<{w}}', SET_STYLES[set_name]) for set_name, w in zip(SETS, widths)))
    for group, row in texts.items():
        print(f'  {group:<{group_width}}' + ''.join(f'  {text:<{w}}' for text, w in zip(row, widths)).rstrip())

    # Totals of each set
    used = [s for s in sequences if s.name in assignment]
    grand_total = sum(weight(s) for s in used) or 1
    print('\n' + paint(f"  {'Set':<5} {'Seqs':>5} {'Groups':>6} {'Images':>7} {'Labels':>7} {'Share':>6} "
                       f"{'Target':>6} {'Size':>9}", 'dim'))
    rows = [(set_name, [s for s in used if assignment[s.name] == set_name]) for set_name in SETS] + [('total', used)]
    for i, (set_name, members) in enumerate(rows):
        share = sum(weight(s) for s in members) / grand_total
        target = '-' if manual or set_name == 'total' else f'{ratios[i]:.0%}'
        name = paint(f'{set_name:<5}', SET_STYLES.get(set_name, 'bold'))
        print(f"  {name} {len(members):>5} {len({s.group for s in members}):>6} {sum(s.images for s in members):>7} "
              f"{sum(s.labels for s in members):>7} {share:>6.1%} {target:>6} {format_size(sum(s.size for s in members)):>9}")

        if set_name == 'total':
            continue
        if not members and (manual or ratios[i] > 0):
            problems.append(f'{set_name} is empty')
        elif not manual and members and abs(share - ratios[i]) > MAX_SHARE_DEVIATION:
            hint = 'the sequences chosen with --train/--val/--test count too' if pinned else \
                'try another --seed' + (' or strategy' if args.strategy == 'by-group' else '')
            problems.append(f'{set_name} has {share:.1%} of the {args.balance} instead of {ratios[i]:.0%} ({hint})')

    if problems:
        print()
    for problem in problems:
        print(paint(f'  {problem}', WARNING))


def strategies_help() -> str:
    return '\n'.join(['strategies (--strategy):'] + [
        textwrap.fill(text, width=100, initial_indent=f'  {name:<11}', subsequent_indent=' ' * 13)
        for name, text in STRATEGIES.items()] + [
        '', 'PATTERN is a sequence or group name, and may use the wildcards * ? [...] (quote them in the shell).',
        "Separate several patterns with commas, e.g. --test 'PIDS2025_GR01,PIDS2024_GR02_000[0-4]'."])


# ======================================================================== create

def existing_parent(path: str) -> str:
    while not os.path.exists(path):
        path = os.path.dirname(path)
    return path


def create_sets(dataset: str, output: str, sequences: List[Sequence], assignment: Dict[str, str], manifest: dict,
                paint: Painter) -> int:
    """Copy every sequence folder, whole, into its set; return the number of failures."""
    for set_name in SETS:
        os.makedirs(os.path.join(output, set_name), exist_ok=True)

    failed = 0
    used = [s for s in sequences if s.name in assignment]
    for s in tqdm(used, desc='Copying', file=sys.stderr, leave=False):
        src, dst = os.path.join(dataset, s.name), os.path.join(output, assignment[s.name], s.name)
        try:
            shutil.copytree(src, dst)
            if scan_sequence(dst) != (s.images, s.labels, s.size):
                raise RuntimeError('the copy does not have the same files as the original')
        except Exception as e:
            failed += 1
            tqdm.write(paint(f'  FAILED {s.name}: {e}', ERROR))

    with open(os.path.join(output, 'sets.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')
    return failed


# ======================================================================== main

def parse_patterns(values: List[str]) -> List[str]:
    return [pattern.strip() for value in values for pattern in value.split(',') if pattern.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=strategies_help(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('dataset', help='Dataset with the sequences')
    parser.add_argument('output', help='Folder to create with the train, val and test sets (must not exist, or be empty)')
    parser.add_argument('-s', '--strategy', choices=STRATEGIES, default='random',
                        help='How the sequences are split (default: random; see below)')
    parser.add_argument('--ratios', nargs=3, type=float, default=[70, 15, 15], metavar=('TRAIN', 'VAL', 'TEST'),
                        help='Share of each set, e.g. 70 15 15 or 0.8 0.1 0.1 (default: 70 15 15)')
    parser.add_argument('--balance', choices=('labels', 'sequences'), default='labels',
                        help='What --ratios count: labelled images (default) or sequences')
    parser.add_argument('--seed', type=int, default=0, help='Random seed; change it for a different split (default: 0)')
    for set_name in SETS:
        parser.add_argument(f'--{set_name}', action='append', default=[], metavar='PATTERN',
                            help=f'Put these sequences or groups in {set_name} (repeatable)')
    parser.add_argument('--exclude', action='append', default=[], metavar='PATTERN',
                        help='Leave these sequences or groups out (repeatable)')
    parser.add_argument('--dry-run', action='store_true', help='List the split without creating anything')
    parser.add_argument('-y', '--yes', action='store_true', help='Create the sets without asking for confirmation')
    args = parser.parse_args()

    # Options
    dataset, output = args.dataset, os.path.abspath(args.output)
    if not os.path.isdir(dataset):
        parser.error(f"'{dataset}' is not a folder")
    if os.path.exists(output) and (not os.path.isdir(output) or os.listdir(output)):
        parser.error(f"'{args.output}' already exists and is not an empty folder")
    real_dataset, real_output = os.path.realpath(dataset), os.path.realpath(output)
    if real_output == real_dataset or real_output.startswith(real_dataset + os.sep):
        parser.error('the output cannot be inside the dataset')
    if any(r < 0 for r in args.ratios) or sum(args.ratios) <= 0:
        parser.error('--ratios must be non-negative and not all zero')
    ratios = [r / sum(args.ratios) for r in args.ratios]
    patterns = {option: parse_patterns(getattr(args, option)) for option in (*SETS, 'exclude')}
    if args.strategy == 'manual' and not any(patterns[set_name] for set_name in SETS):
        parser.error('--strategy manual needs --train, --val and/or --test')
    if not (args.dry_run or args.yes) and not sys.stdin.isatty():
        parser.error('confirming needs a terminal: use --dry-run or --yes')

    paint = Painter(sys.stdout.isatty() and 'NO_COLOR' not in os.environ)
    weight = (lambda s: s.labels) if args.balance == 'labels' else (lambda s: 1)

    # Scan and split
    problems: List[str] = []
    sequences, left_out = scan_dataset(dataset)
    excluded = {s.name for s in select(sequences, patterns['exclude'], '--exclude', problems)}
    left_out[EXCLUDED] = sorted(excluded)
    sequences = [s for s in sequences if s.name not in excluded]

    pinned: Dict[str, str] = {}
    for set_name in SETS:
        for s in select(sequences, patterns[set_name], f'--{set_name}', problems):
            if pinned.setdefault(s.name, set_name) != set_name:
                parser.error(f'{s.name} is chosen for both {pinned[s.name]} and {set_name}')
    assignment = split_sequences(sequences, args.strategy, ratios, weight, pinned, args.seed)
    left_out[NOT_CHOSEN] = [s.name for s in sequences if s.name not in assignment]

    print(f"{paint('Dataset', 'bold')}  {real_dataset}: {len(sequences)} usable sequences in "
          f"{len({s.group for s in sequences})} groups")
    print_left_out(left_out, paint)
    print_split(sequences, assignment, pinned, args, ratios, weight, problems, paint)
    if not assignment:
        print('Nothing to create.')
        return 1

    size = sum(s.size for s in sequences if s.name in assignment)
    free = shutil.disk_usage(existing_parent(output)).free
    if size > free:
        print(paint(f'Not enough space to copy {format_size(size)} ({format_size(free)} free): choose another '
                    f'output folder.', ERROR))
        return 1
    if args.dry_run:
        print('\nDry run, nothing was created.')
        return 0

    try:
        if not (args.yes or input(f'\nCopy {format_size(size)} into {real_output}? [y/N] ').strip().lower() in ('y', 'yes')):
            print('Nothing was created.')
            return 0
    except (EOFError, KeyboardInterrupt):
        print('\nAborted, nothing was created.')
        return 130

    try:
        manifest = {
            'created': datetime.now().isoformat(timespec='seconds'),
            'command': shlex.join(sys.argv),
            'dataset': real_dataset,
            'strategy': args.strategy,
            'ratios': dict(zip(SETS, (round(r, 4) for r in ratios))),
            'balance': args.balance,
            'seed': args.seed,
            'sets': {set_name: sorted(n for n, s in assignment.items() if s == set_name) for set_name in SETS},
            'left_out': {reason: left_out[reason] for reason in REASONS if left_out.get(reason)},
        }
        failed = create_sets(dataset, output, sequences, assignment, manifest, paint)
    except KeyboardInterrupt:
        print(f'\nInterrupted: {real_output} is incomplete, delete it before trying again.')
        return 130

    counts = ', '.join(f"{set_name} {sum(s == set_name for s in assignment.values())}" for set_name in SETS)
    print(f'\nDone: {len(assignment) - failed} sequences in {real_output} ({counts})'
          + (paint(f', {failed} failed', ERROR) if failed else '') + '.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
