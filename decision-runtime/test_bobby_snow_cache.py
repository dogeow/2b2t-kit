import gzip
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from material_jobs import bobby_snow_cache as cache


HASH = -1234567890123456789
WORLD_FOLDER = str(HASH)


def named(kind, name, payload):
    encoded = name.encode()
    return bytes([kind]) + struct.pack(">H", len(encoded)) + encoded + payload


def string(value):
    value = value.encode()
    return struct.pack(">H", len(value)) + value


def compound(values):
    return b"".join(values) + b"\0"


def chunk_nbt(cx, cz, biome="minecraft:snowy_plains", status="full"):
    palette = bytes([8]) + struct.pack(">i", 1) + string(biome)
    biomes = compound([named(9, "palette", palette)])
    section = compound([named(10, "biomes", biomes)])
    sections = bytes([10]) + struct.pack(">i", 1) + section
    root = compound([
        named(8, "Status", string(status)),
        named(3, "xPos", struct.pack(">i", cx)),
        named(3, "zPos", struct.pack(">i", cz)),
        named(9, "sections", sections),
    ])
    return bytes([10, 0, 0]) + root


def region(path, chunks):
    """chunks: (cx, cz, compression, nbt-or-payload, raw_payload=False)."""
    locations = bytearray(4096)
    body = bytearray(4096)  # timestamp sector
    sector = 2
    for cx, cz, compression, value, raw_payload in chunks:
        if raw_payload:
            payload = value
        elif compression == 1:
            payload = gzip.compress(value)
        elif compression == 2:
            payload = zlib.compress(value)
        else:
            payload = value
        record = struct.pack(">I", len(payload) + 1) + bytes([compression]) + payload
        sectors = (len(record) + 4095) // 4096
        slot = (cx & 31) + (cz & 31) * 32
        locations[slot * 4:slot * 4 + 4] = ((sector << 8) | sectors).to_bytes(4, "big")
        body.extend(record)
        body.extend(b"\0" * (sectors * 4096 - len(record)))
        sector += sectors
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(locations) + bytes(body))
    return path


class BobbySnowCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        scout = self.root / "config/twob2tkit/seed-scout.json"
        scout.parent.mkdir(parents=True)
        scout.write_text(json.dumps({"hasHashedSeed": True, "hashedSeed": HASH}))

    def tearDown(self):
        self.temp.cleanup()

    def world(self, server="example.test_25565", world=WORLD_FOLDER,
              dimension="minecraft/overworld"):
        path = self.root / ".bobby" / server / world / dimension
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_gzip_zlib_and_uncompressed_full_snowy_chunks_are_read(self):
        folder = self.world()
        region(folder / "r.0.0.mca", [
            (0, 0, 1, chunk_nbt(0, 0), False),
            (1, 0, 2, chunk_nbt(1, 0, "minecraft:grove"), False),
            (2, 0, 3, chunk_nbt(2, 0, "minecraft:snowy_taiga"), False),
        ])
        rows = cache.candidates(self.root, "example.test:25565",
                                "minecraft:overworld", [0, 70, 0])
        self.assertEqual([[0, 0], [1, 0], [2, 0]], [row["chunk"] for row in rows])
        for row in rows:
            self.assertTrue(cache.validate_candidate(
                self.root, "example.test", "minecraft:overworld", row))
            self.assertEqual("example.test", row["cache_server"])
            self.assertEqual(f"r.0.0.mca", row["region_file"])
            self.assertRegex(row["fingerprint"], r"^[0-9a-f]{64}$")
            self.assertTrue(row["biomes"])

    def test_only_full_explicit_snow_palette_and_matching_slot_coordinates_are_accepted(self):
        folder = self.world()
        region(folder / "r.-1.0.mca", [
            (-32, 0, 2, chunk_nbt(-32, 0, status="carvers"), False),
            (-31, 0, 2, chunk_nbt(-31, 0, "minecraft:desert"), False),
            (-30, 0, 2, chunk_nbt(77, 0), False),
            (-29, 0, 2, chunk_nbt(-29, 0, "minecraft:snowy_slopes"), False),
        ])
        rows = cache.candidates(self.root, "example.test", "minecraft:overworld", [0, 0])
        self.assertEqual([[-29, 0]], [row["chunk"] for row in rows])

    def test_external_unsupported_corrupt_and_overlong_chunks_are_rejected(self):
        folder = self.world()
        valid = chunk_nbt(4, 0)
        path = region(folder / "r.0.0.mca", [
            (0, 0, 0x82, zlib.compress(chunk_nbt(0, 0)), True),
            (1, 0, 4, b"unsupported", True),
            (2, 0, 2, b"not-zlib", True),
            (3, 0, 3, b"\x0a\x00", True),
            (4, 0, 2, valid, False),
        ])
        with patch.object(cache, "MAX_NBT_BYTES", 32):
            self.assertEqual([], cache.candidates(
                self.root, "example.test", "minecraft:overworld", [0, 0]))
        (self.root / "config/twob2tkit/bobby-snow-index.json").unlink()
        rows = cache.candidates(self.root, "example.test", "minecraft:overworld", [0, 0])
        self.assertEqual([[4, 0]], [row["chunk"] for row in rows])
        data = bytearray(path.read_bytes())
        data[4 * 4:4 * 4 + 4] = ((2 << 8) | 1).to_bytes(4, "big")
        path.write_bytes(data)
        self.assertEqual([], cache.candidates(
            self.root, "example.test", "minecraft:overworld", [0, 0]))

    def test_current_hash_selects_one_world_and_never_escapes_output_or_index(self):
        current = self.world()
        wrong = self.world(world=str(HASH + 1))
        region(current / "r.0.0.mca", [(4, 0, 3, chunk_nbt(4, 0), False)])
        region(wrong / "r.0.0.mca", [(0, 0, 3, chunk_nbt(0, 0), False)])
        rows = cache.candidates(self.root, "example.test:25565",
                                "minecraft:overworld", [0, 0])
        self.assertEqual([[4, 0]], [row["chunk"] for row in rows])
        self.assertTrue({"source", "cache_server", "dimension", "chunk", "tile",
                         "target", "region_file", "fingerprint", "biomes",
                         "mtime_ns", "ctime_ns", "size", "file_id"}.issubset(rows[0]))
        public = json.dumps(rows, sort_keys=True)
        stored = (self.root / "config/twob2tkit/bobby-snow-index.json").read_text()
        self.assertNotIn(str(HASH), public + stored)
        self.assertNotIn(WORLD_FOLDER, public + stored)

    def test_exact_colon_folder_wins_and_default_port_alias_is_supported(self):
        exact = self.world()
        alias = self.world(server="example.test")
        region(exact / "r.0.0.mca", [
            (2, 0, 3, chunk_nbt(2, 0, "minecraft:desert"), False),
        ])
        region(alias / "r.0.0.mca", [(1, 0, 3, chunk_nbt(1, 0), False)])
        rows = cache.candidates(self.root, "example.test:25565",
                                "minecraft:overworld", [0, 0])
        self.assertEqual([[1, 0]], [row["chunk"] for row in rows])
        rows = cache.candidates(self.root, "example.test",
                                "minecraft:overworld", [0, 0])
        self.assertEqual([[1, 0]], [row["chunk"] for row in rows])
        default_alias = self.world(server="alias.test_25565")
        region(default_alias / "r.0.0.mca", [(3, 0, 3, chunk_nbt(3, 0), False)])
        rows = cache.candidates(self.root, "alias.test",
                                "minecraft:overworld", [0, 0])
        self.assertEqual([[3, 0]], [row["chunk"] for row in rows])

    def test_index_caches_metadata_content_fingerprint_and_chunks(self):
        folder = self.world()
        path = region(folder / "r.0.0.mca", [(0, 0, 3, chunk_nbt(0, 0), False)])
        first = cache.candidates(self.root, "example.test", "minecraft:overworld", [0, 0])
        index_path = self.root / "config/twob2tkit/bobby-snow-index.json"
        index = json.loads(index_path.read_text())
        entry = next(iter(index["entries"].values()))
        self.assertEqual({"server", "dimension", "cache_folder", "region_file",
                          "mtime_ns", "ctime_ns", "size", "file_id", "fingerprint", "chunks"},
                         set(entry))
        self.assertLessEqual(entry["file_id"], (1 << 53) - 1)
        with patch.object(cache, "_scan_region", side_effect=AssertionError("reparsed")), \
             patch.object(cache,"_content_fingerprint",side_effect=AssertionError("rehashed")):
            self.assertEqual(first, cache.candidates(
                self.root, "example.test", "minecraft:overworld", [0, 0]))
        before = path.stat()
        old = first[0]
        original = path.read_bytes()
        replaced = original.replace(b"minecraft:snowy_plains", b"minecraft:frozen_peaks")
        self.assertEqual(len(original), len(replaced))
        path.write_bytes(replaced)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        second = cache.candidates(self.root, "example.test", "minecraft:overworld", [0, 0])
        self.assertEqual(1, len(second))
        self.assertNotEqual(old["fingerprint"], second[0]["fingerprint"])
        self.assertFalse(cache.validate_candidate(
            self.root, "example.test", "minecraft:overworld", old))
        self.assertTrue(cache.validate_candidate(
            self.root, "example.test", "minecraft:overworld", second[0]))
        with patch.object(cache, "_content_fingerprint",
                          side_effect=AssertionError("quick validation hashed MCA")):
            self.assertTrue(cache.validate_candidate(
                self.root, "example.test", "minecraft:overworld", second[0], quick=True))
        altered = dict(second[0], target=[999.5, 200.0, 8.5])
        self.assertFalse(cache.validate_candidate(
            self.root, "example.test", "minecraft:overworld", altered))

    def test_per_leg_world_identity_tolerates_bobby_extending_same_region(self):
        folder=self.world();path=region(
            folder/'r.0.0.mca',[(0,0,3,chunk_nbt(0,0),False)])
        row=cache.candidates(self.root,'example.test','minecraft:overworld',[0,0])[0]
        self.assertTrue(cache.validate_candidate(
            self.root,'example.test','minecraft:overworld',row))
        with path.open('ab') as stream:stream.write(b'\0'*4096)
        self.assertFalse(cache.validate_candidate(
            self.root,'example.test','minecraft:overworld',row,quick=True))
        self.assertTrue(cache.validate_current_world(
            self.root,'example.test','minecraft:overworld',row))
        (self.root/'config/twob2tkit/seed-scout.json').write_text(json.dumps({
            'hasHashedSeed':True,'hashedSeed':HASH+1}))
        self.assertFalse(cache.validate_current_world(
            self.root,'example.test','minecraft:overworld',row))

    def test_unvisited_then_origin_distance_order_and_world_border(self):
        folder = self.world()
        region(folder / "r.0.0.mca", [
            (0, 0, 3, chunk_nbt(0, 0), False),
            (2, 0, 3, chunk_nbt(2, 0), False),
            (4, 0, 3, chunk_nbt(4, 0), False),
        ])
        outside = 1_874_999
        rx = outside // 32
        region(folder / f"r.{rx}.0.mca", [
            (outside, 0, 3, chunk_nbt(outside, 0), False),
        ])
        rows = cache.candidates(self.root, "example.test", "minecraft:overworld",
                                [8.5, 70, 8.5], visited=[(0, 0)])
        self.assertEqual([[2, 0], [4, 0], [0, 0]], [row["chunk"] for row in rows])
        self.assertEqual([32, 0], rows[0]["tile"])
        self.assertEqual([40.5, 200.0, 8.5], rows[0]["target"])

    def test_unavailable_errors_are_sanitized(self):
        secret = WORLD_FOLDER
        with self.assertRaises(cache.CacheUnavailable) as caught:
            cache.candidates(self.root, "missing.test", "minecraft:overworld", [0, 0])
        self.assertNotIn(secret, str(caught.exception))
        (self.root / "config/twob2tkit/seed-scout.json").write_text("broken")
        with self.assertRaises(cache.CacheUnavailable) as caught:
            cache.candidates(self.root, "example.test", "minecraft:overworld", [0, 0])
        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
