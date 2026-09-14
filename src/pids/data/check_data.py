#!/usr/bin/env python
"""
Check (and optionally repair) the structure and annotations of a RoboMaster detection dataset.

Expected layout (one folder per recorded sequence):

    <dataset>/
        PIDS<year>_GR<group>_<index>/
            images/frame_XXXX.jpg
            labels/frame_XXXX.xml     Pascal VOC; <filename> is the image inside images/

Every issue has a severity:
    ERROR    breaks training with the week2 data loader, or the data is unusable/missing
    WARNING  should be fixed or removed, although the loader tolerates it
    INFO     worth knowing (unlabelled images, background frames...); listed with --level info

Only sequences with issues are printed. Every issue is skipped by default: choose what to do with
each type of issue with --action CODE=ACTION, or answer the questions of --interactive. The changes
are listed and must be confirmed before any file is touched (--dry-run only lists them).

Usage:
    python check_data.py /path/to/dataset
    python check_data.py /path/to/dataset --verify --duplicates --level info
    python check_data.py /path/to/dataset -a hidden-entry,extra-entry=remove -a unexpected-class=fix --dry-run
    python check_data.py /path/to/dataset -i                    # ask what to do with each issue

The exit code is 1 if any ERROR is found, 0 otherwise.
"""
import os
import re
import sys
import shutil
import hashlib
import argparse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from functools import partial
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from PIL import Image
from tqdm import tqdm

SEQUENCE_PATTERN = re.compile(r'^PIDS(\d{4})_GR(\d{2})_(\d{4})$')
FRAME_PATTERN = re.compile(r'^frame_\d+$')
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png')
EXPECTED_IMAGE_EXTENSION = '.jpg'
EXPECTED_RESOLUTION = (1280, 720)
BOX_KEYS = ('xmin', 'ymin', 'xmax', 'ymax')

ERROR, WARNING, INFO = 'ERROR', 'WARNING', 'INFO'
SEVERITIES = (ERROR, WARNING, INFO)

# Actions: name -> (Plan method that schedules the change, help). 'skip' is always valid and the default.
REMOVE = {'remove': ('remove_entry', 'delete it')}
REMOVE_SEQUENCE = {'remove': ('remove_sequence', 'delete the whole sequence folder')}
REMOVE_IMAGE = {'remove': ('remove_image', 'delete the image and the labels pointing to it')}
REMOVE_LABEL = {'remove': ('remove_entry', 'delete the label file')}
REMOVE_WITH_IMAGE = {'remove-with-image': ('remove_label_and_image', 'delete the label file and the image with the same name')}
REMOVE_OBJECT = {'remove': ('remove_object', 'delete the object from the label')}
FIX_FILENAME = {'fix': ('fix_filename', 'point <filename> to the image named like the label')}

