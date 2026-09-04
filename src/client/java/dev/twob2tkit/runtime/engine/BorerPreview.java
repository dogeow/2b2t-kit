package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.gizmos.TextGizmo;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** 竖井/区域预览与运行中全息框。回家箭头仍由引擎在帧回调里画。 */
final class BorerPreview {
	private final DefaultTunnelBorerEngine engine;

	BorerPreview(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 开始竖井预览。 */
	void beginShaft(Minecraft client) {
		if (client.player == null || client.level == null) return;
		engine.mode = DefaultTunnelBorerEngine.Mode.DOWN;
		engine.forward = engine.headingFromConfig(client.player);
		engine.keepPreviewHeading = false;
		engine.showingShaftPreview = true;
		engine.status = "预览竖井，再按 B 开始挖";
		DefaultTunnelBorerEngine.message(client, "预览 " + engine.effectiveWidth() + "×" + engine.effectiveHeight()
			+ " 竖井：黄框当前层，橙框下一层，白框是脚下原点。朝"
			+ BorerText.direction(engine.forward) + "已锁定，转身不改范围。走动仍对齐脚下。再按 B 开挖，End 取消。");
	}

	/** 开始区域预览。 */
	void beginArea(Minecraft client) {
		if (client.player == null || client.level == null) return;
		if (!engine.prepareArea(client)) return;
		engine.mode = DefaultTunnelBorerEngine.Mode.AREA;
		engine.showingAreaPreview = true;
		engine.status = "预览区域，再按 B 开始挖";
		DefaultTunnelBorerEngine.message(client, "预览区域 " + BorerAreaPolicy.sizeLabel(
			engine.areaMin.getX(), engine.areaMax.getY(), engine.areaMin.getZ(),
			engine.areaMax.getX(), engine.areaMin.getY(), engine.areaMax.getZ())
			+ "。黄框是整块范围。再按 B 开挖，End 取消。");
	}

	/** 竖井若需要时。 */
	void presentShaftIfNeeded(Minecraft client) {
		if (!engine.showingShaftPreview || engine.active || client.player == null || client.level == null) return;
		engine.mode = DefaultTunnelBorerEngine.Mode.DOWN;
		engine.forward = BorerShaftPolicy.headingForPreview(engine.forward, engine.headingFromConfig(client.player));
		try {
			emitShaft(client, client.player.blockPosition());
		} catch (IllegalStateException ignored) {
		}
	}

	/** 竖井原点相对提示。 */
	String shaftHint() {
		if (engine.forward == null) return "";
		Direction right = engine.forward.getClockWise();
		return BorerShaftPolicy.originHint(
			engine.effectiveWidth(), engine.effectiveHeight(),
			BorerText.direction(right.getOpposite()), BorerText.direction(right),
			BorerText.direction(engine.forward.getOpposite()), BorerText.direction(engine.forward))
			+ "  朝" + BorerText.direction(engine.forward) + "已锁定";
	}

	/** 区域若需要时。 */
	void presentAreaIfNeeded(Minecraft client) {
		if (engine.active || client.player == null || client.level == null) return;
		if (engine.showingShaftPreview) return;
		if (!engine.host.borerAreaSet()) {
			engine.dismissAreaPreview();
			return;
		}
		if (!engine.showingAreaPreview && !"AREA".equals(engine.host.borerLastMode())) return;
		ensureAreaBoundsLoaded();
	}

	/** 每帧 gizmo 收集里画区域黄框和标题，钉在世界坐标，不跟镜头。 */
	void emitAreaPreviewGizmosIfNeeded(Minecraft client) {
		if (client.player == null || client.level == null) return;
		if (engine.showingShaftPreview || engine.goingHome) return;
		if (engine.active) {
			if (engine.mode != DefaultTunnelBorerEngine.Mode.AREA) return;
			if (engine.areaMin == null || engine.areaMax == null) return;
			try {
				emitArea();
			} catch (IllegalStateException ignored) {
			}
			return;
		}
		if (!engine.host.borerAreaSet()) return;
		if (!engine.showingAreaPreview && !"AREA".equals(engine.host.borerLastMode())) return;
		ensureAreaBoundsLoaded();
		if (engine.areaMin == null || engine.areaMax == null) return;
		try {
			emitArea();
		} catch (IllegalStateException ignored) {
		}
	}

	/** 确保区域预览边界已从配置加载。 */
	private void ensureAreaBoundsLoaded() {
		if (engine.showingAreaPreview && engine.areaMin != null && engine.areaMax != null) return;
		engine.loadAreaFromHost();
	}

	/** 画出运行中的活动预览。 */
	void emitActive(Minecraft client) {
		if (engine.currentTarget != null && !engine.goingHome) {
			BorerGizmos.hold(Gizmos.cuboid(engine.currentTarget, GizmoStyle.strokeAndFill(0xFF00FFFF, 2.5F, 0x4400FFFF)));
		}
		if (engine.oreTargetPos != null && !engine.goingHome) {
			// 矿脉目标常在岩石后面，穿墙才看得到往哪挖。
			BorerGizmos.holdOnTop(Gizmos.cuboid(engine.oreTargetPos, GizmoStyle.strokeAndFill(0xFF55FF55, 3.0F, 0x4455FF55)));
		}
		if (engine.sideOreTargetPos != null && !engine.goingHome) {
			BorerGizmos.holdOnTop(Gizmos.cuboid(engine.sideOreTargetPos, GizmoStyle.strokeAndFill(0xFFFFAA00, 3.0F, 0x44FFAA00)));
		}
		if (engine.sealTarget != null) {
			BorerGizmos.hold(Gizmos.cuboid(engine.sealTarget, GizmoStyle.strokeAndFill(0xFF55AAFF, 3.0F, 0x4455AAFF)));
		}
		if (engine.goingHome && engine.trail.portal() != null) {
			BorerGizmos.holdOnTop(Gizmos.cuboid(engine.trail.portal(), GizmoStyle.strokeAndFill(0xFF66FFFF, 4.0F, 0x4466FFFF)));
		}
		if (engine.escapeShaft != null) {
			int headroom = BorerHazards.openHeadroom(client, engine.escapeShaft.below(), 12);
			for (int dy = 0; dy <= Math.max(3, headroom); dy++) {
				BorerGizmos.holdOnTop(Gizmos.cuboid(engine.escapeShaft.above(dy),
					GizmoStyle.strokeAndFill(0xFF22FF66, 2.8F, 0x5522FF66)));
			}
			try {
				BorerGizmos.holdOnTop(Gizmos.billboardText("↑ 无岩浆 可上升", Vec3.atCenterOf(engine.escapeShaft.above(2)),
					TextGizmo.Style.forColorAndCentered(0xFF22FF66).withScale(0.28F)));
			} catch (IllegalStateException ignored) {
			}
			if (client.player != null) {
				BorerGizmos.holdOnTop(Gizmos.arrow(client.player.getEyePosition().add(0.0, -0.3, 0.0),
					Vec3.atCenterOf(engine.escapeShaft), 0xFF22FF66, 2.8F));
			}
		}
		if (!engine.goingHome) {
			BlockPos lava = engine.liquids.findLava(client, client.player);
			// 岩浆穿墙显示：它藏在墙后面的时候才最需要看到。
			if (lava != null) {
				BorerGizmos.holdOnTop(Gizmos.cuboid(lava, GizmoStyle.strokeAndFill(0xFFFF3300, 3.0F, 0x66FF3300)));
			}
			BorerGizmos.hold(Gizmos.arrow(
				Vec3.atCenterOf(client.player.blockPosition()),
				Vec3.atCenterOf(client.player.blockPosition().relative(
					engine.mode == DefaultTunnelBorerEngine.Mode.DOWN ? Direction.DOWN : engine.forward, 3)),
				0xFF55FF55,
				2.5F
			));
		}
	}

	/** 画出区域黄框。 */
	void emitArea() {
		if (engine.areaMin == null || engine.areaMax == null) return;
		int y0 = engine.areaBoundedDown ? engine.areaMin.getY() : engine.areaMax.getY() - 1;
		int y1 = engine.areaMax.getY() + 1;
		AABB box = new AABB(
			engine.areaMin.getX(), y0, engine.areaMin.getZ(),
			engine.areaMax.getX() + 1.0, y1, engine.areaMax.getZ() + 1.0
		);
		BorerGizmos.holdOnTop(Gizmos.cuboid(box, GizmoStyle.strokeAndFill(0xFFFFFF66, 2.8F, 0x22FFCC33)));
		BorerGizmos.holdOnTop(Gizmos.cuboid(engine.areaMin, GizmoStyle.stroke(0xFFFFFFFF, 3.2F)));
		BorerGizmos.holdOnTop(Gizmos.cuboid(engine.areaMax, GizmoStyle.stroke(0xFFFFFFFF, 3.2F)));
		if (engine.areaWalkTarget != null) {
			BorerGizmos.holdOnTop(Gizmos.cuboid(engine.areaWalkTarget,
				GizmoStyle.strokeAndFill(0xFF55FF55, 3.0F, 0x4455FF55)));
		}
		Vec3 caption = new Vec3(
			(engine.areaMin.getX() + engine.areaMax.getX() + 1.0) * 0.5,
			y1 + 0.4,
			(engine.areaMin.getZ() + engine.areaMax.getZ() + 1.0) * 0.5
		);
		String title = engine.showingAreaPreview && !engine.active ? "预览区域  再按B开挖" : "已标区域";
		String size = BorerAreaPolicy.sizeLabel(
			engine.areaMin.getX(), engine.areaMax.getY(), engine.areaMin.getZ(),
			engine.areaMax.getX(), engine.areaMin.getY(), engine.areaMax.getZ());
		try {
			BorerGizmos.holdOnTop(Gizmos.billboardText(title, caption,
				TextGizmo.Style.forColorAndCentered(0xFFFFCC33).withScale(0.28F)));
			BorerGizmos.holdOnTop(Gizmos.billboardText(size, caption.add(0.0, -0.22, 0.0),
				TextGizmo.Style.forColorAndCentered(0xFFC0C0C0).withScale(0.20F)));
		} catch (IllegalStateException ignored) {
		}
	}

	/** 画出向下挖的整层矩形。脚下那格是原点；穿墙显示，旁边高地挡视线时仍能看出会挖进去。 */
	void emitShaft(Minecraft client, BlockPos feet) {
		int minX = Integer.MAX_VALUE;
		int minZ = Integer.MAX_VALUE;
		int maxX = Integer.MIN_VALUE;
		int maxZ = Integer.MIN_VALUE;
		int minDy = BorerShaftPolicy.previewSliceMinDy();
		int maxDy = BorerShaftPolicy.previewSliceMaxDy();
		for (BlockPos column : engine.shaftColumns(feet)) {
			minX = Math.min(minX, column.getX());
			minZ = Math.min(minZ, column.getZ());
			maxX = Math.max(maxX, column.getX());
			maxZ = Math.max(maxZ, column.getZ());
			boolean origin = column.equals(feet);
			for (int dy = minDy; dy <= maxDy; dy++) {
				BlockPos pos = column.offset(0, dy, 0);
				if (dy > 0 && client.level.getBlockState(pos).isAir()) continue;
				boolean originBlock = origin && dy == 0;
				boolean nextLayer = dy < 0;
				if (nextLayer) {
					BorerGizmos.holdOnTop(Gizmos.cuboid(pos,
						GizmoStyle.strokeAndFill(origin ? 0xFFFFCC33 : 0xFFFF8800, 2.2F, origin ? 0x44FFCC33 : 0x33FF8800)));
				} else {
					BorerGizmos.holdOnTop(Gizmos.cuboid(pos,
						GizmoStyle.stroke(originBlock ? 0xFFFFFFFF : 0xFFFFFF66, originBlock ? 3.2F : 2.0F)));
				}
			}
		}
		if (minX <= maxX) {
			AABB slice = new AABB(
				minX,
				BorerShaftPolicy.previewSliceMinY(feet.getY()),
				minZ,
				maxX + 1.0,
				BorerShaftPolicy.previewSliceMaxYExclusive(feet.getY()),
				maxZ + 1.0
			);
			BorerGizmos.holdOnTop(Gizmos.cuboid(slice, GizmoStyle.strokeAndFill(0xFFFFFF66, 2.8F, 0x22FFCC33)));
		}
		try {
			BorerGizmos.holdOnTop(Gizmos.billboardText("原点", Vec3.atCenterOf(feet.above()),
				TextGizmo.Style.forColorAndCentered(0xFFFFFFFF).withScale(0.24F)));
		} catch (IllegalStateException ignored) {
		}
	}
}
