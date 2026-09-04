package dev.twob2tkit.structure;

import net.minecraft.util.RandomSource;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.WorldgenRandom;

import java.util.ArrayList;
import java.util.List;

/**
 * 按原版 {@code EndCityPieces} / cubiomes 生成部件，判断末地城有没有船。
 * 不读结构模板，碰撞盒用原版模板尺寸。
 */
public final class EndCityLayout {
	private final RandomSource random;
	private boolean ship;
	private int houseY;

	private EndCityLayout(RandomSource random) {
		this.random = random;
	}

	/** 按原版部件生成判断该末地城区块是否有船。 */
	public static boolean hasShip(long seed, int chunkX, int chunkZ) {
		WorldgenRandom random = new WorldgenRandom(new LegacyRandomSource(0L));
		random.setLargeFeatureSeed(seed, chunkX, chunkZ);
		int rot = random.nextInt(4);
		EndCityLayout layout = new EndCityLayout(random);
		List<Piece> pieces = new ArrayList<>();
		int x = (chunkX << 4) + 8;
		int z = (chunkZ << 4) + 8;
		Piece base = layout.add(pieces, null, rot, x, 0, z, Type.BASE_FLOOR);
		base = layout.add(pieces, base, rot, -1, 0, -1, Type.SECOND_FLOOR_1);
		base = layout.add(pieces, base, rot, -1, 4, -1, Type.THIRD_FLOOR_1);
		base = layout.add(pieces, base, rot, -1, 8, -1, Type.THIRD_ROOF);
		layout.recurse(pieces, layout::genTower, base, 1);
		return layout.ship;
	}

	/** 递归生成子部件；碰撞冲突则失败。 */
	private boolean recurse(List<Piece> dest, Gen gen, Piece current, int depth) {
		if (depth > 8) return false;
		List<Piece> local = new ArrayList<>();
		if (!gen.run(local, current, depth)) return false;
		int tag = this.random.nextInt();
		for (Piece child : local) {
			child.depth = tag;
			for (Piece existing : dest) {
				if (overlaps(child, existing) && current.depth != existing.depth) return false;
			}
		}
		dest.addAll(local);
		return true;
	}

	/** 生成塔楼及可能的桥。 */
	private boolean genTower(List<Piece> dest, Piece current, int depth) {
		int rot = current.rot;
		Piece base = current;
		base = add(dest, base, rot, 3 + this.random.nextInt(2), -3, 3 + this.random.nextInt(2), Type.TOWER_BASE);
		base = add(dest, base, rot, 0, 7, 0, Type.TOWER_PIECE);
		Piece floor = this.random.nextInt(3) == 0 ? base : null;
		int floors = 1 + this.random.nextInt(3);
		for (int i = 0; i < floors; i++) {
			base = add(dest, base, rot, 0, 4, 0, Type.TOWER_PIECE);
			if (i < floors - 1 && this.random.nextBoolean()) floor = base;
		}
		if (floor != null) {
			int[][] bridges = {
				{0, 1, -1, 0},
				{1, 6, -1, 1},
				{3, 0, -1, 5},
				{2, 5, -1, 6}
			};
			for (int[] bridge : bridges) {
				if (!this.random.nextBoolean()) continue;
				int brot = (rot + bridge[0]) & 3;
				Piece start = add(dest, floor, brot, bridge[1], bridge[2], bridge[3], Type.BRIDGE_END);
				recurse(dest, this::genBridge, start, depth + 1);
			}
		} else if (depth != 7) {
			return recurse(dest, this::genFatTower, base, depth + 1);
		}
		add(dest, base, rot, -1, 4, -1, Type.TOWER_TOP);
		return true;
	}

	/** 生成桥；可能挂船或房屋塔。 */
	private boolean genBridge(List<Piece> dest, Piece current, int depth) {
		int rot = current.rot;
		int length = 1 + this.random.nextInt(4);
		Piece base = add(dest, current, rot, 0, 0, -4, Type.BRIDGE_PIECE);
		base.depth = -1;
		int y = 0;
		for (int i = 0; i < length; i++) {
			if (this.random.nextBoolean()) {
				base = add(dest, base, rot, 0, y, -4, Type.BRIDGE_PIECE);
				y = 0;
			} else {
				if (this.random.nextBoolean()) {
					base = add(dest, base, rot, 0, y, -4, Type.BRIDGE_STEEP);
				} else {
					base = add(dest, base, rot, 0, y, -8, Type.BRIDGE_GENTLE);
				}
				y = 4;
			}
		}
		if (!this.ship && this.random.nextInt(10 - depth) == 0) {
			add(dest, base, rot, -8 + this.random.nextInt(8), y, -70 + this.random.nextInt(10), Type.SHIP);
			this.ship = true;
		} else {
			this.houseY = y + 1;
			if (!recurse(dest, this::genHouseTower, base, depth + 1)) return false;
		}
		base = add(dest, base, (rot + 2) & 3, 4, y, 0, Type.BRIDGE_END);
		base.depth = -1;
		return true;
	}