# Issue code -> (severity, description, actions)
ISSUES = {
    # Dataset root
    'stray-file':            (WARNING, 'File at the dataset root', REMOVE),
    'bad-sequence-name':     (WARNING, 'Folder name is not PIDS<year>_GR<group>_<index>', REMOVE),
    'sequence-gap':          (WARNING, 'Index missing in the numbering of a group',
                              {'fix': ('fix_gap', "rename the group's sequences so their indices are consecutive")}),
    'hidden-entry':          (WARNING, 'Hidden file or folder (e.g. .ipynb_checkpoints)', REMOVE),
    # Sequence folder
    'empty-sequence':        (ERROR,   'Empty sequence folder', REMOVE_SEQUENCE),
    'missing-images-dir':    (ERROR,   "No 'images' folder", REMOVE_SEQUENCE),
    'missing-labels-dir':    (ERROR,   "No 'labels' folder", REMOVE_SEQUENCE),
    'no-images':             (ERROR,   "Empty 'images' folder", REMOVE_SEQUENCE),
    'no-labels':             (ERROR,   "Empty 'labels' folder (its images are never used)", REMOVE_SEQUENCE),
    'extra-entry':           (WARNING, "Unexpected entry (a sequence only has 'images' and 'labels')", REMOVE),
    # images/
    'image-subfolder':       (WARNING, "Folder inside 'images'", REMOVE),
    'image-checkpoint-copy': (WARNING, "Jupyter checkpoint copy inside 'images'", REMOVE),
    'not-an-image':          (WARNING, "File inside 'images' that is not an image", REMOVE),
    'corrupt-image':         (ERROR,   'Image cannot be opened/decoded', REMOVE_IMAGE),
    'image-extension':       (INFO,    f"Image extension is not '{EXPECTED_IMAGE_EXTENSION}'",
                              {'fix': ('fix_extension', 'rename it to .jpg (converting non-JPEG files) and update its labels')}),
    'frame-name':            (INFO,    'Image name is not frame_<number>', REMOVE_IMAGE),
    'unusual-resolution':    (INFO,    'Image resolution differs from --resolution', {
        'remove': ('remove_entry', 'delete the image (its labels are kept)'),
        'remove-with-labels': ('remove_image_or_sequence',
                               'delete the image and its labels (the whole sequence if all its images are affected)'),
        'rescale': ('rescale_image', 'resize the image to --resolution (stretching it if the aspect ratio differs) '
                                     'and scale its labels'),
    }),
    'unlabelled-image':      (INFO,    'Image without a label (never used for training)', REMOVE_IMAGE),
    'duplicate-image':       (WARNING, 'Identical copy of another image', REMOVE_IMAGE),
    # labels/ (the loader reads EVERY file in this folder, so any junk file crashes it)
    'label-subfolder':       (WARNING, "Folder inside 'labels'", REMOVE),
    'label-checkpoint-copy': (ERROR,   "Jupyter checkpoint copy inside 'labels'", REMOVE),
    'not-a-label':           (ERROR,   "File inside 'labels' that is not an .xml label", REMOVE),
    'invalid-xml':           (ERROR,   'Label is not valid XML (corrupt file)', {**REMOVE_LABEL, **REMOVE_WITH_IMAGE}),
    'missing-filename':      (ERROR,   'Label without <filename>', {**FIX_FILENAME, **REMOVE_LABEL}),
    'missing-image':         (ERROR,   "Label points to an image that is not in 'images'", {**FIX_FILENAME, **REMOVE_LABEL}),
    'filename-mismatch':     (WARNING, 'Label name and its <filename> differ', {**FIX_FILENAME, **REMOVE_LABEL}),
    'duplicate-reference':   (WARNING, 'Several labels point to the same image', {}),
    'size-mismatch':         (WARNING, '<size> in the label differs from the real image size',
                              {'fix': ('fix_size', 'write the real image size in <size>')}),
    'bad-box':               (ERROR,   'Box missing or with non-integer coordinates',
                              {'fix': ('fix_box', 'round the coordinates (delete the object if not possible)'), **REMOVE_OBJECT}),
    'degenerate-box':        (ERROR,   'Box with zero or negative width/height',
                              {'fix': ('fix_box', 'swap inverted coordinates (delete the object if it has no area)'), **REMOVE_OBJECT}),
    'box-out-of-bounds':     (WARNING, 'Box goes outside the image',
                              {'fix': ('fix_box', 'clip the box to the image'), **REMOVE_OBJECT}),
    'unexpected-class':      (WARNING, 'Class not in --classes (the loader counts it as a robot)',
                              {'fix': ('fix_class', 'rename it to the first --classes value'), **REMOVE_OBJECT}),
    'no-objects':            (INFO,    'Label without objects (background frame)',
                              {'remove': ('remove_entry', 'delete the label file (the image stays, unlabelled)')}),
}

# Issues better summarised by their detail (e.g. 'robot_p (120)') than by listing files
SUMMARISE_BY_DETAIL = {'unexpected-class', 'unusual-resolution'}


def issue_order(code: str) -> Tuple[int, int]:
    """Sort by severity, then in the order of ISSUES (grouped by location)."""
    return SEVERITIES.index(ISSUES[code][0]), list(ISSUES).index(code)


class Issue(NamedTuple):
    code: str
    sequence: str       # '' for dataset-level issues
    path: str           # relative to the sequence folder (or to the dataset root); '' for the sequence itself
    detail: str = ''
    data: Any = None    # whatever the fix needs (object index, real image size...)


# ======================================================================== check

