"""Bounded, read-only snow hints from the current Bobby MCA cache.

The seed-scout hash is used only to select Bobby's current world directory.  It
is intentionally absent from candidates, exceptions, and the optional index.
Cached chunks are hints: callers must still obtain normal host authorization
and verify the loaded server chunk before acting on one.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
import zlib


INDEX_VERSION = 2
WORLD_BORDER = 29_999_984
MAX_REGION_BYTES = 128 * 1024 * 1024
MAX_SCAN_BYTES = 256 * 1024 * 1024
MAX_REGION_FILES = 256
MAX_CANDIDATES = 512
MAX_NBT_BYTES = 16 * 1024 * 1024
MAX_NBT_NODES = 262_144
MAX_NBT_COLLECTION = 262_144
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_INDEX_ENTRIES = 4096
MAX_INDEX_CHUNKS = 1024
MAX_VISITED = 65_536
MAX_SAFE_INTEGER = (1 << 53) - 1

REGION_NAME = re.compile(r"r\.(-?\d+)\.(-?\d+)\.mca")
FINGERPRINT = re.compile(r"[0-9a-f]{64}")

# Conservative list: every entry has a cold/snow-covered surface in vanilla.
SNOW_BIOMES = frozenset({
    "minecraft:snowy_plains",
    "minecraft:ice_spikes",
    "minecraft:snowy_taiga",
    "minecraft:snowy_beach",
    "minecraft:grove",
    "minecraft:snowy_slopes",
    "minecraft:frozen_peaks",
    "minecraft:jagged_peaks",
    "minecraft:frozen_river",
    "minecraft:frozen_ocean",
    "minecraft:deep_frozen_ocean",
})


class CacheUnavailable(RuntimeError):
    """A sanitized failure to locate the current Bobby cache."""


class _Rejected(Exception):
    """Internal malformed/unsupported region or NBT marker."""


def canonical_server(server):
    """Return a stable server identity, omitting Minecraft's default port."""
    if not isinstance(server, str):
        raise CacheUnavailable("Bobby server identity is unavailable")
    value = server.strip().lower()
    if not value or len(value) > 255 or any(char in value for char in "/\\\x00"):
        raise CacheUnavailable("Bobby server identity is unavailable")
    if value.startswith("["):
        end = value.find("]")
        if end < 2 or end + 1 < len(value) and value[end + 1] != ":":
            raise CacheUnavailable("Bobby server identity is unavailable")
        host = value[:end + 1]
        port = value[end + 2:] if end + 1 < len(value) else ""
    elif value.count(":") == 1:
        host, port = value.rsplit(":", 1)
    else:
        host, port = value, ""
    if not host or port and (not port.isdigit() or not 1 <= int(port) <= 65535):
        raise CacheUnavailable("Bobby server identity is unavailable")
    return host if not port or port == "25565" else f"{host}:{int(port)}"


