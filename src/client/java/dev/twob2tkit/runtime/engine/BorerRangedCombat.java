package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.KeyMapping;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.Vec3;

/** Target priority + bow trigger. Ballistics is shared with the host; never chases out of the shaft. */
final class BorerRangedCombat {
	private final DefaultTunnelBorerEngine engine;
	private LivingEntity target;
	private boolean drawing;
	private boolean escaping, escapeFlightFailed;
	private final BorerAreaFlightSession escapeFlight = new BorerAreaFlightSession();
	private boolean releasePending;
	private final BorerBowViewGate viewGate = new BorerBowViewGate();
	private int lookTick = Integer.MIN_VALUE, viewWaitTicks;
	private RotationAim.Look look;
	private int previousSlot = -1, cooldown, blockedTicks, passiveTicks;
	BorerRangedCombat(DefaultTunnelBorerEngine engine) { this.engine = engine; }
	boolean tick(Minecraft c) {
		boolean enabled;
		try { enabled = engine.standaloneGuard || engine.host.borerAutoDefend(); } catch (LinkageError oldHost) { return false; }
		if (!enabled) { end(c); return false; }
		var p = c.player;
		var visible = c.level.getEntities(p, p.getBoundingBox().inflate(40)).stream()
			.filter(e -> e instanceof LivingEntity && e instanceof Enemy)
			.map(e -> (LivingEntity)e)
			.filter(e -> BorerDefensePolicy.eligible(true, e.isAlive(), p.hasLineOfSight(e), rank(e), p.distanceTo(e)) || engine.standaloneGuard && e.isAlive() && creeperAlert(c,e))
			.toList();
		var threats = visible.stream().filter(e -> engine.engagement.shouldReact(p, e) || engine.standaloneGuard && creeperAlert(c,e)).toList();
		if (visible.size() > threats.size() && ++passiveTicks >= 100) {
			engine.fileLog(c, "area-defense-ignore-passive count=" + (visible.size() - threats.size())); passiveTicks = 0;
		}
		int chosen = BorerDefensePolicy.choose(threats.stream().map(e -> new BorerDefensePolicy.Candidate(e.getId(), rank(e), p.distanceTo(e), engine.engagement.recentAttacker(p, e))).toList(), target == null ? -1 : target.getId());
		LivingEntity next = threats.stream().filter(e -> e.getId() == chosen).findFirst().orElse(null);
		if (next == null) {
			if (target != null) engine.fileLog(c, "area-defense-resume-work reason=no-active-threat previous=" + target.getId());
			end(c); return false;
		}
		if (previousSlot < 0) previousSlot = p.getInventory().getSelectedSlot();
		if (engine.standaloneGuard) engine.pauseGuardMovement(c);
		else engine.areaRunner.suspendForCombat(c);
		if (next != target) {
			cancelDraw(c);
			target = next; blockedTicks = 0;
			engine.fileLog(c, "area-defense-target id=" + next.getId() + " rank=" + rank(next) + " name=" + next.getName().getString()
				+ " engaged=true recentAttacker=" + engine.engagement.recentAttacker(p, next));
		}
		if (engine.standaloneGuard && target instanceof Creeper creeper && StandaloneCreeperPolicy.evade(swelling(creeper),creeper.isPowered(),p.distanceTo(creeper),escaping)) {
			return evadeCreeper(c,creeper);
		}
		if (escaping) { releaseEscape(c); engine.status="已拉开距离，建造保持停止"; }
		if (p.distanceTo(target) < 3 && p.hasLineOfSight(target)) {
			cancelDraw(c);
			rangedMode(true);
			BorerItems.selectWeapon(c, p);
			look = RotationAim.lookAt(p, target.getEyePosition());
			lookTick = p.tickCount;
			RotationAim.apply(p, look);
			if (p.getAttackStrengthScale(0) >= 0.95F) {
				c.gameMode.attack(p, target); p.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
			}
			engine.status = "优先反击 " + target.getName().getString();
			return true;
		}
		if (previousSlot < 0) previousSlot = p.getInventory().getSelectedSlot();
		rangedMode(true);
		if (!visibleHost()) {
			cancelDraw(c); look = RotationAim.lookAt(p, target.getEyePosition()); lookTick = p.tickCount; RotationAim.apply(p, look);
			engine.mobs.raiseShield(c, p); engine.status = "请完整重启游戏启用新版可见预判射箭；当前先停挖防御";
			return true;
		}
		if (cooldown > 0) {
			cooldown--;
			Vec3 nextAim = engine.host.borerBowAim(c, target);
			look = RotationAim.lookAt(p, nextAim == null ? target.getEyePosition() : nextAim); lookTick = p.tickCount;
			RotationAim.apply(p, look); return true;
		}
		if (!selectBow(c) || p.getProjectile(p.getMainHandItem()).isEmpty()) {
			cancelDraw(c);
			rangedMode(false);
			look = RotationAim.lookAt(p, target.getEyePosition()); lookTick = p.tickCount; RotationAim.apply(p, look);
			engine.mobs.raiseShield(c, p);
			engine.status = "需要弓和箭反击 " + target.getName().getString() + "，已停挖举盾";
			return true;
		}
		Vec3 aim;
		try { aim = engine.host.borerBowAim(c, target); } catch (LinkageError oldHost) { aim = null; }
		if (aim == null) {
			cancelDraw(c);
			look = RotationAim.lookAt(p, target.getEyePosition()); lookTick = p.tickCount; RotationAim.apply(p, look);
			engine.status = "射线被挡，举盾等待 " + target.getName().getString();
			engine.mobs.raiseShield(c, p);
			if (++blockedTicks % 40 == 0) engine.fileLog(c, "area-defense-blocked id=" + target.getId());
			return true;
		}
		blockedTicks = 0;
		engine.mobs.lowerShield(c);
		if (p.isUsingItem() && p.getUseItem().is(Items.SHIELD)) p.stopUsingItem();
		look = RotationAim.lookAt(p, aim);
		lookTick = p.tickCount;
		RotationAim.apply(p, look);
		if (BorerDefensePolicy.releaseArrow(p.getTicksUsingItem(), drawing && p.getUseItem().is(Items.BOW), true)) {
			if (viewReady(c)) {
				c.options.keyUse.setDown(false); releasePending = true;
				engine.status = "已对准，准备放箭 " + target.getName().getString();
			} else {
				c.options.keyUse.setDown(true); releasePending = false;
				engine.status = "等待画面朝向预判点，再放箭 " + target.getName().getString();
				logViewWait(c);
			}
		} else {
			if (!drawing) KeyMapping.click(com.mojang.blaze3d.platform.InputConstants.getKey(c.options.keyUse.saveString()));
			c.options.keyUse.setDown(true);
			drawing = true;
			engine.status = "拉弓反击 " + target.getName().getString() + " · 苦力怕优先";
		}
		return true;
	}
	private static boolean swelling(Creeper e) { return e.isIgnited() || e.getSwellDir()>0 || e.getSwelling(1)>0; }
	private boolean creeperAlert(Minecraft c, LivingEntity e) {
		if (!(e instanceof Creeper creeper) || !e.isAlive()) return false;
		double d=c.player.distanceTo(e);
		return StandaloneCreeperPolicy.alert(c.player.hasLineOfSight(e),swelling(creeper),creeper.isPowered(),d)
			|| escaping && e==target && StandaloneCreeperPolicy.evade(swelling(creeper),creeper.isPowered(),d,true);
	}
	/** Emergency motion must outrank the ordinary food pause, without changing ordinary mob engagement. */
	boolean hasCreeperEmergency(Minecraft c) {
		if(c.player==null||c.level==null)return false;
		for(var e:c.level.getEntitiesOfClass(Creeper.class,c.player.getBoundingBox().inflate(14)))
			if(e.isAlive() && creeperAlert(c,e) && StandaloneCreeperPolicy.evade(swelling(e),e.isPowered(),c.player.distanceTo(e),escaping&&e==target))return true;
		return false;
	}
	private boolean evadeCreeper(Minecraft c,Creeper creeper) {
		var p=c.player;
		if(!escaping){
			// Existing host contract stops construction/cruise first. Their later pause cannot erase escape input or set Flight speed to zero.
			engine.host.prepareForBorer(c);
			escaping=true;escapeFlightFailed=false;
			DefaultTunnelBorerEngine.message(c,"苦力怕近身：已停止施工，优先撤离，安全后再继续建造");
			engine.fileLog(c,"guard-creeper-evade id="+creeper.getId()+" distance="+p.distanceTo(creeper)+" swelling="+swelling(creeper)+" visible="+p.hasLineOfSight(creeper)+" player="+p.position()+" mob="+creeper.position());
		}
		cancelDraw(c);rangedMode(true);engine.pauseGuardMovement(c);
		boolean flying=false;
		if(!escapeFlightFailed)try{
			escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/creeper-escape-flight.bak"));
			String error=escapeFlight.acquire(p);
			if(error==null){escapeFlight.speed(.08);flying=true;}else escapeFlightFailed=true;
		}catch(IllegalStateException unavailable){if(!escapeFlightFailed)engine.fileLog(c,"guard-creeper-flight-unavailable "+unavailable.getMessage());escapeFlightFailed=true;}
		look=RotationAim.lookAt(p,creeper.getEyePosition());lookTick=p.tickCount;RotationAim.apply(p,look);
		if(flying && StandaloneCreeperPolicy.riseMovesAway(p.getY(),creeper.getY()) && clearRise(c)){
			c.options.keyJump.setDown(true);engine.status="苦力怕近身，向上脱离爆炸范围";return true;
		}
		float toward=RotationAim.yawToward(creeper.getX()-p.getX(),creeper.getZ()-p.getZ());
		for(float offset:new float[]{0,45,-45,90,-90}){
			float yaw=toward+offset;double rad=Math.toRadians(yaw);Vec3 away=new Vec3(Math.sin(rad),0,-Math.cos(rad));
			var swept=p.getBoundingBox().expandTowards(away.scale(1.1));
			if(!c.level.noCollision(p,swept))continue;
			var dest=net.minecraft.core.BlockPos.containing(p.position().add(away.scale(1.1)));
			if(!safeAir(c,dest)||!safeAir(c,dest.above()))continue;
			if(!flying && !BorerHazards.canWalkOrFallInto(c,dest))continue;
			look=new RotationAim.Look(yaw,12);lookTick=p.tickCount;RotationAim.apply(p,look);
			c.options.keyDown.setDown(true);engine.mobs.raiseShield(c,p);engine.status="苦力怕近身，面向威胁后撤";return true;
		}
		if(flying)escapeFlight.hover();engine.mobs.raiseShield(c,p);engine.status="苦力怕逼近，撤离通道被挡，请立即接管";return true;
	}
	private boolean clearRise(Minecraft c){
		if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(0,1.1,0)))return false;
		for(int i=1;i<=3;i++)if(!safeAir(c,c.player.blockPosition().above(i)))return false;
		return true;
	}
	private boolean safeAir(Minecraft c,net.minecraft.core.BlockPos p){
		if(!c.level.hasChunkAt(p))return false;var s=c.level.getBlockState(p);
		return s.getFluidState().isEmpty()&&!s.is(net.minecraft.world.level.block.Blocks.FIRE)&&!s.is(net.minecraft.world.level.block.Blocks.COBWEB)&&!s.is(net.minecraft.world.level.block.Blocks.POWDER_SNOW);
	}
	private void releaseEscape(Minecraft c){
		if(!escaping)return;engine.pauseGuardMovement(c);
		if(c.player!=null&&!c.player.onGround())escapeFlight.closeKeepingFlight();else escapeFlight.close();
		escaping=false;escapeFlightFailed=false;
	}
	private static int rank(LivingEntity e) {
		return BorerDefensePolicy.priority(e instanceof Creeper,
			e.getMainHandItem().is(Items.BOW) || e.getMainHandItem().is(Items.CROSSBOW));
	}
	private boolean selectBow(Minecraft c) {
		var p = c.player; var inv = p.getInventory();
		if (p.getMainHandItem().is(Items.BOW)) return true;
		for (int i = 0; i < 36; i++) {
			var stack = inv.getItem(i);
			if (!stack.is(Items.BOW) || stack.isDamageableItem() && stack.getMaxDamage() - stack.getDamageValue() < 3) continue;
			if (p.isUsingItem()) p.stopUsingItem();
			int slot = i < 9 ? i : 8;
			if (i >= 9) c.gameMode.handleContainerInput(p.containerMenu.containerId, i, slot, ContainerInput.SWAP, p);
			inv.setSelectedSlot(slot); return true;
		}
		return false;
	}
	private void cancelDraw(Minecraft c) {
		if (c.player != null && (drawing || target != null && c.player.getUseItem().is(Items.BOW))) c.player.stopUsingItem();
		if (c.options != null) c.options.keyUse.setDown(false);
		drawing = false; releasePending = false; look = null; viewGate.reset(); viewWaitTicks = 0;
	}
	private void rangedMode(boolean on) {
		try { engine.host.borerRangedMode(on); } catch (LinkageError ignored) {}
	}
	/** Keep the aura lease until eating finishes; do not restore a tool over Meteor's food. */
	void pauseForEating(Minecraft c) {
		if (c.player != null && c.player.isUsingItem() && c.player.getUseItem().is(Items.BOW)) {
			c.player.stopUsingItem();
			c.options.keyUse.setDown(false);
		}
		drawing = false; releasePending = false; look = null; viewGate.reset(); viewWaitTicks = 0;
	}
	void end(Minecraft c) {
		if (target == null && !drawing && previousSlot < 0 && !escaping) return;
		releaseEscape(c);
		cancelDraw(c); rangedMode(false);
		if (c.player != null && previousSlot >= 0) c.player.getInventory().setSelectedSlot(previousSlot);
		previousSlot = -1; target = null; cooldown = 0;
	}
	boolean reapply(Minecraft c) {
		if (visibleLook(c) == null) return false;
		rangedMode(true);
		RotationAim.apply(c.player, look); return true;
	}
	private boolean visibleHost() {
		try { return engine.host.supportsVisibleBowAim(); } catch (LinkageError oldHost) { return false; }
	}
	RotationAim.Look visibleLook(Minecraft c) {
		if (target == null || !target.isAlive() || look == null || c.player == null || c.screen != null) return null;
		long age = (long)c.player.tickCount - lookTick;
		return age >= 0 && age <= 1 ? look : null;
	}
	void viewRendered(Minecraft c, RotationAim.Look view) {
		if (visibleLook(c) != null) viewGate.rendered(view, c.player.tickCount);
	}
	private boolean viewReady(Minecraft c) {
		if (c.player == null || c.getCameraEntity() != c.player || !c.options.getCameraType().isFirstPerson()) return false;
		var camera = c.gameRenderer.getMainCamera();
		return camera.isInitialized() && camera.entity() == c.player && !camera.isDetached()
			&& viewGate.ready(look, new RotationAim.Look(camera.yRot(), camera.xRot()), c.player.tickCount);
	}
	private void logViewWait(Minecraft c) {
		if (++viewWaitTicks == 1 || viewWaitTicks % 40 == 0) {
			var camera = c.gameRenderer.getMainCamera();
			engine.fileLog(c, "area-defense-wait-view id=" + target.getId() + " wanted=" + look
				+ " camera=" + camera.yRot() + "," + camera.xRot() + " firstPerson=" + c.options.getCameraType().isFirstPerson());
		}
	}
	/** Called immediately before vanilla RELEASE_USE_ITEM, not when the key was merely scheduled to be released. */
	boolean prepareRelease(Minecraft c) {
		if (!drawing && !releasePending) return true;
		if (c.player == null || c.screen != null || target == null || !target.isAlive() || !visibleHost()) { cancelDraw(c); return false; }
		var p = c.player;
		if (!releasePending || !p.isUsingItem() || !p.getUseItem().is(Items.BOW) || p.getTicksUsingItem() < 20) {
			c.options.keyUse.setDown(true); return false;
		}
		Vec3 fresh = engine.host.borerBowAim(c, target);
		if (fresh == null) { releasePending = false; c.options.keyUse.setDown(true); return false; }
		look = RotationAim.lookAt(p, fresh); lookTick = p.tickCount; RotationAim.apply(p, look);
		if (!viewReady(c)) { releasePending = false; c.options.keyUse.setDown(true); logViewWait(c); return false; }
		// This is the same rotation already applied to the player and visible camera, never a silent aim packet.
		p.connection.send(new net.minecraft.network.protocol.game.ServerboundMovePlayerPacket.Rot(look.yaw(), look.pitch(), p.onGround(), p.horizontalCollision));
		drawing = false; releasePending = false; cooldown = 6; viewWaitTicks = 0;
		engine.status = "放箭反击 " + target.getName().getString();
		engine.fileLog(c, "area-defense-shot id=" + target.getId() + " rank=" + rank(target) + " visible=true look=" + look
			+ " target=" + target.position() + " " + engine.host.borerBowDiagnostics());
		return true;
	}
}