class DatasetChecker:
    """Walks the dataset once, collecting issues and statistics."""

    def __init__(self, root: str, classes: List[str], resolution: Tuple[int, int] = EXPECTED_RESOLUTION,
                 verify: bool = False, duplicates: bool = False) -> None:
        self.root = root
        self.classes = classes
        self.resolution = resolution
        self.verify = verify
        self.duplicates = duplicates
        self.sequences: List[str] = []
        self.issues: List[Issue] = []
        self.counts: Dict[str, Counter] = defaultdict(Counter)                    # sequence -> images/labels/objects
        self.references: Dict[Tuple[str, str], List[str]] = {}                   # (sequence, image) -> its labels
        self.image_hashes: Dict[str, List[Tuple[str, str]]] = defaultdict(list)  # md5 -> [(sequence, image)]

    def add(self, code: str, sequence: str, path: str, detail: str = '', data: Any = None) -> None:
        self.issues.append(Issue(code, sequence, path, detail, data))

    def list_dir(self, path: str, sequence: str, rel: str) -> List[str]:
        """Sorted entries of a folder; hidden ones are reported and left out."""
        entries = []
        for name in sorted(os.listdir(path)):
            if name.startswith('.'):
                self.add('hidden-entry', sequence, os.path.join(rel, name))
            else:
                entries.append(name)
        return entries

    # ------------------------------------------------------------------ dataset

    def run(self) -> None:
        for name in self.list_dir(self.root, '', ''):
            if os.path.isdir(os.path.join(self.root, name)):
                self.sequences.append(name)
            else:
                self.add('stray-file', '', name)

        self.check_numbering()
        for sequence in tqdm(self.sequences, desc='Checking', file=sys.stderr, leave=False):
            self.check_sequence(sequence)
        self.find_duplicates()

    def check_numbering(self) -> None:
        """Sequence names must follow the pattern and be numbered 0000, 0001... within each group."""
        indices = defaultdict(set)
        for name in self.sequences:
            match = SEQUENCE_PATTERN.match(name)
            if match is None:
                self.add('bad-sequence-name', '', name)
            else:
                indices[match.group(1), match.group(2)].add(int(match.group(3)))

        for (year, group), found in sorted(indices.items()):
            for index in sorted(set(range(max(found) + 1)) - found):
                self.add('sequence-gap', '', f'PIDS{year}_GR{group}_{index:04d}', 'does not exist', (year, group))

    def find_duplicates(self) -> None:
        """Keep one copy of each identical image (preferring labelled, well-named ones) and flag the rest."""
        for copies in self.image_hashes.values():
            if len(copies) < 2:
                continue
            copies.sort(key=lambda c: (c not in self.references, not FRAME_PATTERN.match(os.path.splitext(c[1])[0]),
                                       len(c[1]), c))
            kept = os.path.join(copies[0][0], 'images', copies[0][1])
            for sequence, name in copies[1:]:
                self.add('duplicate-image', sequence, f'images/{name}', f'same as {kept}')

    # ----------------------------------------------------------------- sequence

    def check_sequence(self, sequence: str) -> None:
        path = os.path.join(self.root, sequence)
        entries = self.list_dir(path, sequence, '')
        if not entries:
            self.add('empty-sequence', sequence, '')
            return

        for name in entries:
            if name not in ('images', 'labels') or not os.path.isdir(os.path.join(path, name)):
                self.add('extra-entry', sequence, name)

        images: Dict[str, Optional[Tuple[int, int]]] = {}
        if not os.path.isdir(os.path.join(path, 'images')):
            self.add('missing-images-dir', sequence, '')
        else:
            images = self.check_images(sequence)
            if not images:
                self.add('no-images', sequence, '')

        if not os.path.isdir(os.path.join(path, 'labels')):
            self.add('missing-labels-dir', sequence, '')
        else:
            self.check_labels(sequence, images)
            if not self.counts[sequence]['labels']:
                self.add('no-labels', sequence, '')

    # ------------------------------------------------------------------- images

    def check_images(self, sequence: str) -> Dict[str, Optional[Tuple[int, int]]]:
        """Return {image name: (width, height)}; the size is None if the image is corrupt."""
        images_dir = os.path.join(self.root, sequence, 'images')
        images = {}
        for name in self.list_dir(images_dir, sequence, 'images'):
            rel, path = os.path.join('images', name), os.path.join(images_dir, name)
            stem, ext = os.path.splitext(name)

            if os.path.isdir(path):
                self.add('image-subfolder', sequence, rel)
                continue
            if stem.endswith('-checkpoint'):
                self.add('image-checkpoint-copy', sequence, rel)
                continue
            if ext.lower() not in IMAGE_EXTENSIONS:
                self.add('not-an-image', sequence, rel)
                continue

            self.counts[sequence]['images'] += 1
            if ext != EXPECTED_IMAGE_EXTENSION:
                self.add('image-extension', sequence, rel)
            if not FRAME_PATTERN.match(stem):
                self.add('frame-name', sequence, rel)

            images[name] = self.read_image_size(sequence, rel, path)
            if images[name] is not None and images[name] != self.resolution:
                self.add('unusual-resolution', sequence, rel, '{}x{}'.format(*images[name]), images[name])

            if self.duplicates:
                with open(path, 'rb') as f:
                    self.image_hashes[hashlib.md5(f.read()).hexdigest()].append((sequence, name))
        return images

    def read_image_size(self, sequence: str, rel: str, path: str) -> Optional[Tuple[int, int]]:
        """Read the header (or decode the whole image with --verify) and return (width, height)."""
        try:
            with Image.open(path) as image:
                if self.verify:
                    image.load()
                return image.size
        except Exception as e:
            self.add('corrupt-image', sequence, rel, type(e).__name__)
            return None

    # ------------------------------------------------------------------- labels

    def check_labels(self, sequence: str, images: Dict[str, Optional[Tuple[int, int]]]) -> None:
        labels_dir = os.path.join(self.root, sequence, 'labels')
        image_stems = {os.path.splitext(name)[0]: name for name in images}
        referenced = defaultdict(list)                       # image name -> labels pointing to it

        for name in self.list_dir(labels_dir, sequence, 'labels'):
            rel, path = os.path.join('labels', name), os.path.join(labels_dir, name)
            stem, ext = os.path.splitext(name)

            if os.path.isdir(path):
                self.add('label-subfolder', sequence, rel)
                continue
            if stem.endswith('-checkpoint'):
                self.add('label-checkpoint-copy', sequence, rel)
                continue
            if ext.lower() != '.xml':
                self.add('not-a-label', sequence, rel)
                continue

            self.counts[sequence]['labels'] += 1
            try:
                root = ET.parse(path).getroot()
            except Exception as e:
                self.add('invalid-xml', sequence, rel, type(e).__name__)
                continue

            same_name_image = image_stems.get(stem)          # what a <filename> fix would point to
            image_name = root.findtext('filename')
            if not image_name:
                self.add('missing-filename', sequence, rel, data=same_name_image)
                continue
            referenced[image_name].append(name)
            if os.path.splitext(image_name)[0] != stem:
                self.add('filename-mismatch', sequence, rel, f'<filename>{image_name}</filename>', same_name_image)

            image_size, label_size = None, self.read_label_size(root)
            if image_name not in images:
                self.add('missing-image', sequence, rel, f'images/{image_name}', same_name_image)
            else:
                image_size = images[image_name]
                if image_size and label_size and image_size != label_size:
                    self.add('size-mismatch', sequence, rel,
                             'label {}x{}, image {}x{}'.format(*label_size, *image_size), image_size)

            self.check_objects(sequence, rel, root, image_size or label_size)

        for image_name, labels in referenced.items():
            self.references[sequence, image_name] = labels
            if len(labels) > 1:
                self.add('duplicate-reference', sequence, f'images/{image_name}', ', '.join(labels))
        for image_name in images:
            if image_name not in referenced:
                self.add('unlabelled-image', sequence, f'images/{image_name}')

    @staticmethod
    def read_label_size(root: ET.Element) -> Optional[Tuple[int, int]]:
        try:
            return int(root.findtext('size/width')), int(root.findtext('size/height'))
        except (TypeError, ValueError):
            return None

    def check_objects(self, sequence: str, rel: str, root: ET.Element, image_size: Optional[Tuple[int, int]]) -> None:
        """Validate each box exactly as read_label() in the week2 notebooks reads it."""
        objects = list(root.iter('object'))
        if not objects:
            self.add('no-objects', sequence, rel)

        for index, obj in enumerate(objects):
            self.counts[sequence]['objects'] += 1
            class_name = obj.findtext('name')
            if class_name not in self.classes:
                self.add('unexpected-class', sequence, rel, str(class_name), {'object': index})

            box = obj.find('bndbox')
            raw = [box.findtext(k) if box is not None else None for k in BOX_KEYS]
            data = {'object': index, 'box': raw, 'size': image_size}
            try:
                xmin, ymin, xmax, ymax = [int(v) for v in raw]
            except (TypeError, ValueError):
                self.add('bad-box', sequence, rel, str(raw), data)
                continue

            if xmax <= xmin or ymax <= ymin:
                self.add('degenerate-box', sequence, rel, str([xmin, ymin, xmax, ymax]), data)
            elif image_size and (xmin < 0 or ymin < 0 or xmax > image_size[0] or ymax > image_size[1]):
                self.add('box-out-of-bounds', sequence, rel, '{} in {}x{}'.format([xmin, ymin, xmax, ymax], *image_size), data)


