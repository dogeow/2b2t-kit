"""Read-only dependency closure check for patched Java class families."""
import argparse
import json
import re
import struct
import zipfile


def references(data):
    if data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('Not a Java class file')
    try:
        count = struct.unpack_from('>H', data, 8)[0]
        utf8, classes = {}, []
        offset, index = 10, 1
        while index < count:
            tag = data[offset]
            offset += 1
            if tag == 1:
                length = struct.unpack_from('>H', data, offset)[0]
                offset += 2
                if offset + length > len(data):
                    raise ValueError('Truncated class constant')
                utf8[index] = data[offset:offset + length].decode('utf-8', errors='replace')
                offset += length
            elif tag == 7:
                classes.append(struct.unpack_from('>H', data, offset)[0])
                offset += 2
            elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
                offset += 4
            elif tag in (5, 6):
                offset += 8
                index += 1
            elif tag in (8, 16, 19, 20):
                offset += 2
            elif tag == 15:
                offset += 3
            else:
                raise ValueError('Unknown class constant tag: ' + str(tag))
            if offset > len(data):
                raise ValueError('Truncated class constant pool')
            index += 1
        result = set()
        for ref in classes:
            name = utf8[ref]
            if not name.startswith('['):
                result.add(name)
        for value in utf8.values():
            result.update(re.findall(r'L([A-Za-z0-9_/$]+)', value))
        return result
    except (IndexError, KeyError, struct.error) as error:
        raise ValueError('Invalid class constant pool') from error


def check(path, families, namespace='dev/twob2tkit/'):
    with zipfile.ZipFile(path) as jar:
        names = set(jar.namelist())
        missing, checked = [], []
        for name in sorted(names):
            if not name.endswith('.class'):
                continue
            cls = name[:-6]
            if not any(cls == family or cls.startswith(family + '$') for family in families):
                continue
            checked.append(name)
            for ref in sorted(references(jar.read(name))):
                if ref.startswith(namespace) and ref + '.class' not in names:
                    missing.append({'source': name, 'missing': ref + '.class'})
        for family in families:
            if family + '.class' not in names:
                missing.append({'source': 'requested_family', 'missing': family + '.class'})
        return {'complete': not missing, 'checked_classes': checked, 'missing': missing}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('jar')
    parser.add_argument('--family', action='append', required=True)
    args = parser.parse_args()
    result = check(args.jar, args.family)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['complete'] else 1)


if __name__ == '__main__':
    main()
