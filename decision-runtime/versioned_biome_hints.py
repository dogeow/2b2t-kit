"""Offline versioned seed calibration and bounded hints; never drives the game.

Cubiomes exposes 1.19.2 and 1.19.4 compatibility tables rather than a separate
1.19.3 selector. Require both tables to match live samples and agree on hints.
The caller supplies the compiled kit_seed_biomes adapter, which accepts a full
decimal seed, a table version, and block XYZ lines on stdin.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess

TABLES = {"1.19.3": ("1.19.2", "1.19.4")}


def seed_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
        raise ValueError("Keep the full seed as a decimal string")
    number = int(value)
    if not -(1 << 63) <= number < (1 << 63):
        raise ValueError("Seed must fit a Java long")
    return number


def seed_hash(value):
    raw = hashlib.sha256(struct.pack("<q", seed_value(value))).digest()
    return struct.unpack("<q", raw[:8])[0]


def predict(executable, seed, table, points):
    # Cubiomes internally takes the same 64 bits as an unsigned integer.
    unsigned = str(seed_value(seed) & ((1 << 64) - 1))
    data = "".join("%d %d %d\n" % tuple(p) for p in points)
    result = subprocess.run([str(executable), unsigned, table], input=data,
                            text=True, capture_output=True, check=True, timeout=120)
    lines = result.stdout.splitlines()
    if len(lines) != len(points):
        raise ValueError("Generator omitted or added positions")
    biomes = []
    for point, line in zip(points, lines):
        fields = line.split()
        if (len(fields) != 5 or list(map(int, fields[:3])) != point
                or not re.fullmatch(r"[a-z_]+", fields[4]) or fields[4] == "unknown"):
            raise ValueError("Generator response position or biome is invalid")
        biomes.append("minecraft:" + fields[4])
    return biomes


def calibrate(seed, version, survey, login, executable, *, predictor=predict):
    tables = TABLES.get(version)
    seed_value(seed)
    if tables is None:
        raise ValueError("Unsupported generation version; do not substitute the client version")
    if (not survey.get("id") or not survey.get("world_session")
            or survey.get("phase") not in (None, "done")):
        raise ValueError("A scoped successful native survey is required")
    counts = survey.get("snow_biome_survey") or {}
    samples = counts.get("samples")
    if (not isinstance(samples, list) or not 5 <= len(samples) <= 169
            or any(type(counts.get(k)) is not int for k in
                   ("loaded_samples", "unloaded_samples", "requested_samples"))
            or counts.get("loaded_samples") != len(samples)
            or type(counts.get("unloaded_samples")) is not int
            or counts["unloaded_samples"] < 0
            or counts.get("requested_samples") != len(samples) + counts["unloaded_samples"]):
        raise ValueError("Native survey counts are inconsistent")
    points, actual, seen = [], [], set()
    for sample in samples:
        point = sample.get("pos")
        biome = sample.get("biome")
        if (not isinstance(point, list) or len(point) != 3
                or any(type(n) is not int for n in point)
                or not -64 <= point[1] <= 319
                or any(abs(point[i]) > 30_000_000 for i in (0, 2))
                or tuple(point) in seen
                or not isinstance(biome, str) or not re.fullmatch(r"minecraft:[a-z_]+", biome)):
            raise ValueError("Native sample identity or coordinates are invalid")
        seen.add(tuple(point)); points.append(point); actual.append(biome)
    hash_matches = (login.get("hasHashedSeed") is True
                    and type(login.get("hashedSeed")) is int
                    and seed_hash(seed) == login["hashedSeed"])
    models = {}
    for table in tables:
        predicted = predictor(executable, seed, table, points)
        if len(predicted) != len(actual):
            raise ValueError("Generator sample count mismatch")
        models[table] = {"matched": sum(a == b for a, b in zip(actual, predicted)),
                         "samples": [{"pos": p, "actual": a, "predicted": b}
                                     for p, a, b in zip(points, actual, predicted)]}
    land = {b for b in actual if "ocean" not in b and "river" not in b}
    allowed = hash_matches and len(land) >= 2 and all(v["matched"] == len(actual) for v in models.values())
    return {"schema": 1, "seed": seed, "generation_version": version,
            "world_session": survey["world_session"], "survey_request_id": survey["id"],
            "sample_count": len(actual), "models": models, "login_hash_matches": hash_matches,
            "hint_use_allowed": allowed, "hint_only": True, "inventory_credit": 0}


def search(calibration, origin, radius, stride, wanted, limit, executable, *, predictor=predict):
    seed, version = calibration.get("seed"), calibration.get("generation_version")
    tables = TABLES.get(version)
    models = calibration.get("models") or {}
    if (tables is None or calibration.get("hint_use_allowed") is not True
            or calibration.get("login_hash_matches") is not True
            or type(calibration.get("sample_count")) is not int or not 5 <= calibration["sample_count"] <= 169
            or set(models) != set(tables)
            or any(v.get("matched") != calibration["sample_count"] for v in models.values())):
        raise ValueError("Use only a fully calibrated seed; no travel hints emitted")
    if (not isinstance(origin, list) or len(origin) != 2 or any(type(n) is not int for n in origin)
            or type(radius) is not int or not 64 <= radius <= 16384
            or type(stride) is not int or not 32 <= stride <= 256
            or type(limit) is not int or not 64 <= limit <= 30_000_000
            or not wanted or any(not isinstance(b, str) or not re.fullmatch(r"minecraft:[a-z_]+", b) for b in wanted)
            or any(abs(n) >= limit - 32 for n in origin)):
        raise ValueError("Search needs bounded coordinates and explicit vanilla biomes")
    points = [[origin[0] + dx, 100, origin[1] + dz]
              for dx in range(-radius, radius + 1, stride)
              for dz in range(-radius, radius + 1, stride)
              if dx * dx + dz * dz <= radius * radius
              and abs(origin[0] + dx) < limit - 32 and abs(origin[1] + dz) < limit - 32]
    if len(points) > 250000:
        raise ValueError("Search exceeds the bounded offline sample budget")
    predictions = [predictor(executable, seed, table, points) for table in tables]
    if any(len(rows) != len(points) for rows in predictions):
        raise ValueError("Generator search count mismatch")
    candidates = [{"pos": p, "biome": a, "distance": round(math.hypot(p[0]-origin[0], p[2]-origin[1]), 1)}
                  for p, a, b in zip(points, *predictions) if a == b and a in wanted]
    candidates.sort(key=lambda c: c["distance"])
    selected = []
    for candidate in candidates:
        if all(math.hypot(candidate["pos"][0]-v["pos"][0], candidate["pos"][2]-v["pos"][2]) >= 256 for v in selected):
            selected.append(candidate)
        if len(selected) == 16:
            break
    return {"schema": 1, "seed": seed, "generation_version": version,
            "world_session": calibration["world_session"], "origin": origin,
            "radius": radius, "stride": stride, "coordinate_limit": limit, "margin": 32,
            "compatibility_tables": list(tables), "sample_count": len(points),
            "candidates": selected, "hint_only": True, "actual_blocks_required": True,
            "inventory_credit": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("calibrate", "search"))
    parser.add_argument("--generator", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed"); parser.add_argument("--version", default="1.19.3")
    parser.add_argument("--survey", type=Path); parser.add_argument("--login", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--origin", nargs=2, type=int)
    parser.add_argument("--radius", type=int, default=8192)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--limit", type=int, default=800000)
    parser.add_argument("--biomes", default="minecraft:desert,minecraft:badlands,minecraft:wooded_badlands,minecraft:eroded_badlands")
    args = parser.parse_args()
    if args.mode == "calibrate":
        result = calibrate(args.seed, args.version, json.loads(args.survey.read_text()),
                           json.loads(args.login.read_text()), args.generator)
    else:
        result = search(json.loads(args.calibration.read_text()), args.origin, args.radius,
                        args.stride, set(args.biomes.split(",")), args.limit, args.generator)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("sample_count", "hint_only", "inventory_credit")}))


if __name__ == "__main__":
    main()