# ======================================================================== fix

def sanitize_box(raw: List[Any], size: Optional[Tuple[int, int]]) -> Optional[List[int]]:
    """Integer, well-ordered box clipped to the image; None if impossible or if the box has no area."""
    try:
        xmin, ymin, xmax, ymax = [int(round(float(v))) for v in raw]
    except (TypeError, ValueError, OverflowError):
        return None
    xmin, xmax = sorted((xmin, xmax))
    ymin, ymax = sorted((ymin, ymax))
    if size:
        xmin, xmax = [min(max(v, 0), size[0]) for v in (xmin, xmax)]
        ymin, ymax = [min(max(v, 0), size[1]) for v in (ymin, ymax)]
    if xmax <= xmin or ymax <= ymin:
        return None
    return [xmin, ymin, xmax, ymax]


def find_or_create(parent: ET.Element, tag: str) -> ET.Element:
    element = parent.find(tag)
    return element if element is not None else ET.SubElement(parent, tag)


def clean_operations(operations: List[Tuple[str, Optional[int], Any]]) -> List[Tuple[str, Optional[int], Any]]:
    """Drop repeated edits and edits of objects that are going to be removed anyway."""
    to_remove = {index for op, index, _ in operations if op == 'remove-object'}
    unique = list(dict.fromkeys((op, index, tuple(value) if isinstance(value, list) else value)
                                for op, index, value in operations))
    return [(op, index, value) for op, index, value in unique if op == 'remove-object' or index is None
            or index not in to_remove]


def edit_label(path: str, operations: List[Tuple[str, Optional[int], Any]]) -> None:
    """Apply (operation, object index, value) edits to a label file, removing objects last."""
    tree = ET.parse(path)
    root = tree.getroot()
    objects = list(root.iter('object'))
    parents = {child: parent for parent in root.iter() for child in parent}
    to_remove, scale = set(), None

    for op, index, value in clean_operations(operations):
        if op == 'scale':
            scale = value                                    # applied last: the other edits use the original size
        elif op == 'set-filename':
            find_or_create(root, 'filename').text = value
        elif op == 'set-size':
            size = find_or_create(root, 'size')
            find_or_create(size, 'width').text, find_or_create(size, 'height').text = str(value[0]), str(value[1])
        elif op == 'remove-object':
            to_remove.add(index)
        elif op == 'set-class':
            find_or_create(objects[index], 'name').text = value
        elif op == 'set-box':
            box = find_or_create(objects[index], 'bndbox')
            for key, coordinate in zip(BOX_KEYS, value):
                find_or_create(box, key).text = str(coordinate)

    if scale:
        scale_label(root, *scale)
    for index in sorted(to_remove):
        parents[objects[index]].remove(objects[index])
    root.tail = '\n'
    tree.write(path, encoding='utf-8')