	/** 桥端房屋塔。 */
	private boolean genHouseTower(List<Piece> dest, Piece current, int depth) {
		if (depth > 8) return false;
		int rot = current.rot;
		Piece base = add(dest, current, rot, -3, this.houseY, -11, Type.BASE_FLOOR);
		int size = this.random.nextInt(3);
		if (size == 0) {
			add(dest, base, rot, -1, 4, -1, Type.BASE_ROOF);
			return true;
		}
		base = add(dest, base, rot, -1, 0, -1, Type.SECOND_FLOOR_2);
		if (size == 1) {
			base = add(dest, base, rot, -1, 8, -1, Type.SECOND_ROOF);
		} else {
			base = add(dest, base, rot, -1, 4, -1, Type.THIRD_FLOOR_2);
			base = add(dest, base, rot, -1, 8, -1, Type.THIRD_ROOF);
		}
		recurse(dest, this::genTower, base, depth + 1);
		return true;
	}

	/** 粗塔变体。 */
	private boolean genFatTower(List<Piece> dest, Piece current, int depth) {
		int rot = current.rot;
		Piece base = add(dest, current, rot, -3, 4, -3, Type.FAT_BASE);
		base = add(dest, base, rot, 0, 4, 0, Type.FAT_MIDDLE);
		int[][] bridges = {
			{0, 4, -1, 0},
			{1, 12, -1, 4},
			{3, 0, -1, 8},
			{2, 8, -1, 12}
		};
		for (int extra = 0; extra < 2 && this.random.nextInt(3) != 0; extra++) {
			base = add(dest, base, rot, 0, 8, 0, Type.FAT_MIDDLE);
			for (int[] bridge : bridges) {
				if (!this.random.nextBoolean()) continue;
				int brot = (rot + bridge[0]) & 3;
				Piece start = add(dest, base, brot, bridge[1], bridge[2], bridge[3], Type.BRIDGE_END);
				recurse(dest, this::genBridge, start, depth + 1);
			}
		}
		add(dest, base, rot, -2, 8, -2, Type.FAT_TOP);
		return true;
	}

	/** 按相对偏移追加一个部件。 */
	private Piece add(List<Piece> dest, Piece prev, int rot, int px, int py, int pz, Type type) {
		Piece piece = new Piece(prev, rot, px, py, pz, type);
		dest.add(piece);
		return piece;
	}

	/** 两部件碰撞盒是否相交。 */
	private static boolean overlaps(Piece a, Piece b) {
		return a.x1 >= b.x0 && b.x1 >= a.x0 && a.z1 >= b.z0 && b.z1 >= a.z0 && a.y1 >= b.y0 && b.y1 >= a.y0;
	}

	/** 生成一步子部件的回调。 */
	@FunctionalInterface
	private interface Gen {
		boolean run(List<Piece> dest, Piece current, int depth);
	}

	/** 末地城模板部件类型与尺寸。 */
	private enum Type {
		BASE_FLOOR(9, 3, 9),
		BASE_ROOF(11, 1, 11),
		BRIDGE_END(4, 5, 1),
		BRIDGE_GENTLE(4, 6, 7),
		BRIDGE_PIECE(4, 5, 3),
		BRIDGE_STEEP(4, 6, 3),
		FAT_BASE(12, 3, 12),
		FAT_MIDDLE(12, 7, 12),
		FAT_TOP(16, 5, 16),
		SECOND_FLOOR_1(11, 7, 11),
		SECOND_FLOOR_2(11, 7, 11),
		SECOND_ROOF(13, 1, 13),
		SHIP(12, 23, 28),
		THIRD_FLOOR_1(13, 7, 13),
		THIRD_FLOOR_2(13, 7, 13),
		THIRD_ROOF(15, 1, 15),
		TOWER_BASE(6, 6, 6),
		TOWER_PIECE(6, 3, 6),
		TOWER_TOP(8, 4, 8);

		final int sx;
		final int sy;
		final int sz;

		Type(int sx, int sy, int sz) {
			this.sx = sx;
			this.sy = sy;
			this.sz = sz;
		}
	}

	/** 已放置部件：旋转、深度与碰撞盒。 */
	private static final class Piece {
		final int rot;
		int depth;
		int x0;
		int y0;
		int z0;
		int x1;
		int y1;
		int z1;
		int px;
		int py;
		int pz;

		Piece(Piece prev, int rot, int ox, int oy, int oz, Type type) {
			this.rot = rot;
			int x = ox;
			int y = oy;
			int z = oz;
			if (prev != null) {
				x = prev.px;
				y = prev.py;
				z = prev.pz;
				switch (prev.rot) {
					case 0 -> {
						x += ox;
						z += oz;
					}
					case 1 -> {
						x -= oz;
						z += ox;
					}
					case 2 -> {
						x -= ox;
						z -= oz;
					}
					default -> {
						x += oz;
						z -= ox;
					}
				}
				y += oy;
			}
			this.px = x;
			this.py = y;
			this.pz = z;
			this.x0 = x;
			this.y0 = y;
			this.z0 = z;
			this.x1 = x;
			this.y1 = y + type.sy;
			this.z1 = z;
			switch (rot) {
				case 0 -> {
					this.x1 += type.sx;
					this.z1 += type.sz;
				}
				case 1 -> {
					this.x0 -= type.sz;
					this.z1 += type.sx;
				}
				case 2 -> {
					this.x0 -= type.sx;
					this.z0 -= type.sz;
				}
				default -> {
					this.x1 += type.sz;
					this.z0 -= type.sx;
				}
			}
		}
	}
}