def candidates(automation_root, server, dimension, origin, visited=(), *,
               target_y=200.0, max_candidates=MAX_CANDIDATES, index_path=None):
    """Return nearest unvisited full snowy chunks from the current Bobby world.

    ``automation_root`` is the active Minecraft instance directory containing
    ``.bobby`` and ``config/twob2tkit/seed-scout.json``.  MCA files are never
    modified.  A small derived index is stored outside ``.bobby``; it contains
    no world hash or absolute path.
    """
    root = Path(automation_root)
    cache_server = canonical_server(server)
    dimension = _dimension(dimension)
    ox, oz = _origin(origin)
    if (type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES
            or type(target_y) not in (int, float) or not math.isfinite(target_y)
            or not 160 <= target_y <= 316):
        raise ValueError("Bobby candidate bounds are invalid")
    directories = _current_dimensions(root, server, dimension)
    index_file = Path(index_path) if index_path is not None else _default_index(root)
    index = _load_index(index_file)
    entries = index["entries"]
    seen = _visited(visited)
    region_files = []
    available_keys = set()
    try:
        for alias_rank, (cache_folder, directory) in enumerate(directories):
            for path in directory.iterdir():
                parsed = _region_coordinates(path.name)
                if parsed is None or path.is_symlink() or not path.is_file():
                    continue
                rx, rz = parsed
                center_x, center_z = rx * 512 + 256, rz * 512 + 256
                distance = (center_x - ox) ** 2 + (center_z - oz) ** 2
                key = _index_key(cache_server, dimension, cache_folder, path.name)
                available_keys.add(key)
                region_files.append((distance, alias_rank, path.name, path,
                                     cache_folder, rx, rz, key))
    except OSError:
        raise CacheUnavailable("Bobby dimension cache cannot be read") from None
    region_files.sort(key=lambda row: (row[0], row[1], row[2]))
    region_files = region_files[:MAX_REGION_FILES]
    changed = False
    scanned_bytes = 0
    rows = []
    found_chunks = set()
    for _, _, name, path, cache_folder, rx, rz, key in region_files:
        try:
            stat = path.stat()
            if (stat.st_size < 8192 or stat.st_size > MAX_REGION_BYTES
                    or scanned_bytes + stat.st_size > MAX_SCAN_BYTES):
                continue
            scanned_bytes += stat.st_size
            cached = entries.get(key)
            if _cached_region(cached, cache_server, dimension, cache_folder, name,
                              stat):
                fingerprint=cached['fingerprint']
                chunks = cached["chunks"]
            else:
                fingerprint = _content_fingerprint(path, stat.st_size)
                after_hash = path.stat()
                if not _same_file(stat, after_hash):
                    continue
                chunks = _scan_region(path, rx, rz, stat.st_size)
                after_scan = path.stat()
                if not _same_file(stat, after_scan):
                    continue
                entries[key] = {
                    "server": cache_server,
                    "dimension": dimension,
                    "cache_folder": cache_folder,
                    "region_file": name,
                    "mtime_ns": stat.st_mtime_ns,
                    "ctime_ns": stat.st_ctime_ns,
                    "size": stat.st_size,
                    "file_id": _file_id(stat),
                    "fingerprint": fingerprint,
                    "chunks": chunks,
                }
                changed = True
            for chunk in chunks:
                cx, cz = chunk["chunk"]
                if not _inside_world(cx, cz):
                    continue
                if (cx, cz) in found_chunks:
                    continue
                found_chunks.add((cx, cz))
                x, z = cx * 16 + 8.5, cz * 16 + 8.5
                distance_sq = (x - ox) ** 2 + (z - oz) ** 2
                rows.append({
                    "source": "bobby_cache",
                    "cache_server": cache_server,
                    "dimension": dimension,
                    "chunk": [cx, cz],
                    "tile": [cx * 16, cz * 16],
                    "target": [x, float(target_y), z],
                    "region_file": name,
                    "fingerprint": fingerprint,
                    "mtime_ns": stat.st_mtime_ns,
                    "ctime_ns": stat.st_ctime_ns,
                    "size": stat.st_size,
                    "file_id": _file_id(stat),
                    "biomes": list(chunk["biomes"]),
                    "distance_sq": distance_sq,
                })
        except (OSError, _Rejected, ValueError, OverflowError):
            # A live cache can contain a partly-written region.  It contributes
            # no hint until a later call observes a complete stable file.
            continue
    prefix = f"{cache_server}\x00{dimension}\x00"
    for key in list(entries):
        if key.startswith(prefix) and key not in available_keys:
            del entries[key]
            changed = True
    if len(entries) > MAX_INDEX_ENTRIES:
        keep = set(key for key in sorted(available_keys) if key in entries)
        if len(keep) > MAX_INDEX_ENTRIES:
            keep = set(sorted(keep)[:MAX_INDEX_ENTRIES])
        for key in sorted(entries, reverse=True):
            if len(keep) >= MAX_INDEX_ENTRIES:
                break
            keep.add(key)
        entries = {key: entries[key] for key in sorted(keep)}
        index["entries"] = entries
        changed = True
    if changed:
        _save_index(index_file, index)
    rows.sort(key=lambda row: (
        tuple(row["chunk"]) in seen,
        row["distance_sq"],
        row["chunk"][0],
        row["chunk"][1],
    ))
    return rows[:max_candidates]