def scale_label(root: ET.Element, old_size: Tuple[int, int], new_size: Tuple[int, int]) -> None:
    """Scale every box (and <size>) from the old image size to the new one."""
    scale_x, scale_y = new_size[0] / old_size[0], new_size[1] / old_size[1]
    for box in root.iter('bndbox'):
        for key, scale, limit in zip(BOX_KEYS, (scale_x, scale_y, scale_x, scale_y), new_size * 2):
            element = box.find(key)
            try:
                element.text = str(min(max(int(round(float(element.text) * scale)), 0), limit))
            except (AttributeError, TypeError, ValueError, OverflowError):
                pass                                         # unreadable coordinates stay as they are (see bad-box)
    size = find_or_create(root, 'size')
    find_or_create(size, 'width').text, find_or_create(size, 'height').text = str(new_size[0]), str(new_size[1])


def describe(operation: Tuple[str, Optional[int], Any]) -> str:
    op, index, value = operation
    if op == 'scale':
        return 'boxes scaled from {}x{} to {}x{}'.format(*value[0], *value[1])
    if op == 'set-filename':
        return f'<filename> = {value}'
    if op == 'set-size':
        return '<size> = {}x{}'.format(*value)
    if op == 'set-class':
        return f'object {index}: class = {value}'
    if op == 'set-box':
        return f'object {index}: box = {value}'
    return f'object {index}: removed'


def convert_image(src: str, dst: str) -> None:
    """Rename a JPEG to its new extension, or re-encode any other format as JPEG."""
    if os.path.exists(dst):
        raise FileExistsError(dst)
    if os.path.splitext(src)[1].lower() in ('.jpg', '.jpeg'):
        os.rename(src, dst)
    else:
        with Image.open(src) as image:
            image.convert('RGB').save(dst, quality=95)
        os.remove(src)


def resize_image(path: str, size: Tuple[int, int]) -> None:
    """Resize an image in place, keeping its format (JPEG quality 95)."""
    with Image.open(path) as image:
        image_format = image.format
        resized = image.resize(size, Image.LANCZOS)
    resized.save(path, format=image_format, quality=95)


def safe_rename(src: str, dst: str) -> None:
    if os.path.exists(dst):                                  # os.rename would silently replace an empty folder
        raise FileExistsError(dst)
    os.rename(src, dst)


