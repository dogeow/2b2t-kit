import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from check_jar_class_closure import check, references


def class_bytes(names=(), descriptors=()):
    entries = []
    for name in names:
        encoded = name.encode()
        entries.append(b'\x01' + struct.pack('>H', len(encoded)) + encoded)
        entries.append(b'\x07' + struct.pack('>H', len(entries)))
    for text in descriptors:
        encoded = text.encode()
        entries.append(b'\x01' + struct.pack('>H', len(encoded)) + encoded)
    return b'\xca\xfe\xba\xbe\x00\x00\x00\x45' + struct.pack('>H', len(entries) + 1) + b''.join(entries)


class ClosureTests(unittest.TestCase):
    def test_missing_compiler_enum_switch_class_is_detected(self):
        family = 'dev/twob2tkit/builder/Reach'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'candidate.jar'
            with zipfile.ZipFile(path, 'w') as jar:
                jar.writestr(family + '.class', class_bytes([family, family + '$1']))
            result = check(path, [family])
            self.assertFalse(result['complete'])
            self.assertEqual(family + '$1.class', result['missing'][0]['missing'])

    def test_complete_family_needs_no_source_directory_fallback(self):
        family = 'dev/twob2tkit/builder/Reach'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'candidate.jar'
            with zipfile.ZipFile(path, 'w') as jar:
                jar.writestr(family + '.class', class_bytes([family, family + '$1', 'java/lang/Object']))
                jar.writestr(family + '$1.class', class_bytes([family]))
            self.assertTrue(check(path, [family])['complete'])

    def test_descriptors_and_missing_root_are_checked(self):
        name = 'dev/twob2tkit/OnlyInDescriptor'
        self.assertIn(name, references(class_bytes(descriptors=['(L' + name + ';)V'])))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.jar'
            with zipfile.ZipFile(path, 'w'):
                pass
            self.assertFalse(check(path, [name])['complete'])

    def test_malformed_constants_fail_closed(self):
        for data in (b'bad', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbe\x00\x00\x00\x45\x00\x02\xff'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                references(data)