def validate_candidate(automation_root, server, dimension, candidate, *, quick=False):
    """Revalidate a candidate against the current world and region content."""
    try:
        root = Path(automation_root)
        cache_server = canonical_server(server)
        dimension = _dimension(dimension)
        if (not isinstance(candidate, dict)
                or candidate.get("source") != "bobby_cache"
                or candidate.get("cache_server") != cache_server
                or candidate.get("dimension") != dimension
                or not isinstance(candidate.get("chunk"), list)
                or len(candidate["chunk"]) != 2
                or any(type(value) is not int for value in candidate["chunk"])
                or candidate.get("tile") != [candidate["chunk"][0] * 16,
                                               candidate["chunk"][1] * 16]
                or not isinstance(candidate.get("target"), list)
                or len(candidate["target"]) != 3
                or not isinstance(candidate.get("biomes"), list)
                or not candidate["biomes"]
                or candidate["biomes"] != sorted(set(candidate["biomes"]))
                or any(type(value) is not str or value not in SNOW_BIOMES
                       for value in candidate["biomes"])
                or not isinstance(candidate.get("region_file"), str)
                or not isinstance(candidate.get("fingerprint"), str)
                or not FINGERPRINT.fullmatch(candidate["fingerprint"])
                or type(candidate.get("mtime_ns")) is not int
                or candidate["mtime_ns"] < 0
                or type(candidate.get("ctime_ns")) is not int
                or candidate["ctime_ns"] < 0
                or type(candidate.get("size")) is not int
                or not 8192 <= candidate["size"] <= MAX_REGION_BYTES
                or type(candidate.get("file_id")) is not int
                or not 0 <= candidate["file_id"] <= MAX_SAFE_INTEGER
                or type(quick) is not bool):
            return False
        cx, cz = candidate["chunk"]
        target = candidate["target"]
        if (any(type(value) not in (int, float) or not math.isfinite(value)
                for value in target)
                or target[0] != cx * 16 + 8.5 or target[2] != cz * 16 + 8.5
                or not 160 <= target[1] <= 316):
            return False
        if not _inside_world(cx, cz):
            return False
        parsed = _region_coordinates(candidate["region_file"])
        if parsed is None:
            return False
        rx, rz = parsed
        if cx // 32 != rx or cz // 32 != rz:
            return False
        for _, directory in _current_dimensions(root, server, dimension):
            path = directory / candidate["region_file"]
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            if stat.st_size < 8192 or stat.st_size > MAX_REGION_BYTES:
                continue
            if (stat.st_size != candidate["size"]
                    or stat.st_mtime_ns != candidate["mtime_ns"]
                    or stat.st_ctime_ns != candidate["ctime_ns"]
                    or _file_id(stat) != candidate["file_id"]):
                continue
            if quick:
                return True
            if _content_fingerprint(path, stat.st_size) != candidate["fingerprint"]:
                continue
            after_hash = path.stat()
            if not _same_file(stat, after_hash):
                continue
            biomes = _snowy_biomes(
                _read_chunk(path, rx, rz, cx, cz, stat.st_size), cx, cz)
            if not _same_file(stat, path.stat()):
                continue
            if biomes == candidate["biomes"]:
                return True
        return False
    except (CacheUnavailable, OSError, _Rejected, ValueError, OverflowError):
        return False