def remove_path(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


class Plan:
    """Changes chosen for the issues. Nothing is touched until apply()."""

    def __init__(self, checker: DatasetChecker) -> None:
        self.checker = checker
        self.root = checker.root
        self.chosen: Counter = Counter()                                      # (code, action) -> issues
        self.removals: Dict[str, str] = {}                                    # path -> issue code
        self.label_edits: Dict[str, list] = defaultdict(list)                 # label path -> operations
        self.image_fixes: Dict[str, Tuple[str, List[str]]] = {}               # image -> (new image, its labels)
        self.rescales: Dict[str, Tuple[Tuple[int, int], List[str]]] = {}      # image -> (current size, its labels)
        self.renumber: set = set()                                            # (year, group)
        self.problems: List[str] = []                                         # chosen changes that are impossible
        self.issue_counts = Counter((issue.sequence, issue.code) for issue in checker.issues)

    def add(self, issue: Issue, action: str) -> None:
        getattr(self, ISSUES[issue.code][2][action][0])(issue)
        self.chosen[issue.code, action] += 1

    def path(self, issue: Issue, *parts: str) -> str:
        return os.path.join(self.root, issue.sequence, *parts)

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root)

    # ------------------------------------------------ one method per action kind

    def remove_entry(self, issue: Issue) -> None:
        self.removals[self.path(issue, issue.path)] = issue.code

    def remove_sequence(self, issue: Issue) -> None:
        self.removals[self.path(issue)] = issue.code

    def remove_image(self, issue: Issue, name: Optional[str] = None) -> None:
        name = name or os.path.basename(issue.path)
        self.removals[self.path(issue, 'images', name)] = issue.code
        for label in self.checker.references.get((issue.sequence, name), []):
            self.removals[self.path(issue, 'labels', label)] = issue.code

    def remove_image_or_sequence(self, issue: Issue) -> None:
        """Delete the image and its labels, or the whole sequence if none of its images would be left."""
        if self.issue_counts[issue.sequence, issue.code] == self.checker.counts[issue.sequence]['images']:
            self.remove_sequence(issue)
        else:
            self.remove_image(issue)

    def rescale_image(self, issue: Issue) -> None:
        labels = self.checker.references.get((issue.sequence, os.path.basename(issue.path)), [])
        self.rescales[self.path(issue, issue.path)] = (issue.data, [self.path(issue, 'labels', label) for label in labels])

    def remove_label_and_image(self, issue: Issue) -> None:
        """For labels that cannot be read: the image is found by name (frame_0001.xml -> images/frame_0001.*)."""
        self.remove_entry(issue)
        stem = os.path.splitext(os.path.basename(issue.path))[0]
        images_dir = self.path(issue, 'images')
        names = [name for name in (sorted(os.listdir(images_dir)) if os.path.isdir(images_dir) else [])
                 if os.path.splitext(name)[0] == stem and os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS]
        if not names:
            self.problems.append(f'{os.path.join(issue.sequence, issue.path)}: no image with the same name, '
                                 f'only the label is removed')
        for name in names:
            self.remove_image(issue, name)

    def remove_object(self, issue: Issue) -> None:
        self.label_edits[self.path(issue, issue.path)].append(('remove-object', issue.data['object'], None))

    def fix_filename(self, issue: Issue) -> None:
        if issue.data is None:
            self.problems.append(f'cannot fix {issue.code} {os.path.join(issue.sequence, issue.path)}: '
                                 f'no image named like the label')
        else:
            self.label_edits[self.path(issue, issue.path)].append(('set-filename', None, issue.data))

    def fix_size(self, issue: Issue) -> None:
        self.label_edits[self.path(issue, issue.path)].append(('set-size', None, issue.data))

    def fix_box(self, issue: Issue) -> None:
        index, box = issue.data['object'], sanitize_box(issue.data['box'], issue.data['size'])
        operation = ('remove-object', index, None) if box is None else ('set-box', index, box)
        self.label_edits[self.path(issue, issue.path)].append(operation)

    def fix_class(self, issue: Issue) -> None:
        self.label_edits[self.path(issue, issue.path)].append(('set-class', issue.data['object'], self.checker.classes[0]))

    def fix_extension(self, issue: Issue) -> None:
        src = self.path(issue, issue.path)
        dst = os.path.splitext(src)[0] + EXPECTED_IMAGE_EXTENSION
        if os.path.exists(dst) or any(dst == d for d, _ in self.image_fixes.values()):
            self.problems.append(f'cannot fix {issue.code} {self.rel(src)}: {self.rel(dst)} already exists')
            return
        labels = self.checker.references.get((issue.sequence, os.path.basename(src)), [])
        self.image_fixes[src] = (dst, [self.path(issue, 'labels', label) for label in labels])

    def fix_gap(self, issue: Issue) -> None:
        self.renumber.add(issue.data)

    # --------------------------------------------------------------------- apply

    def apply(self, dry_run: bool, paint: 'Painter') -> None:
        """Remove, rescale images, rename images, edit labels and renumber sequences, in this order (paths stay valid)."""
        done, failed, removed = Counter(), [], []

        def gone(path: str) -> bool:
            return any(path == r or path.startswith(r + os.sep) for r in removed)

        def run(kind: str, text: str, operation: Callable[[], None]) -> bool:
            if dry_run:
                print(f'  {kind:<16} {text}')
            else:
                try:
                    operation()
                except Exception as e:
                    failed.append(f'{kind} {text}: {e}')
                    print(paint(f'  FAILED {failed[-1]}', ERROR))
                    return False
            done[kind] += 1
            return True

        for path in sorted(self.removals):                   # parents sort before their children
            if not gone(path) and run('remove', self.rel(path), partial(remove_path, path)):
                removed.append(path)

        target = self.checker.resolution
        for path, (size, labels) in sorted(self.rescales.items()):
            if not gone(path) and run('rescale image', '{}: {}x{} -> {}x{}'.format(self.rel(path), *size, *target),
                                      partial(resize_image, path, target)):
                for label in labels:                         # only scale the labels if the image was resized
                    self.label_edits[label].append(('scale', None, (size, target)))

        for src, (dst, labels) in sorted(self.image_fixes.items()):
            if not gone(src) and run('rename image', f'{self.rel(src)} -> {os.path.basename(dst)}',
                                     partial(convert_image, src, dst)):
                for label in labels:
                    self.label_edits[label].append(('set-filename', None, os.path.basename(dst)))

        for label, operations in sorted(self.label_edits.items()):
            if not gone(label):
                run('edit label', f"{self.rel(label)}: {'; '.join(describe(op) for op in clean_operations(operations))}",
                    partial(edit_label, label, operations))

        for year, group in sorted(self.renumber):
            prefix = f'PIDS{year}_GR{group}_'
            names = sorted(n for n in os.listdir(self.root) if n.startswith(prefix) and SEQUENCE_PATTERN.match(n)
                           and not gone(os.path.join(self.root, n)))
            for index, name in enumerate(names):             # ascending order: the target index is always free
                new_name = f'{prefix}{index:04d}'
                if new_name != name:
                    run('rename sequence', f'{name} -> {new_name}',
                        partial(safe_rename, os.path.join(self.root, name), os.path.join(self.root, new_name)))

        summary = ', '.join(f'{n} {kind}' for kind, n in done.items()) or 'no changes'
        if dry_run:
            print(f'\nDry run, nothing was changed ({summary}).')
        else:
            print(f'\nDone: {summary}' + (paint(f', {len(failed)} failed', ERROR) if failed else '') + '.')
            print('Run the check again to verify the result.')


# ======================================================================== output

class Painter:
    """ANSI colours, only when writing to a terminal (and NO_COLOR is not set)."""
    STYLES = {ERROR: '1;31', WARNING: '1;33', INFO: '36', 'bold': '1', 'dim': '2', 'green': '32'}

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, style: str) -> str:
        return f'\033[{self.STYLES[style]}m{text}\033[0m' if self.enabled else text


