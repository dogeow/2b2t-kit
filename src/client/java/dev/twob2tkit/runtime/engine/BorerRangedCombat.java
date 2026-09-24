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
	private final BorerCombatSession<LivingEntity> session = new BorerCombatSession<>();
	private final BorerCombatPeek peek;
	private final BorerCombatContinuation continuation=new BorerCombatContinuation();
	private String holdReason = "";
	private boolean drawing;
	private boolean escaping, escapeFlightFailed,hoverMelee;
	private final BorerAreaFlightSession escapeFlight = new BorerAreaFlightSession();
	private boolean releasePending;
	private final BorerBowViewGate viewGate = new BorerBowViewGate();
	private int lookTick = Integer.MIN_VALUE, viewWaitTicks;
	private RotationAim.Look look;
	private int previousSlot = -1, cooldown, blockedTicks, passiveTicks;
	BorerRangedCombat(DefaultTunnelBorerEngine engine) { this.engine = engine; this.peek=new BorerCombatPeek(engine); }
	boolean tick(Minecraft c) {
		boolean enabled;
		try { enabled = engine.standaloneGuard || engine.host.borerAutoDefend(); } catch (LinkageError oldHost) { return false; }
		if (!enabled) { end(c); return false; }
		var p = c.player;
		boolean wasPending = session.pending();
		session.beginTick(p.tickCount);
		boolean missingRestored=continuation.restore(c,session);
		// Retain removed references so a received death event is distinguishable from unloading.
		var observed = new java.util.LinkedHashMap<java.util.UUID, LivingEntity>();
		for (var e : session.targets()) observed.put(e.getUUID(), e);
		var nearby = c.level.getEntities(p, p.getBoundingBox().inflate(40)).stream()
			.filter(e -> e instanceof LivingEntity && e instanceof Enemy)
			.map(e -> (LivingEntity)e)
			.toList();
		for (var e : nearby) observed.put(e.getUUID(), e);
		int passive = 0;
		for (var e : observed.values()) {
			boolean present = c.level.getEntity(e.getId()) == e;
			boolean eligible = present && BorerDefensePolicy.eligible(true, e.isAlive(), p.hasLineOfSight(e), rank(e), p.distanceTo(e));
			boolean engaged = eligible && engine.engagement.shouldReact(p, e)
				|| present && engine.standaloneGuard && creeperAlert(c, e);
			if (eligible && !engaged && !session.contains(e.getUUID())) passive++;
			// isAlive() also becomes false on an unload. Health/death status is the required evidence.
			if (session.observe(e.getUUID(), e, engaged, e.isDeadOrDying(), eligible, e.getHealth()))
				engine.fileLog(c, "area-defense-death-confirmed id=" + e.getId() + " uuid=" + e.getUUID());
		}
		continuation.save(c,session);
		if(missingRestored){engine.pauseGuardMovement(c);engine.status="等待重新观察热加载前的敌对生物，施工保持暂停";return true;}
		// A controller may have flown away from an unfinished fight to a different
		// work area. Keeping that old UUID pending forever blocks safe inventory
		// work even when every hostile is over 48 blocks behind us. Record an
		// explicit disengagement, never a fabricated kill; fresh nearby threats
		// are observed again when the player returns.
		if(engine.standaloneGuard && session.pending() && session.targets().stream()
			.allMatch(e -> BorerDefensePolicy.encounterLeftBehind(p.getX()-e.getX(),p.getZ()-e.getZ()))) {
			engine.fileLog(c,"area-defense-disengage-relocated unresolved="+session.targets().size()+" confirmed_deaths=0");
			end(c);return false;
		}
		if (passive > 0 && ++passiveTicks >= 100) {
			engine.fileLog(c, "area-defense-ignore-passive count=" + passive); passiveTicks = 0;
		}
		if(peek.active()&&peek.acquired(c,peek.target())){
			boolean retry=session.repositioned(peek.target().getUUID());
			engine.fileLog(c,"guard-peek-visible uuid="+peek.target().getUUID()+" retry="+retry);peek.close(c);
		}
		var threats = session.targets().stream().filter(e -> session.canAttack(e.getUUID())).toList();
		int chosen = BorerDefensePolicy.choose(threats.stream().map(e -> new BorerDefensePolicy.Candidate(e.getId(), rank(e), p.distanceTo(e), engine.engagement.recentAttacker(p, e))).toList(), target == null ? -1 : target.getId());
		LivingEntity next = threats.stream().filter(e -> e.getId() == chosen).findFirst().orElse(null);
		if (!session.pending()) {
			if (wasPending) engine.fileLog(c, "area-defense-resume-work reason=all-engaged-targets-dead");
			end(c); return false;
		}
		if (previousSlot < 0) previousSlot = p.getInventory().getSelectedSlot();
		if (engine.standaloneGuard) engine.pauseGuardMovement(c);
		else engine.areaRunner.suspendForCombat(c);
		// An urgent creeper can require evasion even behind a corner or after the attack budget expires.
		if (engine.standaloneGuard) {
			var emergency = session.targets().stream().filter(e -> e instanceof Creeper && c.level.getEntity(e.getId()) == e && e.isAlive())
				.map(e -> (Creeper)e).filter(e -> StandaloneCreeperPolicy.evade(swelling(e), e.isPowered(), p.distanceTo(e), escaping && e == target))
				.min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
			if (emergency != null) { peek.close(c);target = emergency; return evadeCreeper(c, emergency); }
		}
		if (next == null) {
			releaseEscape(c); cancelDraw(c); rangedMode(false); target = null;
			if(engine.standaloneGuard){
				var hidden=session.targets().stream().filter(e->c.level.getEntity(e.getId())==e&&e.isAlive()&&!p.hasLineOfSight(e))
					.min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
				if(hidden!=null&&peek.tick(c,hidden))return true;
			}
			engine.mobs.raiseShield(c, p);
			String reason = session.timedOut() ? "no-confirmed-damage-30s" : "target-unavailable";
			if (!holdReason.equals(reason)) engine.fileLog(c, "area-defense-hold reason=" + reason + " unresolved=" + session.targets().size());
			holdReason = reason;
			engine.status = session.timedOut() ? "未确认击杀，已保持停挖，请接管" : "目标暂时被挡或离开视野，未确认击杀，保持停挖";
			return true;
		}
		peek.close(c);
		holdReason = "";
		if (next != target) {
			cancelDraw(c);
			target = next; blockedTicks = 0;
			engine.fileLog(c, "area-defense-target id=" + next.getId() + " rank=" + rank(next) + " name=" + next.getName().getString()
				+ " engaged=true recentAttacker=" + engine.engagement.recentAttacker(p, next));
		}
		if (engine.standaloneGuard && elevateBeforeCombat(c, threats)) return true;
		if(engine.standaloneGuard && target instanceof net.minecraft.world.entity.monster.zombie.Zombie && p.distanceTo(target)<9 && hoverZombie(c))return true;
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
			engine.status = "没有可用弓箭，停工并保留近身防御，等待补给";
            engine.host.requestEmergencyExit(c,"低血量且远程武器不可用");
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
	/** Clear the whole ascent before borrowing Flight; combat only resumes above nearby hostiles. */
	private boolean elevateBeforeCombat(Minecraft c, java.util.List<LivingEntity> threats) {
		var p = c.player;
		double rise = GuardWeaponPolicy.combatRise(p.getY(), threats.stream()
			.map(e -> new GuardWeaponPolicy.Threat(e.getY(),
				e.getMainHandItem().is(Items.BOW) || e.getMainHandItem().is(Items.CROSSBOW), p.distanceTo(e)))
			.toList());
		if (rise <= .25) return false;
		cancelDraw(c);rangedMode(false);engine.pauseGuardMovement(c);
		if (!clearWholeRise(c, rise)) {
			releaseEscape(c);
			engine.mobs.raiseShield(c, p);
			engine.status = "头顶没有安全升空通道，已停止攻击与施工";
			if (p.getHealth() < 14) engine.host.requestEmergencyExit(c, "遇敌且无法安全升空");
			return true;
		}
		try {
			escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/guard-hover-flight.bak"));
			if (escapeFlight.acquire(p) != null) {
				releaseEscape(c);
				engine.mobs.raiseShield(c, p);
				engine.status = "无法启飞，已停止攻击与施工";
				if (p.getHealth() < 14) engine.host.requestEmergencyExit(c, "遇敌且飞行不可用");
				return true;
			}
			escaping = true;
			if (!hoverMelee) { engine.host.enablePveMelee(); hoverMelee = true; }
			escapeFlight.speed(.16);
			c.options.keyJump.setDown(true);
			look = RotationAim.lookAt(p, target.getEyePosition());lookTick = p.tickCount;RotationAim.apply(p, look);
			engine.status = "先升空避敌，再反击 " + target.getName().getString();
			return true;
		} catch (IllegalStateException unavailable) {
			releaseEscape(c);engine.mobs.raiseShield(c, p);
			engine.status = "升空失败，已停止攻击与施工";
			if (p.getHealth() < 14) engine.host.requestEmergencyExit(c, "遇敌且升空失败");
			return true;
		}
	}
	/** Emergency motion must outrank the ordinary food pause, without changing ordinary mob engagement. */
	boolean hasCreeperEmergency(Minecraft c) {
		if(c.player==null||c.level==null)return false;
		for(var e:c.level.getEntitiesOfClass(Creeper.class,c.player.getBoundingBox().inflate(14)))
			if(e.isAlive() && creeperAlert(c,e) && StandaloneCreeperPolicy.evade(swelling(e),e.isPowered(),c.player.distanceTo(e),escaping&&e==target))return true;
		return false;
	}
	boolean hasImmediateHostileThreat(Minecraft c) {
		if (c.player == null || c.level == null) return false;
		var p = c.player;
		return c.level.getEntities(p, p.getBoundingBox().inflate(12)).stream()
			.anyMatch(e -> e instanceof Enemy && e instanceof LivingEntity living && living.isAlive()
				&& p.distanceTo(e) <= (living.getMainHandItem().is(Items.BOW)
					|| living.getMainHandItem().is(Items.CROSSBOW) ? 12 : 9)
				&& (p.hasLineOfSight(e) || p.distanceTo(e) < 3));
	}
	private boolean evadeCreeper(Minecraft c,Creeper creeper) {
        hoverMelee=false;
		var p=c.player;
		if(!escaping){
			// The host's beforeGuard/pauseForDefense path already yields construction
			// movement without overwriting this flight lease. This is not a new user task:
			// prepareForBorer would revoke the supervisor and permanently cancel the job.
			engine.pauseGuardMovement(c);
			escaping=true;escapeFlightFailed=false;
			DefaultTunnelBorerEngine.message(c,"苦力怕近身：施工暂停，优先撤离，确认安全后继续");
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
    private boolean hoverZombie(Minecraft c){
        var p=c.player;
        double rise=target.getY()+3.0-p.getY();
        // Check the whole ascent before borrowing movement. A low ceiling is not a logout reason.
        var choice=GuardWeaponPolicy.hover(p.getY(),target.getY(),rise<=0||clearWholeRise(c,rise));
        if(choice==GuardWeaponPolicy.Hover.FALLBACK)return false;
        try{
            escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/guard-hover-flight.bak"));
            if(escapeFlight.acquire(p)!=null)return false;
            escaping=true;
            cancelDraw(c);rangedMode(false);
            if(!hoverMelee){engine.host.enablePveMelee();hoverMelee=true;escaping=true;escapeFlightFailed=false;}
            engine.pauseGuardMovement(c);
            if(choice==GuardWeaponPolicy.Hover.RISE){
                escapeFlight.speed(.04);c.options.keyJump.setDown(true);
                engine.status="升高避开僵尸，保留杀戮光环";
            }else{escapeFlight.hover();engine.status="高处反击僵尸，确认击杀后继续";}
            if(!p.isUsingItem())BorerItems.selectWeapon(c,p);
            look=RotationAim.lookAt(p,target.getEyePosition());lookTick=p.tickCount;RotationAim.apply(p,look);
            return true;
        }catch(IllegalStateException unavailable){releaseEscape(c);return false;}
    }
    private boolean clearWholeRise(Minecraft c,double rise){
        if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(0,rise+.15,0)))return false;
        for(int i=1;i<=Math.ceil(rise+2);i++)if(!safeAir(c,c.player.blockPosition().above(i)))return false;
        return true;
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
		escaping=false;escapeFlightFailed=false;hoverMelee=false;
	}
	private static int rank(LivingEntity e) {
		return BorerDefensePolicy.priority(e instanceof Creeper,
			e.getMainHandItem().is(Items.BOW) || e.getMainHandItem().is(Items.CROSSBOW));
	}
	private static boolean usableBow(net.minecraft.world.item.ItemStack stack){return GuardWeaponPolicy.usableBow(stack.is(Items.BOW),stack.isDamageableItem(),stack.getMaxDamage()-stack.getDamageValue());}
	private boolean selectBow(Minecraft c) {
		var p = c.player; var inv = p.getInventory();
		if (usableBow(p.getMainHandItem())) return true;
		for (int i = 0; i < 36; i++) {
			var stack = inv.getItem(i);
			if (!usableBow(stack)) continue;
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
		if (c.player != null) session.pause(c.player.tickCount);
		if (c.player != null && c.player.isUsingItem() && c.player.getUseItem().is(Items.BOW)) {
			c.player.stopUsingItem();
			c.options.keyUse.setDown(false);
		}
		drawing = false; releasePending = false; look = null; viewGate.reset(); viewWaitTicks = 0;
	}
	void end(Minecraft c) {
		session.clear(); continuation.clear(); holdReason = "";
		releaseControls(c);
	}
	/** A menu suspends input, not our knowledge of the unfinished fight. */
	void pause(Minecraft c) {
		if (c.player != null) session.pause(c.player.tickCount);
		releaseControls(c);
	}
	private void releaseControls(Minecraft c) {
		peek.close(c);
		if (target == null && !drawing && previousSlot < 0 && !escaping) return;
		releaseEscape(c);
		cancelDraw(c); rangedMode(false);
		if (c.player != null && previousSlot >= 0) c.player.getInventory().setSelectedSlot(previousSlot);
		previousSlot = -1; target = null; cooldown = 0;
	}
	boolean reapply(Minecraft c) {
		if(peek.active()){peek.reapply(c);return true;}
		if (visibleLook(c) == null) return false;
		rangedMode(!hoverMelee);
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
		if (c.player == null || c.level == null || c.screen != null || target == null
			|| c.level.getEntity(target.getId()) != target || !target.isAlive() || !session.canAttack(target.getUUID())
			|| !c.player.hasLineOfSight(target) || !visibleHost()) { cancelDraw(c); return false; }
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