def validate_current_world(automation_root,server,dimension,candidate):
    """Cheap per-leg identity check tolerant of Bobby extending the region.

    Ordinary travel loads chunks and may legitimately rewrite the same MCA.
    The immutable preflight fingerprint remains in the route ledger, while
    each leg only proves that the current seed-scout world/server/dimension
    still owns this bounded region/chunk name.  Live biome/block scans are the
    post-arrival authority.
    """
    try:
        root=Path(automation_root);canonical=canonical_server(server)
        dimension=_dimension(dimension)
        if (not isinstance(candidate,dict)
                or candidate.get('source')!='bobby_cache'
                or candidate.get('cache_server')!=canonical
                or candidate.get('dimension')!=dimension
                or not isinstance(candidate.get('chunk'),list)
                or len(candidate['chunk'])!=2
                or any(type(value) is not int for value in candidate['chunk'])
                or candidate.get('tile')!=[candidate['chunk'][0]*16,
                                            candidate['chunk'][1]*16]
                or not isinstance(candidate.get('region_file'),str)):
            return False
        parsed=_region_coordinates(candidate['region_file'])
        if parsed is None or (candidate['chunk'][0]//32,candidate['chunk'][1]//32)!=parsed:
            return False
        return any((not (path:=directory/candidate['region_file']).is_symlink()
                    and path.is_file() and 8192<=path.stat().st_size<=MAX_REGION_BYTES)
                   for _,directory in _current_dimensions(root,server,dimension))
    except (CacheUnavailable,OSError,ValueError,TypeError,OverflowError):
        return False


def _origin(origin):
    if not isinstance(origin, (list, tuple)) or len(origin) not in (2, 3):
        raise ValueError("Bobby origin is invalid")
    values = (origin[0], origin[-1])
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Bobby origin is invalid")
    return float(values[0]), float(values[1])


def _visited(visited):
    result = set()
    if visited is None:
        return result
    try:
        for number, value in enumerate(visited):
            if number >= MAX_VISITED:
                raise ValueError("Bobby visited chunks are invalid")
            if isinstance(value, dict):
                value = value.get("chunk")
            if isinstance(value, str) and re.fullmatch(r"-?\d+:-?\d+", value):
                value = value.split(":")
            if (isinstance(value, (list, tuple)) and len(value) == 2
                    and all(type(part) is int or isinstance(part, str)
                            and re.fullmatch(r"-?\d+", part) for part in value)):
                result.add((int(value[0]), int(value[1])))
    except TypeError:
        raise ValueError("Bobby visited chunks are invalid") from None
    return result


def _dimension(value):
    if not isinstance(value, str) or value.count(":") != 1 or len(value) > 255:
        raise CacheUnavailable("Bobby dimension identity is unavailable")
    namespace, path = value.lower().split(":", 1)
    parts = path.split("/")
    valid = re.compile(r"[a-z0-9._-]+")
    if not valid.fullmatch(namespace) or not parts or any(not valid.fullmatch(part) for part in parts):
        raise CacheUnavailable("Bobby dimension identity is unavailable")
    return f"{namespace}:{'/'.join(parts)}"


def _server_folders(server):
    raw = server.strip().lower()
    canonical = canonical_server(raw)
    names = [raw.replace(":", "_")]
    if canonical != raw:
        names.append(canonical.replace(":", "_"))
    elif ":" not in raw and not raw.startswith("["):
        names.append(raw + "_25565")
    for name in names:
        if not re.fullmatch(r"[a-z0-9._\[\]-]+", name):
            raise CacheUnavailable("Bobby server identity is unavailable")
    return tuple(dict.fromkeys(names))


def _seed_hash(root):
    paths = (
        root / "config" / "twob2tkit" / "seed-scout.json",
        root / "config" / "autocruise" / "seed-scout.json",
        root / "seed-scout.json",
    )
    for path in paths:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > 1024 * 1024:
                raise CacheUnavailable("Seed scout state is unavailable")
            value = json.loads(path.read_text(encoding="utf-8"))
            hashed = value.get("hashedSeed") if isinstance(value, dict) else None
            if (value.get("hasHashedSeed") is True and type(hashed) is int
                    and -(1 << 63) <= hashed < (1 << 63)):
                return hashed
            raise CacheUnavailable("Seed scout state is unavailable")
        except CacheUnavailable:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise CacheUnavailable("Seed scout state is unavailable") from None
    raise CacheUnavailable("Seed scout state is unavailable")


def _current_dimensions(root, server, dimension):
    bobby = root if root.name == ".bobby" else root / ".bobby"
    if bobby.is_symlink() or not bobby.is_dir():
        raise CacheUnavailable("Bobby cache is unavailable")
    world_name = str(_seed_hash(root))
    namespace, path = dimension.split(":", 1)
    parts = (namespace, *path.split("/"))
    try:
        resolved_root = bobby.resolve(strict=True)
    except OSError:
        raise CacheUnavailable("Bobby cache is unavailable") from None
    found = []
    for server_folder in _server_folders(server):
        current = bobby / server_folder
        world = current / world_name
        directory = world
        components = [current, world]
        for part in parts:
            directory /= part
            components.append(directory)
        if any(part.is_symlink() for part in components):
            continue
        try:
            resolved = directory.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        if resolved.is_dir():
            found.append((server_folder, resolved))
    if found:
        return found
    raise CacheUnavailable("Current Bobby world is unavailable")


def _default_index(root):
    return root / "config" / "twob2tkit" / "bobby-snow-index.json"


def _region_coordinates(name):
    match = REGION_NAME.fullmatch(name)
    if not match:
        return None
    rx, rz = int(match.group(1)), int(match.group(2))
    if abs(rx) > 60_000 or abs(rz) > 60_000:
        return None
    return rx, rz


def _inside_world(cx, cz):
    x, z = cx * 16 + 8.5, cz * 16 + 8.5
    return -WORLD_BORDER < x < WORLD_BORDER and -WORLD_BORDER < z < WORLD_BORDER


def _same_file(before, after):
    return (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)


def _file_id(stat):
    """Stable opaque file identity that is exactly representable in JSON/JS."""
    identity = f"{stat.st_dev}:{stat.st_ino}".encode("ascii")
    return int.from_bytes(hashlib.blake2s(identity, digest_size=6).digest(), "big")


def _content_fingerprint(path, expected_size):
    if expected_size > MAX_REGION_BYTES:
        raise _Rejected()
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_REGION_BYTES:
                raise _Rejected()
            digest.update(block)
    if total != expected_size:
        raise _Rejected()
    return digest.hexdigest()


def _scan_region(path, rx, rz, size):
    with path.open("rb") as stream:
        header = stream.read(4096)
        if len(header) != 4096:
            raise _Rejected()
        locations = _locations(header, size)
        chunks = []
        for slot, location in enumerate(locations):
            if location is None:
                continue
            cx, cz = rx * 32 + slot % 32, rz * 32 + slot // 32
            try:
                tag = _read_location(stream, location)
                biomes = _snowy_biomes(tag, cx, cz)
                if biomes:
                    chunks.append({"chunk": [cx, cz], "biomes": biomes})
            except _Rejected:
                continue
        return chunks


def _read_chunk(path, rx, rz, cx, cz, size):
    slot = (cx - rx * 32) + (cz - rz * 32) * 32
    if not 0 <= slot < 1024:
        raise _Rejected()
    with path.open("rb") as stream:
        header = stream.read(4096)
        if len(header) != 4096:
            raise _Rejected()
        location = _locations(header, size)[slot]
        if location is None:
            raise _Rejected()
        return _read_location(stream, location)


def _locations(header, size):
    result = []
    used = set()
    for slot in range(1024):
        value = int.from_bytes(header[slot * 4:slot * 4 + 4], "big")
        offset, count = value >> 8, value & 255
        if offset == 0 and count == 0:
            result.append(None)
            continue
        if offset < 2 or count == 0 or (offset + count) * 4096 > size:
            result.append(None)
            continue
        allocation = set(range(offset, offset + count))
        if allocation & used:
            raise _Rejected()
        used.update(allocation)
        result.append((offset, count))
    return result


def _read_location(stream, location):
    offset, sectors = location
    stream.seek(offset * 4096)
    prefix = stream.read(5)
    if len(prefix) != 5:
        raise _Rejected()
    length = int.from_bytes(prefix[:4], "big")
    compression = prefix[4]
    if (compression & 0x80) or compression not in (1, 2, 3):
        raise _Rejected()
    if length < 2 or length > sectors * 4096 - 4 or length - 1 > 1024 * 1024:
        raise _Rejected()
    payload = stream.read(length - 1)
    if len(payload) != length - 1:
        raise _Rejected()
    raw = _decompress(payload, compression)
    return _NBTReader(raw).root()


def _decompress(payload, compression):
    if compression == 3:
        if len(payload) > MAX_NBT_BYTES:
            raise _Rejected()
        return payload
    window = 16 + zlib.MAX_WBITS if compression == 1 else zlib.MAX_WBITS
    try:
        decoder = zlib.decompressobj(window)
        raw = decoder.decompress(payload, MAX_NBT_BYTES + 1)
    except zlib.error:
        raise _Rejected() from None
    if (len(raw) > MAX_NBT_BYTES or not decoder.eof or decoder.unconsumed_tail
            or decoder.unused_data):
        raise _Rejected()
    return raw


def _snowy_biomes(tag, cx, cz):
    if not isinstance(tag, dict) or tag.get("Status") != "full":
        return []
    if tag.get("xPos") != cx or tag.get("zPos") != cz:
        return []
    sections = tag.get("sections")
    if not isinstance(sections, list):
        return []
    found = set()
    for section in sections:
        biomes = section.get("biomes") if isinstance(section, dict) else None
        palette = biomes.get("palette") if isinstance(biomes, dict) else None
        if isinstance(palette, list):
            found.update(name for name in palette
                         if type(name) is str and name in SNOW_BIOMES)
    return sorted(found)


class _NBTReader:
    def __init__(self, data):
        if not isinstance(data, bytes) or len(data) > MAX_NBT_BYTES:
            raise _Rejected()
        self.data = data
        self.pos = 0
        self.nodes = 0

    def root(self):
        kind = self._u8()
        if kind != 10:
            raise _Rejected()
        self._string()  # root name
        value = self._payload(10, 0)
        if self.pos != len(self.data):
            raise _Rejected()
        return value

    def _take(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise _Rejected()
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def _u8(self):
        return self._take(1)[0]

    def _number(self, fmt):
        return struct.unpack(fmt, self._take(struct.calcsize(fmt)))[0]

    def _string(self):
        size = self._number(">H")
        try:
            return self._take(size).decode("utf-8")
        except UnicodeDecodeError:
            raise _Rejected() from None

    def _node(self, count=1):
        self.nodes += count
        if self.nodes > MAX_NBT_NODES:
            raise _Rejected()

    def _length(self, width=1):
        count = self._number(">i")
        if count < 0 or count > MAX_NBT_COLLECTION or count * width > len(self.data) - self.pos:
            raise _Rejected()
        return count

    def _payload(self, kind, depth):
        self._node()
        if depth > 64:
            raise _Rejected()
        if kind == 1:
            return self._number(">b")
        if kind == 2:
            return self._number(">h")
        if kind == 3:
            return self._number(">i")
        if kind == 4:
            return self._number(">q")
        if kind == 5:
            return self._number(">f")
        if kind == 6:
            return self._number(">d")
        if kind == 7:
            return self._take(self._length())
        if kind == 8:
            return self._string()
        if kind == 9:
            child = self._u8()
            count = self._length()
            if child == 0 and count:
                raise _Rejected()
            return [self._payload(child, depth + 1) for _ in range(count)]
        if kind == 10:
            result = {}
            while True:
                child = self._u8()
                if child == 0:
                    return result
                if child > 12:
                    raise _Rejected()
                name = self._string()
                if name in result:
                    raise _Rejected()
                result[name] = self._payload(child, depth + 1)
        if kind == 11:
            count = self._length(4)
            self._node(count)
            return list(struct.unpack(f">{count}i", self._take(count * 4))) if count else []
        if kind == 12:
            count = self._length(8)
            self._node(count)
            return list(struct.unpack(f">{count}q", self._take(count * 8))) if count else []
        raise _Rejected()


def _index_key(server, dimension, cache_folder, region_file):
    return f"{server}\x00{dimension}\x00{cache_folder}\x00{region_file}"


def _cached_region(value, server, dimension, cache_folder, name, stat):
    return (isinstance(value, dict)
            and value.get("server") == server
            and value.get("dimension") == dimension
            and value.get("cache_folder") == cache_folder
            and value.get("region_file") == name
            and value.get("mtime_ns") == stat.st_mtime_ns
            and value.get("ctime_ns") == stat.st_ctime_ns
            and value.get("size") == stat.st_size
            and value.get("file_id") == _file_id(stat)
            and isinstance(value.get("fingerprint"),str)
            and FINGERPRINT.fullmatch(value["fingerprint"])
            and isinstance(value.get("chunks"), list)
            and len(value["chunks"]) <= MAX_INDEX_CHUNKS
            and all(_valid_index_chunk(chunk) for chunk in value["chunks"]))


def _valid_index_chunk(value):
    return (isinstance(value, dict) and set(value) == {"chunk", "biomes"}
            and isinstance(value.get("chunk"), list) and len(value["chunk"]) == 2
            and all(type(part) is int for part in value["chunk"])
            and isinstance(value.get("biomes"), list) and bool(value["biomes"])
            and value["biomes"] == sorted(set(value["biomes"]))
            and all(type(name) is str and name in SNOW_BIOMES
                    for name in value["biomes"]))


def _load_index(path):
    empty = {"version": INDEX_VERSION, "entries": {}}
    try:
        if path.is_symlink() or not path.is_file():
            return empty
        if path.stat().st_size > MAX_INDEX_BYTES:
            return empty
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or set(value) != {"version", "entries"}
                or value.get("version") != INDEX_VERSION
                or not isinstance(value.get("entries"), dict)
                or len(value["entries"]) > MAX_INDEX_ENTRIES):
            return empty
        for key, row in value["entries"].items():
            if (not isinstance(key, str) or not isinstance(row, dict)
                    or set(row) != {"server", "dimension", "cache_folder", "region_file",
                                        "mtime_ns", "ctime_ns", "size", "file_id", "fingerprint",
                                        "chunks"}
                    or not isinstance(row.get("server"), str)
                    or not isinstance(row.get("dimension"), str)
                    or not isinstance(row.get("cache_folder"), str)
                    or not re.fullmatch(r"[a-z0-9._\[\]-]+", row["cache_folder"])
                    or _region_coordinates(row.get("region_file")) is None
                    or type(row.get("mtime_ns")) is not int or row["mtime_ns"] < 0
                    or type(row.get("ctime_ns")) is not int or row["ctime_ns"] < 0
                    or type(row.get("size")) is not int or not 8192 <= row["size"] <= MAX_REGION_BYTES
                    or type(row.get("file_id")) is not int
                    or not 0 <= row["file_id"] <= MAX_SAFE_INTEGER
                    or not isinstance(row.get("fingerprint"), str)
                    or not FINGERPRINT.fullmatch(row["fingerprint"])
                    or not isinstance(row.get("chunks"), list)
                    or len(row["chunks"]) > MAX_INDEX_CHUNKS
                    or any(not _valid_index_chunk(chunk) for chunk in row["chunks"])
                    or key != _index_key(row["server"], row["dimension"],
                                         row["cache_folder"], row["region_file"])):
                return empty
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return empty


def _save_index(path, value):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"),
                             sort_keys=True).encode("utf-8")
        if len(encoded) > MAX_INDEX_BYTES:
            return
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