def shown_severities(level: str) -> Tuple[str, ...]:
    return SEVERITIES[:SEVERITIES.index(level) + 1]


def format_examples(issues: List[Issue], max_examples: int) -> str:
    if issues[0].code in SUMMARISE_BY_DETAIL:
        items = [f'{detail} ({n})' for detail, n in Counter(i.detail for i in issues).most_common()]
    else:
        items = list(dict.fromkeys(f'{i.path} ({i.detail})' if i.detail else i.path for i in issues if i.path))
    if max_examples and len(items) > max_examples:
        items = items[:max_examples] + [f'+{len(items) - max_examples} more']
    return ', '.join(items)


def issue_line(severity: str, code: str, paint: Painter) -> str:
    return f"  {paint(f'{severity:<7}', severity)} {code:<21}"


def print_report(checker: DatasetChecker, actions: Dict[str, str], level: str, max_examples: int, paint: Painter) -> None:
    shown = shown_severities(level)
    by_sequence = defaultdict(lambda: defaultdict(list))
    for issue in checker.issues:
        if ISSUES[issue.code][0] in shown:
            by_sequence[issue.sequence][issue.code].append(issue)

    # Only sequences with issues (dataset-level issues first)
    for sequence in sorted(by_sequence):
        if sequence:
            counts = checker.counts[sequence]
            print(f"\n{paint(sequence, 'bold')}  " + paint(f"{counts['images']} images, {counts['labels']} labels", 'dim'))
        else:
            print('\n' + paint('Dataset root', 'bold'))
        for code in sorted(by_sequence[sequence], key=issue_order):
            issues = by_sequence[sequence][code]
            action = paint(f'  -> {actions[code]}', 'green') if code in actions else ''
            examples = format_examples(issues, max_examples) or paint(ISSUES[code][1], 'dim')
            print(f'{issue_line(ISSUES[code][0], code, paint)} {len(issues):>5}  {examples}{action}')

    # Summary
    worst = {}
    for issue in checker.issues:
        severity = SEVERITIES.index(ISSUES[issue.code][0])
        if issue.sequence and ISSUES[issue.code][0] in shown:
            worst[issue.sequence] = min(worst.get(issue.sequence, severity), severity)
    n_worst = Counter(worst.values())
    totals = sum(checker.counts.values(), Counter())
    status = [paint(f'{len(checker.sequences) - len(worst)} OK', 'green')]
    status += [paint(f'{n_worst[i]} with {s.lower()}s' if s != INFO else f'{n_worst[i]} with info', s)
               for i, s in enumerate(shown) if n_worst[i]]
    print(f"\n{paint('Summary', 'bold')}  {len(checker.sequences)} sequences, {totals['images']} images, "
          f"{totals['labels']} labels, {totals['objects']} objects: " + ', '.join(status))

    found = defaultdict(list)
    for issue in checker.issues:
        found[issue.code].append(issue)
    if not found:
        print(paint('No issues found.', 'green'))
        return

    width = max(len(' '.join(['[skip]', *ISSUES[code][2]])) for code in found)
    print(paint(f"  {'':<7} {'Issue':<21} {'Count':>5} {'Seqs':>5}  {'Actions':<{width}}  Description", 'dim'))
    for code in sorted(found, key=issue_order):
        severity, description, options = ISSUES[code]
        chosen = actions.get(code, 'skip')
        names = [f'[{a}]' if a == chosen else a for a in ['skip', *options]]
        choices = ' '.join(paint(n, 'green') if n == f'[{chosen}]' != '[skip]' else n for n in names)
        choices += ' ' * (width - len(' '.join(names)))      # pad the plain text: colour codes have no width
        hidden = '' if severity in shown else paint(' (not listed)', 'dim')
        n_sequences = len({i.sequence for i in found[code]})
        print(f'{issue_line(severity, code, paint)} {len(found[code]):>5} {n_sequences:>5}  {choices}  '
              f'{description}{hidden}')

    if any(ISSUES[code][0] not in shown for code in found):
        print(paint(f'(not listed) issues are listed per sequence with --level {ISSUES[max(found, key=issue_order)][0].lower()}', 'dim'))
    if not actions and any(ISSUES[code][2] for code in found):
        print(paint('Choose what to do with -a CODE=ACTION (e.g. -a hidden-entry=remove) or -i; see --help.', 'dim'))


def print_plan(plan: Plan, paint: Painter) -> None:
    print('\n' + paint('Planned changes', 'bold'))
    width = max(len(action) for _, action in plan.chosen)
    for (code, action), n in sorted(plan.chosen.items(), key=lambda item: issue_order(item[0][0])):
        print(f'  {action:<{width}} {code:<21} {n:>5}  {ISSUES[code][2][action][1]}')
    for problem in plan.problems:
        print(paint(f'  {problem}', WARNING))


def actions_help() -> str:
    lines = ['issues and their actions (skip, the default, is always valid):']
    for code, (severity, _, options) in ISSUES.items():
        if not options:
            lines.append(f'  {severity:<7} {code:<21}  -')
        for n, (action, (_, help_text)) in enumerate(options.items()):
            prefix = f'  {severity:<7} {code:<21}' if n == 0 else ' ' * 31
            lines.append(f'{prefix}  {action}: {help_text}')
    return '\n'.join(lines)


# ======================================================================== main

def parse_resolution(text: str) -> Tuple[int, int]:
    match = re.match(r'^(\d+)x(\d+)$', text)
    if match is None or 0 in (int(match.group(1)), int(match.group(2))):
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT (e.g. 1280x720), got '{text}'")
    return int(match.group(1)), int(match.group(2))


def parse_actions(values: List[str], parser: argparse.ArgumentParser) -> Dict[str, str]:
    """'code1,code2=action' -> {code1: action, code2: action}, validating that each action is allowed."""
    actions = {}
    for value in values:
        codes, separator, action = value.partition('=')
        if not separator:
            parser.error(f"--action expects CODE=ACTION, got '{value}'")
        for code in codes.split(','):
            if code not in ISSUES:
                parser.error(f"unknown issue '{code}' (see --help)")
            allowed = ['skip', *ISSUES[code][2]]
            if action not in allowed:
                parser.error(f"'{action}' is not valid for {code}; choose one of: {', '.join(allowed)}")
            if action == 'skip':
                actions.pop(code, None)
            else:
                actions[code] = action
    return actions


def ask_actions(checker: DatasetChecker, actions: Dict[str, str], level: str, paint: Painter) -> None:
    """Ask what to do with each type of issue found (unless already chosen with --action)."""
    shown = shown_severities(level)
    found = Counter(i.code for i in checker.issues if ISSUES[i.code][0] in shown)
    pending = [code for code in sorted(found, key=issue_order) if ISSUES[code][2] and code not in actions]
    if pending:
        print('\n' + paint('What should be done with each issue?', 'bold'))

    for code in pending:
        severity, description, options = ISSUES[code]
        choices = {'skip': 'leave it as it is', **{action: help_text for action, (_, help_text) in options.items()}}
        print(f"\n  {paint(severity, severity)} {code} ({found[code]}): {description}")
        for number, (action, help_text) in enumerate(choices.items()):
            print(f'    [{number}] {action}: {help_text}')
        while True:
            answer = input('    choice (number or name) [0]: ').strip().lower() or '0'
            matches = [action for number, action in enumerate(choices) if answer in (action, str(number))]
            if matches:
                break
        if matches[0] != 'skip':
            actions[code] = matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=actions_help(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('dataset', help='Dataset folder')
    parser.add_argument('--classes', nargs='+', default=['robot'], help='Accepted object class names')
    parser.add_argument('--resolution', type=parse_resolution, default=EXPECTED_RESOLUTION, metavar='WIDTHxHEIGHT',
                        help='Expected image resolution, also the target of unusual-resolution=rescale (default: {}x{})'
                        .format(*EXPECTED_RESOLUTION))
    parser.add_argument('--verify', action='store_true', help='Fully decode every image (slower, finds truncated files)')
    parser.add_argument('--duplicates', action='store_true', help='Hash every image to find identical copies')
    parser.add_argument('--level', choices=[s.lower() for s in SEVERITIES], default='warning',
                        help='Lowest severity listed per sequence (default: warning)')
    parser.add_argument('--max-examples', type=int, default=3, help='Files listed per issue (0 = all)')
    parser.add_argument('-a', '--action', action='append', default=[], metavar='CODE=ACTION',
                        help='What to do with an issue; several codes can be separated by commas (repeatable)')
    parser.add_argument('-i', '--interactive', action='store_true', help='Ask what to do with each type of issue found')
    parser.add_argument('--dry-run', action='store_true', help='List the changes without applying them')
    parser.add_argument('-y', '--yes', action='store_true', help='Apply the changes without asking for confirmation')
    args = parser.parse_args()

    if not os.path.isdir(args.dataset):
        parser.error(f"'{args.dataset}' is not a folder")
    actions = parse_actions(args.action, parser)
    needs_terminal = args.interactive or (actions and not args.dry_run and not args.yes)
    if needs_terminal and not sys.stdin.isatty():
        parser.error('asking questions needs a terminal: use --dry-run or --yes')

    paint = Painter(sys.stdout.isatty() and 'NO_COLOR' not in os.environ)
    level = args.level.upper()
    checker = DatasetChecker(args.dataset, args.classes, args.resolution, verify=args.verify, duplicates=args.duplicates)
    checker.run()
    print_report(checker, actions, level, args.max_examples, paint)

    exit_code = 1 if any(ISSUES[i.code][0] == ERROR for i in checker.issues) else 0
    try:
        if args.interactive:
            ask_actions(checker, actions, level, paint)
        plan = Plan(checker)
        for issue in checker.issues:
            if issue.code in actions:
                plan.add(issue, actions[issue.code])
        if not plan.chosen:
            return exit_code
        print_plan(plan, paint)
        if not (args.dry_run or args.yes or
                input(f'\nApply these changes to {os.path.realpath(args.dataset)}? [y/N] ').strip().lower() in ('y', 'yes')):
            print('Nothing was changed.')
            return exit_code
    except (EOFError, KeyboardInterrupt):
        print('\nAborted, nothing was changed.')
        return 130

    print()
    plan.apply(dry_run=args.dry_run, paint=paint)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
