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
    private final BorerCombatSeparation separation=new BorerCombatSeparation();
    private final TrialCreeperMeleePolicy trialCreeperMelee = new TrialCreeperMeleePolicy();
    private String trialCreeperEvidence = "";
    private final TrialCreeperFlightPolicy trialCreeperFlight = new TrialCreeperFlightPolicy();
    private java.util.List<net.minecraft.core.BlockPos> trialCreeperRoute = java.util.List.of();
    private net.minecraft.core.BlockPos trialCreeperRouteGoal;
    private java.util.UUID trialCreeperRouteTarget;
    private int trialCreeperRouteIndex;
    private String trialCreeperFlightEvidence = "";
    private final GuardWeaponPolicy.SafetyRise safetyRise=new GuardWeaponPolicy.SafetyRise();
    private int evidenceLogTick=Integer.MIN_VALUE;
    private String evidenceLogKey="";
    private final GuardZombieApproach zombieApproach=new GuardZombieApproach();
    private Object combatWorld;
	private String holdReason = "";
	private boolean drawing;
    private boolean miningMeleeLease;
    private final BorerMeleeProgress miningMeleeProgress = new BorerMeleeProgress();
    private boolean miningMeleeFallback;
    private boolean zombieMeleeLease, zombieMeleeFallback;
    private final BorerMeleeProgress zombieMeleeProgress = new BorerMeleeProgress();
	private boolean escaping, escapeFlightFailed,hoverMelee;
	private final BorerAreaFlightSession escapeFlight = new BorerAreaFlightSession();
	private boolean releasePending;
	private final BorerBowViewGate viewGate = new BorerBowViewGate();
	private int lookTick = Integer.MIN_VALUE, viewWaitTicks;
    private int riseRetryAfter,safetyRiseRetryAfter;
    private String lastRiseFailure = "";
	private RotationAim.Look look;
	private int previousSlot = -1, cooldown, blockedTicks, passiveTicks;
	BorerRangedCombat(DefaultTunnelBorerEngine engine) { this.engine = engine; this.peek=new BorerCombatPeek(engine); }
	boolean tick(Minecraft c) {
        var p = c.player;
        boolean minerCombat = engine.active && engine.mode != DefaultTunnelBorerEngine.Mode.AREA;
        var imminent = minerCombat ? engine.mobs.findImminentCreeper(c, p) : null;
		boolean enabled;
		try {
            enabled = minerCombat ? engine.host.borerPauseOnMob() || BorerThreats.shouldYieldToCombat(p) || session.pending() || imminent != null
                : engine.standaloneGuard || engine.host.borerAutoDefend();
        } catch (LinkageError oldHost) { return false; }
		if (!enabled) { end(c); return false; }
        if(combatWorld!=null&&combatWorld!=c.level)end(c);
        combatWorld=c.level;
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
			boolean present = c.level.getEntity(e.getId()) == e && e.level()==c.level;
			boolean eligible = present && attackEligible(c,e);
			boolean engaged = eligible && engine.engagement.shouldReact(p, e)
				|| present && flightDefenseScope() && p.distanceTo(e)<=12 && BorerThreats.currentReceivedMobHit(e,p)
				|| present && flightDefenseScope() && creeperAlert(c, e);
			if (eligible && !engaged && !session.contains(e.getUUID())) passive++;
			// isAlive() also becomes false on an unload. Health/death status is the required evidence.
			if (session.observe(e.getUUID(), e, engaged, e.isDeadOrDying(), eligible, e.getHealth()))
				engine.fileLog(c, "area-defense-death-confirmed id=" + e.getId() + " uuid=" + e.getUUID());
		}
        if (minerCombat) {
            if (imminent != null) {
                session.observe(imminent.getUUID(), imminent, true, imminent.isDeadOrDying(),
                    p.hasLineOfSight(imminent), imminent.getHealth());
                continuation.save(c, session);
                peek.close(c);
                resetMiningMelee();
                cancelDraw(c);
                target = imminent;
                engine.mobs.handleCreeper(c, p, imminent);
                return true;
            }
        }
		continuation.save(c,session);
        if(trialCreeperHorizontalDeferred(c,nearby,missingRestored)){
            safetyRise.cancel();releaseControls(c);session.pause(p.tickCount);
            if(!holdReason.equals("safe-deferred-trial-creeper-horizontal"))
                engine.fileLog(c,"area-defense-safe-deferred-trial-creeper-horizontal unresolved="+session.targets().size()+" confirmed_deaths=0");
            holdReason="safe-deferred-trial-creeper-horizontal";
            engine.status="单人试验：当前地面已远离苦力怕，保留敌人记录并允许准备防御物资";
            return false;
        }
        // Retain every unresolved UUID. Only a continuously verified safe height
        // permits other work; returning into reach/LOS makes this gate false immediately.
        boolean previouslyYielding=separation.yielding();
        if(!missingRestored && safeVerticalSeparation(c,nearby)){
            safetyRise.cancel();
            if(!previouslyYielding){
                engine.fileLog(c,"area-defense-safe-deferred unresolved="+session.targets().size()+" confirmed_deaths=0");
                logThreatEvidence(c,"safe-watch",null);
            }
            releaseControls(c);session.pause(p.tickCount);holdReason="safe-deferred";
            engine.status="已安全升空脱离，保留未解决敌人记录；靠近后恢复防御";return false;
        }
        if(missingRestored)separation.observe(c.level,p.tickCount,false);
        if(!missingRestored&&separation.verifying()){
            safetyRise.cancel();
            releaseControls(c);session.pause(p.tickCount);engine.mobs.raiseShield(c,p);
            engine.status="已离开爆炸范围，正在确认安全高度";return true;
        }

		// Missing pre-reload targets keep work paused, but must not prevent defense
		// against a currently observed threat. They also forbid clearing the fight.
		// A controller may have flown away from an unfinished fight to a different
		// work area. Keeping that old UUID pending forever blocks safe inventory
		// work even when every hostile is over 48 blocks behind us. Record an
		// explicit disengagement, never a fabricated kill; fresh nearby threats
		// are observed again when the player returns.
		if(!missingRestored && (engine.standaloneGuard||separation.retain(c.level)) && session.pending() && session.targets().stream()
			.allMatch(e -> BorerDefensePolicy.encounterLeftBehind(p.getX()-e.getX(),p.getZ()-e.getZ()))) {
            if(separation.retain(c.level)){
                safetyRise.cancel();
                releaseControls(c);session.pause(p.tickCount);holdReason="safe-deferred-relocated";
                engine.status="已离开旧威胁区域，保留未解决敌人记录";return false;
            }
			engine.fileLog(c,"area-defense-disengage-relocated unresolved="+session.targets().size()+" confirmed_deaths=0");
			end(c);return false;
		}
		if (passive > 0 && ++passiveTicks >= 100) {
			engine.fileLog(c, "area-defense-ignore-passive count=" + passive); passiveTicks = 0;
		}
		if(peek.active()){
			if(peek.acquired(c,peek.target())){
				boolean retry=session.repositioned(peek.target().getUUID());
				engine.fileLog(c,"guard-peek-visible uuid="+peek.target().getUUID()+" retry="+retry);peek.close(c);
			}else if(peek.tick(c,peek.target()))return true;
		}
		var threats = session.targets().stream().filter(e -> session.canAttack(e.getUUID())).toList();
		int chosen = BorerDefensePolicy.choose(threats.stream().map(e -> new BorerDefensePolicy.Candidate(e.getId(), rank(p,e), p.distanceTo(e), engine.engagement.recentAttacker(p, e))).toList(), target == null ? -1 : target.getId());
		LivingEntity next = threats.stream().filter(e -> e.getId() == chosen).findFirst().orElse(null);
		if (!missingRestored && !session.pending()) {
			if (wasPending) engine.fileLog(c, "area-defense-resume-work reason=all-engaged-targets-dead");
			end(c); return false;
		}
		if (previousSlot < 0) previousSlot = p.getInventory().getSelectedSlot();
        if (minerCombat) {
            engine.releaseMine(c);
            c.options.keyShift.setDown(false);
            c.options.keySprint.setDown(false);
        } else if (engine.standaloneGuard || escaping && flightDefenseScope()) engine.pauseGuardMovement(c);
		else engine.areaRunner.suspendForCombat(c);
		// The host authorizes only its exact opted-in disposable trial. An old host keeps the existing path.
		// Run before both emergency-distance evasion and the expired ranged-attack budget.
		if (engine.standaloneGuard && trialCreeperFlight(c, missingRestored)) return true;
		if (engine.standaloneGuard && trialCreeperMelee(c, missingRestored)) return true;
		// An urgent creeper can require evasion even behind a corner or after the attack budget expires.
		if (flightDefenseScope()) {
			var emergency = session.targets().stream().filter(e -> e instanceof Creeper && c.level.getEntity(e.getId()) == e && e.isAlive())
				.map(e -> (Creeper)e).filter(e -> StandaloneCreeperPolicy.evade(swelling(e), e.isPowered(), p.distanceTo(e), escaping && e == target))
				.min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
			if (emergency != null) {
                if(!engine.standaloneGuard&&!escaping)engine.areaRunner.yieldFlightForEscape(c);
                peek.close(c);target = emergency; return evadeCreeper(c, emergency);
            }
		}
        // A nearby melee threat can remain visible just beyond attack range.
        // Try only the existing collision-checked safe route before another
        // rise undoes that approach; creepers and ranged threats keep priority.
        if(engine.standaloneGuard&&next==null&&!missingRestored
                &&nearby.stream().noneMatch(e->e.isAlive()&&(e instanceof Creeper||BorerThreats.isRangedCombatThreat(e,p)))){
            var reposition=session.targets().stream().filter(e->c.level.getEntity(e.getId())==e&&e.isAlive()
                &&!(e instanceof Creeper)&&!BorerThreats.isRangedCombatThreat(e,p)&&session.needsReposition(e.getUUID()))
                .min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
            if(reposition!=null&&peek.tick(c,reposition))return true;
        }
        // A verified safe peek must reach attack range before its expired
        // attack budget can be renewed. Re-rising mid-route would undo it.
        if(engine.standaloneGuard && !peek.active() && safetyRise(c))return true;
		if (next == null) {
            rangedMode(false);
            releaseMiningMelee();
			if (missingRestored) return holdForMissingObservation(c);
			releaseEscape(c); cancelDraw(c); rangedMode(false); target = null;
			if(engine.standaloneGuard){
				var hidden=session.targets().stream().filter(e->c.level.getEntity(e.getId())==e&&e.isAlive()
					&&(!p.hasLineOfSight(e)||session.needsReposition(e.getUUID())))
					.min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
				if(hidden!=null&&peek.tick(c,hidden))return true;
			}
			engine.mobs.raiseShield(c, p);
			String reason = session.timedOut() ? "no-confirmed-damage-30s" : "target-unavailable";
			if (!holdReason.equals(reason)) engine.fileLog(c, "area-defense-hold reason=" + reason + " unresolved=" + session.targets().size());
            logThreatEvidence(c,"hold:"+reason,null);
			holdReason = reason;
			engine.status = session.timedOut() ? "未确认击杀，已保持停挖，请接管" : "目标暂时被挡或离开视野，未确认击杀，保持停挖";
			return true;
		}
		peek.close(c);
		holdReason = "";
		if (next != target) {
            releaseZombieMelee();
            if (minerCombat) resetMiningMelee();
			cancelDraw(c);
			target = next; blockedTicks = 0;
			engine.fileLog(c, "area-defense-target id=" + next.getId() + " rank=" + rank(p,next) + " name=" + next.getName().getString()
				+ " engaged=true recentAttacker=" + engine.engagement.recentAttacker(p, next));
            logThreatEvidence(c,"target",next);
            if (minerCombat) engine.fileLog(c, "mining-defense-pause mode=" + engine.mode
                + " currentTarget=" + (engine.currentTarget == null ? "none" : BorerText.block(engine.currentTarget))
                + " oreGoal=" + (engine.oreTargetPos == null ? "none" : BorerText.block(engine.oreTargetPos))
                + " miningAttack=" + c.options.keyAttack.isDown()
                + " miningMove=" + c.options.keyUp.isDown() + " id=" + next.getId());
		}
        boolean meleeTarget = BorerMiningCombatPolicy.meleeTarget(
            target instanceof net.minecraft.world.entity.monster.piglin.Piglin,
            target instanceof net.minecraft.world.entity.monster.piglin.PiglinBrute,
            BorerThreats.isRangedCombatThreat(target,p), p.distanceTo(target), p.getY() - target.getY());
        if (minerCombat && meleeTarget) {
            cancelDraw(c);
            if (!miningMeleeFallback) {
                rangedMode(false);
                miningMeleeLease = true;
                boolean meteorReady = BorerMeteorThreatLease.acquire(engine.host, c, target);
                boolean stalled = miningMeleeProgress.stalled(target.getUUID(), p.tickCount, target.getHealth());
                miningMeleeFallback = !meteorReady || stalled;
                if (miningMeleeFallback) {
                    engine.fileLog(c, "mining-defense-attack-owner id=" + target.getId()
                        + " nativeReady=" + meteorReady + " noDamageGraceExpired=" + stalled + " fallback=true");
                    rangedMode(true);
                }
            }
            if (miningMeleeFallback) {
                look = RotationAim.lookAt(p, target.getEyePosition());
                lookTick = p.tickCount;
                RotationAim.apply(p, look);
            }
            engine.status = engine.mobs.engageMiningThreat(c, p, target, !miningMeleeFallback);
            return true;
        }
        if (miningMeleeLease) resetMiningMelee();

		boolean zombieOnly=engine.standaloneGuard
			&&ordinaryZombie(p,target)&&onlyZombiesNearby(c,nearby);
		if(zombieOnly){if(swordZombieFromHover(c,nearby))return true;}
		else { zombieApproach.reset(); releaseZombieMelee(); }
		if (engine.standaloneGuard && elevateBeforeCombat(c, threats)) return true;
        if (escaping) { releaseEscape(c); engine.status="已拉开距离，建造保持停止"; }
		if (GuardWeaponPolicy.groundSwordAllowed(engine.standaloneGuard,zombieOnly)
				&&p.distanceTo(target) < 3 && p.hasLineOfSight(target)) {
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
    private boolean trialCreeperHorizontalDeferred(Minecraft c,java.util.List<LivingEntity> nearby,boolean missingRestored){
        if(c.player==null||c.level==null||!engine.standaloneGuard||missingRestored)return false;
        boolean authorized;try{authorized=engine.host.allowTrialCreeperMelee(c);}catch(LinkageError oldHost){return false;}
        var p=c.player;
        boolean grounded=p.onGround()&&!p.isInWater()&&!p.isInLava()&&!p.isOnFire()
            &&GuardWeaponPolicy.finiteVector(p.position())&&GuardWeaponPolicy.finiteBox(p.getBoundingBox())
            &&c.level.noCollision(p,p.getBoundingBox())&&currentServerChunk(c,p.blockPosition());
        var threats=session.targets().stream().map(e->{
            boolean current=e.level()==c.level&&c.level.getEntity(e.getId())==e;
            boolean finite=GuardWeaponPolicy.finiteVector(e.position())&&GuardWeaponPolicy.finiteBox(e.getBoundingBox())
                &&Float.isFinite(e.getHealth());
            boolean ordinary=e instanceof Creeper;
            var creeper=ordinary?(Creeper)e:null;
            double bodySquared=finite?GuardWeaponPolicy.boxDistanceSquared(p.getBoundingBox(),e.getBoundingBox()):Double.NaN;
            return new TrialCreeperHorizontalPolicy.Threat(current,e.isAlive()&&e.getHealth()>0,ordinary,
                ordinary&&creeper.isPowered(),ordinary&&creeper.isIgnited(),ordinary&&swelling(creeper),
                finite&&currentServerChunk(c,e.blockPosition()),p.distanceTo(e),Math.sqrt(bodySquared));
        }).toList();
        boolean nearbyHostile=nearby.stream().anyMatch(e->e.isAlive()&&(
            !GuardWeaponPolicy.finiteVector(e.position())||!GuardWeaponPolicy.finiteBox(e.getBoundingBox())
            ||p.distanceTo(e)<=TrialCreeperHorizontalPolicy.SAFE_DISTANCE));
        return TrialCreeperHorizontalPolicy.safe(authorized,engine.standaloneGuard,missingRestored,grounded,nearbyHostile,threats);
    }
    private boolean trialCreeperFlight(Minecraft c, boolean missingRestored) {
        if(missingRestored||c.player==null||c.level==null||c.gameMode==null||c.screen!=null)return false;
        boolean authorized;
        try{authorized=engine.host.allowTrialCreeperMelee(c);}catch(LinkageError oldHost){return false;}
        if(!authorized||hasUsableBow(c)||c.player.hasEffect(net.minecraft.world.effect.MobEffects.WEAKNESS))return false;
        var p=c.player;
        var creeper=session.targets().stream().filter(e->e instanceof Creeper).map(e->(Creeper)e)
            .filter(e->TrialCreeperMeleePolicy.eligible(authorized,e.level()==c.level&&c.level.getEntity(e.getId())==e
                    &&currentServerChunk(c,e.blockPosition()),e.isAlive(),p.hasLineOfSight(e),e.isPowered(),e.isIgnited(),false,
                    trialCreeperFlight.activeTarget(e.getUUID())&&p.distanceTo(e)<=16?Math.min(12,p.distanceTo(e)):p.distanceTo(e)))
            .min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
        if(creeper==null)return false;
        if(p.containerMenu!=p.inventoryMenu||!p.containerMenu.getCarried().isEmpty()){
            trialFlightUnavailable(c,creeper,"inventory_not_settled");return false;
        }
        if(!selectTrialSword(c,creeper.getHealth())){
            trialFlightUnavailable(c,creeper,"insufficient_sword_reserve");return false;
        }
        double highY=creeper.getY()+7.75;
        double strikeY=Math.max(creeper.getY()+3.05,creeper.getBoundingBox().maxY
            +p.getAttackRangeWith(p.getMainHandItem()).effectiveMaxRange(p)-p.getEyeHeight()-.15);
        var high=new Vec3(creeper.getX(),highY,creeper.getZ());
        boolean aligned=Math.hypot(p.getX()-creeper.getX(),p.getZ()-creeper.getZ())<=.25;
        var strike=new Vec3(aligned?p.getX():creeper.getX(),strikeY,aligned?p.getZ():creeper.getZ());
        var columnHigh=new Vec3(strike.x,highY,strike.z);
        boolean column=trialFlightColumn(c,strike,columnHigh,creeper);
        boolean inRange=p.isWithinAttackRange(p.getMainHandItem(),creeper.getBoundingBox(),.15);
        if(!session.canAttack(creeper.getUUID())){
            if(!session.canRetryTrialMelee(creeper.getUUID()))return false;
            // Verify an actual usable strike column and reachable high approach before the single capability retry.
            boolean viable=column&&!swelling(creeper)&&(aligned||!trialFlightPlan(c,creeper,high).isEmpty());
            if(session.retryTrialMelee(creeper.getUUID(),viable))
                engine.fileLog(c,"guard-trial-creeper-budget-retry uuid="+creeper.getUUID()+" reason=verified_flying_sword_capability");
            if(!session.canAttack(creeper.getUUID()))return false;
        }
        var step=trialCreeperFlight.step(creeper.getUUID(),p.tickCount,p.getX(),p.getZ(),creeper.getHealth(),
            p.distanceTo(creeper),p.getY(),creeper.getY(),aligned,swelling(creeper),inRange,
            p.getAttackStrengthScale(0)>=.95F,column);
        logTrialFlight(c,creeper,step);
        if(step.decision()==TrialCreeperFlightPolicy.Decision.UNAVAILABLE)return false;
        peek.close(c);releaseZombieMelee();releaseMiningMelee();cancelDraw(c);rangedMode(true);
        safetyRise.cancel();engine.pauseGuardMovement(c);target=creeper;
        try{
            escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/guard-hover-flight.bak"));
            if(escapeFlight.acquire(p)!=null){trialFlightUnavailable(c,creeper,"flight_unavailable");return false;}
            escaping=true;hoverMelee=false;
            switch(step.decision()){
                case HIGH_APPROACH -> {
                    Vec3 destination=trialFlightHighWaypoint(c,creeper,high);
                    if(destination==null){trialFlightUnavailable(c,creeper,"no_safe_high_approach");return false;}
                    if(!trialFlightMove(c,creeper,destination,true)){trialFlightUnavailable(c,creeper,"high_approach_step_blocked");return false;}
                    engine.status="单人试验：飞到苦力怕上方，升至真实距离超过7.5格并等蓄爆归零";
                }
                case DESCEND -> {
                    // Never descend past the planned strike height just to force a hit.
                    if(p.getY()<=strikeY+.07){trialFlightUnavailable(c,creeper,"sword_unreachable_from_safe_height");return false;}
                    if(!column||!trialFlightMove(c,creeper,new Vec3(p.getX(),strikeY,p.getZ()))){
                        trialFlightUnavailable(c,creeper,"descent_column_changed");return false;
                    }
                    engine.status="单人试验：复核整段升降通道后下降至真实剑程";
                }
                case ATTACK -> {
                    escapeFlight.hover();
                    look=RotationAim.lookAt(p,creeper.getEyePosition());lookTick=p.tickCount;RotationAim.apply(p,look);
                    if(c.level.getEntity(creeper.getId())!=creeper||!creeper.isAlive()||swelling(creeper)
                        ||!p.hasLineOfSight(creeper)||!p.isWithinAttackRange(p.getMainHandItem(),creeper.getBoundingBox(),.15)
                        ||!trialFlightColumn(c,strike,columnHigh,creeper))return evadeCreeper(c,creeper);
                    engine.mobs.lowerShield(c);if(p.isUsingItem()&&p.getUseItem().is(Items.SHIELD))p.stopUsingItem();
                    c.gameMode.attack(p,creeper);p.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
                    trialCreeperFlight.attacked();
                    // Start the verified ascent immediately, without treating the swing as confirmed damage.
                    if(!trialFlightMove(c,creeper,new Vec3(p.getX(),highY,p.getZ())))
                        return evadeCreeper(c,creeper);
                    engine.fileLog(c,"guard-trial-creeper-flight-sword-intent uuid="+creeper.getUUID()
                        +" mob_health="+creeper.getHealth()+" remaining="+BorerItems.remainingDurability(p.getMainHandItem()));
                    engine.status="单人试验：上方挥剑一次，立即升高，等待实际伤害确认";
                }
                case WAIT -> {
                    escapeFlight.hover();look=RotationAim.lookAt(p,creeper.getEyePosition());lookTick=p.tickCount;RotationAim.apply(p,look);
                    engine.status="单人试验：安全悬停剑程，等待攻击冷却";
                }
                default -> {return false;}
            }
            return true;
        }catch(IllegalStateException unavailable){trialFlightUnavailable(c,creeper,"flight_lease_changed");return false;}
    }
    private void logTrialFlight(Minecraft c,Creeper creeper,TrialCreeperFlightPolicy.Step step){
        String key=creeper.getUUID()+":"+step.decision()+":"+step.reason();
        if(key.equals(trialCreeperFlightEvidence))return;trialCreeperFlightEvidence=key;
        engine.fileLog(c,"guard-trial-creeper-flight-"+(step.decision()==TrialCreeperFlightPolicy.Decision.UNAVAILABLE?"unavailable":"step")
            +" uuid="+creeper.getUUID()+" decision="+step.decision()+" reason="+step.reason()
            +" distance="+c.player.distanceTo(creeper)+" player="+c.player.position()+" mob="+creeper.position()+" mob_health="+creeper.getHealth());
    }
    private void trialFlightUnavailable(Minecraft c,Creeper creeper,String reason){
        logTrialFlight(c,creeper,trialCreeperFlight.fail(reason));
        trialCreeperRoute=java.util.List.of();releaseEscape(c);
    }
    private java.util.List<net.minecraft.core.BlockPos> trialFlightPlan(Minecraft c,Creeper creeper,Vec3 high){
        var start=c.player.blockPosition();
        var goal=net.minecraft.core.BlockPos.containing(high.x,Math.ceil(high.y),high.z);
        return BorerFlyPath.findExact(q->trialFlightBody(c,BorerFlyPath.waypoint(q),creeper,true),start,goal,12,1600).nodes();
    }
    private Vec3 trialFlightHighWaypoint(Minecraft c,Creeper creeper,Vec3 high){
        var p=c.player;var goal=net.minecraft.core.BlockPos.containing(high.x,Math.ceil(high.y),high.z);
        // A directly swept, loaded route avoids unnecessary replanning in open air.
        if(trialFlightSweep(c,p.position(),high,creeper,true))return high;
        if(!creeper.getUUID().equals(trialCreeperRouteTarget)||!goal.equals(trialCreeperRouteGoal)||trialCreeperRoute.isEmpty()){
            trialCreeperRoute=trialFlightPlan(c,creeper,high);trialCreeperRouteIndex=0;
            trialCreeperRouteGoal=goal;trialCreeperRouteTarget=creeper.getUUID();
            if(trialCreeperRoute.isEmpty())return null;
            engine.fileLog(c,"guard-trial-creeper-flight-route uuid="+creeper.getUUID()+" nodes="+trialCreeperRoute.size());
        }
        while(trialCreeperRouteIndex<trialCreeperRoute.size()
            &&p.position().distanceToSqr(BorerFlyPath.waypoint(trialCreeperRoute.get(trialCreeperRouteIndex)))<.025)trialCreeperRouteIndex++;
        return trialCreeperRouteIndex>=trialCreeperRoute.size()?high:BorerFlyPath.waypoint(trialCreeperRoute.get(trialCreeperRouteIndex));
    }
    private boolean trialFlightMove(Minecraft c,Creeper creeper,Vec3 destination){
        return trialFlightMove(c,creeper,destination,false);
    }
    private boolean trialFlightMove(Minecraft c,Creeper creeper,Vec3 destination,boolean approach){
        var p=c.player;var input=BorerFlyPath.input(p.position(),destination,p.getYRot());
        if(!trialFlightSweep(c,p.position(),p.position().add(input.delta()),creeper,approach))return false;
        escapeFlight.speed(GuardZombieApproach.sprintSafeSpeed(input.speed()));
        look=input.forward()?new RotationAim.Look(input.yaw(),0):RotationAim.lookAt(p,creeper.getEyePosition());
        lookTick=p.tickCount;RotationAim.apply(p,look);p.stopUsingItem();c.options.keyUse.setDown(false);
        c.options.keyUp.setDown(input.forward());c.options.keyJump.setDown(input.up());c.options.keyShift.setDown(input.down());
        return true;
    }
    private boolean trialFlightColumn(Minecraft c,Vec3 strike,Vec3 high,Creeper creeper){
        return strike.y>=creeper.getY()+3.05&&high.y-strike.y<=12&&trialFlightSweep(c,strike,high,creeper,false);
    }
    private boolean trialFlightBody(Minecraft c,Vec3 feet,Creeper creeper,boolean approach){
        if(!GuardWeaponPolicy.finiteVector(feet)||feet.y>=316)return false;
        var p=c.player;var body=p.getBoundingBox().move(feet.subtract(p.position())).inflate(.02);
        if(!c.level.noCollision(p,body))return false;
        for(var q:net.minecraft.core.BlockPos.betweenClosed(net.minecraft.core.BlockPos.containing(body.minX,body.minY,body.minZ),
            net.minecraft.core.BlockPos.containing(body.maxX-1e-7,body.maxY-1e-7,body.maxZ-1e-7)))if(!safeAir(c,q))return false;
        if(approach&&feet.y<creeper.getY()+3.05&&feet.distanceTo(creeper.position())<6)return false;
        for(var e:c.level.getEntities(p,body.inflate(12)))if(e instanceof Enemy&&e instanceof LivingEntity living&&e.isAlive()){
            if(e==creeper)continue;
            if(!currentServerChunk(c,e.blockPosition())||!GuardWeaponPolicy.finiteBox(e.getBoundingBox()))return false;
            double radius=e instanceof Creeper other?(other.isPowered()?12:6):BorerThreats.isRangedCombatThreat(living,p)?12:4;
            if(GuardWeaponPolicy.boxDistanceSquared(body,e.getBoundingBox())<radius*radius)return false;
        }
        return true;
    }
    private boolean trialFlightSweep(Minecraft c,Vec3 from,Vec3 to,Creeper creeper,boolean approach){
        if(!GuardWeaponPolicy.finiteVector(from)||!GuardWeaponPolicy.finiteVector(to)||from.distanceTo(to)>16)return false;
        var body=c.player.getBoundingBox().move(from.subtract(c.player.position())).expandTowards(to.subtract(from)).inflate(.02);
        if(!c.level.noCollision(c.player,body))return false;
        for(var q:net.minecraft.core.BlockPos.betweenClosed(net.minecraft.core.BlockPos.containing(body.minX,body.minY,body.minZ),
            net.minecraft.core.BlockPos.containing(body.maxX-1e-7,body.maxY-1e-7,body.maxZ-1e-7)))if(!safeAir(c,q))return false;
        int samples=Math.max(1,(int)Math.ceil(from.distanceTo(to)/.25));
        for(int i=0;i<=samples;i++)if(!trialFlightBody(c,from.lerp(to,(double)i/samples),creeper,approach))return false;
        return true;
    }
    private boolean trialCreeperMelee(Minecraft c, boolean missingRestored) {
        if (missingRestored || c.player == null || c.level == null || c.gameMode == null || c.screen != null)
            return false;
        boolean authorized;
        try { authorized = engine.host.allowTrialCreeperMelee(c); }
        catch (LinkageError oldHost) { return false; }
        if (!authorized || hasUsableBow(c) || c.player.hasEffect(net.minecraft.world.effect.MobEffects.WEAKNESS))
            return false;
        var p = c.player;
        var creeper = session.targets().stream().filter(e -> e instanceof Creeper)
            .map(e -> (Creeper)e).filter(e -> TrialCreeperMeleePolicy.eligible(authorized,
                e.level() == c.level && c.level.getEntity(e.getId()) == e && currentServerChunk(c,e.blockPosition()),
                e.isAlive(),p.hasLineOfSight(e),e.isPowered(),e.isIgnited(),false,p.distanceTo(e)))
            .min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
        if (creeper == null) return false;
        if (!selectTrialSword(c,creeper.getHealth())) return false;
        boolean inRange = p.isWithinAttackRange(p.getMainHandItem(),creeper.getBoundingBox(),.15);
        boolean approachClear = inRange || engine.mobs.safeTrialApproach(c,p,creeper);
        boolean retreatClear = engine.mobs.safeRetreatFrom(c,p,creeper);
        if (!session.canAttack(creeper.getUUID())) {
            boolean retry = session.retryTrialMelee(creeper.getUUID(),approachClear && retreatClear && !swelling(creeper));
            if (retry) engine.fileLog(c,"guard-trial-creeper-budget-retry uuid="+creeper.getUUID()+" reason=verified_melee_capability");
            if (!session.canAttack(creeper.getUUID())) return false;
        }
        var step = trialCreeperMelee.step(creeper.getUUID(),p.tickCount,p.getX(),p.getZ(),p.distanceTo(creeper),
            creeper.getHealth(),swelling(creeper),inRange,p.getAttackStrengthScale(0)>=.95F,approachClear,retreatClear);
        String key = creeper.getUUID()+":"+step.decision()+":"+step.reason();
        if (!key.equals(trialCreeperEvidence)) {
            trialCreeperEvidence = key;
            engine.fileLog(c,"guard-trial-creeper-"+(step.decision()==TrialCreeperMeleePolicy.Decision.UNAVAILABLE?"unavailable":"step")
                +" uuid="+creeper.getUUID()+" decision="+step.decision()+" reason="+step.reason()
                +" distance="+p.distanceTo(creeper)+" mob_health="+creeper.getHealth());
        }
        if (step.decision() == TrialCreeperMeleePolicy.Decision.UNAVAILABLE) return false;
        peek.close(c); releaseZombieMelee(); releaseMiningMelee();
        safetyRise.cancel(); releaseEscape(c); cancelDraw(c); rangedMode(true);
        engine.pauseGuardMovement(c);
        p.setSprinting(false);
        target = creeper;
        look = RotationAim.lookAt(p,creeper.getEyePosition());lookTick=p.tickCount;RotationAim.apply(p,look);
        switch (step.decision()) {
            case RETREAT -> {
                engine.mobs.raiseShield(c,p);
                if (!engine.mobs.trialRetreatFrom(c,p,creeper)) return evadeCreeper(c,creeper);
                look = new RotationAim.Look(p.getYRot(),p.getXRot());
                engine.status="单人试验：面向苦力怕后撤，等蓄爆归零再接近";
            }
            case APPROACH -> {
                engine.mobs.lowerShield(c);
                c.options.keyUp.setDown(true);
                engine.status="单人试验：沿安全通道接近苦力怕，剑战清除";
            }
            case ATTACK -> {
                // Recheck live identity, fuse, sight and actual reach after slot/flight ownership changes.
                if (c.level.getEntity(creeper.getId()) != creeper || !creeper.isAlive() || swelling(creeper)
                    || !p.hasLineOfSight(creeper) || !p.isWithinAttackRange(p.getMainHandItem(),creeper.getBoundingBox(),.15))
                    return evadeCreeper(c,creeper);
                engine.mobs.lowerShield(c);
                if (p.isUsingItem() && p.getUseItem().is(Items.SHIELD)) p.stopUsingItem();
                c.gameMode.attack(p,creeper);p.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
                trialCreeperMelee.attacked();
                // Movement can start this tick; damage confirmation comes only from next live observations.
                engine.mobs.trialRetreatFrom(c,p,creeper);
                look = new RotationAim.Look(p.getYRot(),p.getXRot());
                engine.fileLog(c,"guard-trial-creeper-sword-intent uuid="+creeper.getUUID()+" mob_health="+creeper.getHealth()
                    +" remaining="+BorerItems.remainingDurability(p.getMainHandItem()));
                engine.status="单人试验：挥剑后撤，等待实际伤害确认";
            }
            case WAIT -> engine.status="单人试验：保持剑程，等攻击冷却";
            default -> { return false; }
        }
        return true;
    }
    private boolean hasUsableBow(Minecraft c) {
        var p = c.player;
        for (int slot=0;slot<36;slot++) {
            var stack=p.getInventory().getItem(slot);
            if (usableBow(stack) && !p.getProjectile(stack).isEmpty()) return true;
        }
        return false;
    }
    /** Unlike the server's 32 reserve, a starter sword needs the forecast swings plus a small margin. */
    private boolean selectTrialSword(Minecraft c,float health) {
        var p=c.player;var inv=p.getInventory();
        if(p.containerMenu!=p.inventoryMenu||!p.containerMenu.getCarried().isEmpty())return false;
        int best=-1;double bestDamage=0;
        for (int slot=0;slot<36;slot++) {
            var stack=inv.getItem(slot);
            if (stack.isEmpty() || !stack.is(net.minecraft.tags.ItemTags.SWORDS)) continue;
            double damage=stack.getOrDefault(net.minecraft.core.component.DataComponents.ATTRIBUTE_MODIFIERS,
                net.minecraft.world.item.component.ItemAttributeModifiers.EMPTY).compute(
                    net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE,1,
                    net.minecraft.world.entity.EquipmentSlot.MAINHAND);
            if (BorerItems.remainingDurability(stack)<TrialCreeperMeleePolicy.swordReserve(health,damage)) continue;
            if (damage>bestDamage) { best=slot;bestDamage=damage; }
        }
        if (best<0) return false;
        if (best<9) inv.setSelectedSlot(best);
        else {
            int dest=-1;
            for (int slot=0;slot<9;slot++) if (inv.getItem(slot).isEmpty()) { dest=slot;break; }
            if (dest<0) return false; // Preserve a full hotbar instead of overwriting the paused task's tool.
            c.gameMode.handleContainerInput(p.containerMenu.containerId,best,dest,ContainerInput.SWAP,p);
            inv.setSelectedSlot(dest);
        }
        var selected=p.getMainHandItem();
        double damage=selected.getOrDefault(net.minecraft.core.component.DataComponents.ATTRIBUTE_MODIFIERS,
            net.minecraft.world.item.component.ItemAttributeModifiers.EMPTY).compute(
                net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE,1,net.minecraft.world.entity.EquipmentSlot.MAINHAND);
        return selected.is(net.minecraft.tags.ItemTags.SWORDS)
            &&BorerItems.remainingDurability(selected)>=TrialCreeperMeleePolicy.swordReserve(health,damage);
    }
    private boolean safeVerticalSeparation(Minecraft c,java.util.List<LivingEntity> nearby){
        var p=c.player;
        // Account for half a second of downward momentum before accepting the blast margin.
        double projectedY=p.getY()+Math.min(0,p.getDeltaMovement().y)*10;
        var projected=new Vec3(p.getX(),projectedY,p.getZ());
        var currentlyObserved=new java.util.ArrayList<java.util.UUID>();
        var threats=session.targets().stream().map(e->{
            boolean present=e.level()==c.level&&c.level.getEntity(e.getId())==e&&e.isAlive();
            if(!present)return separation.unloaded(c.level,e.getUUID(),p.getX(),projectedY,p.getZ());
            boolean unarmed=ordinaryZombie(p,e)&&e.getMainHandItem().isEmpty()&&e.getOffhandItem().isEmpty()
                &&!BorerThreats.currentReceivedMobHit(e,p);
            if(!unarmed)separation.revokeUnarmed(c.level,e.getUUID());
            if(!GuardWeaponPolicy.finiteVector(e.position())||!GuardWeaponPolicy.finiteBox(e.getBoundingBox())){
                separation.seen(c.level,e.getUUID(),Double.NaN,Double.NaN,Double.NaN,Double.NaN,false,false,false);
                return new BorerCombatSeparation.Threat(false,false,false,false,Double.NaN,Double.NaN);
            }
            if(!currentServerChunk(c,e.blockPosition()))
                return new BorerCombatSeparation.Threat(false,false,false,false,Double.NaN,Double.NaN);
            boolean ordinary=e instanceof Creeper creeper&&!creeper.isPowered();
            boolean swelling=e instanceof Creeper creeper&&swelling(creeper);
            separation.seen(c.level,e.getUUID(),e.getX(),e.getY(),e.getZ(),e.getBoundingBox().maxY,ordinary,swelling,unarmed);
            double distance=projected.distanceTo(e.position()),clearance=projectedY-e.getBoundingBox().maxY;
            if(unarmed&&(distance<12||clearance<6))separation.revokeUnarmed(c.level,e.getUUID());
            currentlyObserved.add(e.getUUID());
            return new BorerCombatSeparation.Threat(true,ordinary,p.hasLineOfSight(e),swelling,
                distance,clearance,false,unarmed);
        }).toList();
        boolean otherThreat=nearby.stream().anyMatch(e->e.isAlive()&&(
            BorerDefensePolicy.eligible(true,true,p.hasLineOfSight(e),rank(p,e),p.distanceTo(e))||creeperAlert(c,e)));
        boolean healthyDryClear=p.getHealth()>=19&&p.hurtTime==0&&!BorerThreats.recentlyHurt(p)
            &&!BorerThreats.shouldYieldToCombat(p)&&!p.isInWater()&&!p.isInLava()&&!p.isOnFire()
            &&safeAir(c,p.blockPosition())&&safeAir(c,p.blockPosition().above())&&c.level.noCollision(p,p.getBoundingBox())
            &&clearSeparationBody(c);
        boolean safe=separation.observe(c.level,p.tickCount,BorerCombatSeparation.safe(engine.standaloneGuard,
            Boolean.TRUE.equals(BorerFlight.meteorFlightActive()),healthyDryClear,false,otherThreat,threats));
        if(safe)separation.verifyDeferred(c.level,currentlyObserved);
        return safe;
    }
    private boolean clearSeparationBody(Minecraft c){
        var p=c.player;
        if(p==null||c.level==null||!GuardWeaponPolicy.finiteVector(p.position())
            ||!GuardWeaponPolicy.finiteVector(p.getDeltaMovement())||!GuardWeaponPolicy.finiteBox(p.getBoundingBox()))return false;
        var body=p.getBoundingBox().inflate(.02,0,.02);
        if(!GuardWeaponPolicy.finiteBox(body)||!c.level.noCollision(p,body))return false;
        for(var pos:net.minecraft.core.BlockPos.betweenClosed(net.minecraft.core.BlockPos.containing(body.minX,body.minY,body.minZ),
            net.minecraft.core.BlockPos.containing(body.maxX-1e-7,body.maxY-1e-7,body.maxZ-1e-7)))if(!safeAir(c,pos))return false;
        return true;
    }
    /** Ordinary task switches release inputs without forgetting a safely deferred same-world fight. */
    void handoff(Minecraft c){
        safetyRise.cancel();
        if(c.player!=null&&c.level!=null&&session.pending()&&separation.retain(c.level)){
            releaseControls(c);session.pause(c.player.tickCount);continuation.save(c,session);return;
        }
        end(c);
    }
	private boolean holdForMissingObservation(Minecraft c) {
		releaseControls(c);
		engine.mobs.raiseShield(c, c.player);
		engine.status = "等待重新观察热加载前的敌对生物，施工保持暂停";
		return true;
	}
	private static boolean swelling(Creeper e) { return e.isIgnited() || e.getSwellDir()>0 || e.getSwelling(1)>0; }
	private boolean creeperAlert(Minecraft c, LivingEntity e) {
		if (!(e instanceof Creeper creeper) || !e.isAlive()) return false;
		double d=c.player.distanceTo(e);
		return StandaloneCreeperPolicy.alert(c.player.hasLineOfSight(e),swelling(creeper),creeper.isPowered(),d)
			|| escaping && e==target && StandaloneCreeperPolicy.evade(swelling(creeper),creeper.isPowered(),d,true);
	}
    private boolean flightDefenseScope(){
        return StandaloneCreeperPolicy.flightDefenseScope(engine.standaloneGuard,engine.active,
            engine.mode==DefaultTunnelBorerEngine.Mode.AREA);
    }
	/** Clear the whole ascent before borrowing Flight; combat only resumes above nearby hostiles. */
	private boolean elevateBeforeCombat(Minecraft c, java.util.List<LivingEntity> threats) {
		var p = c.player;
        if (p.tickCount < riseRetryAfter && p.getHealth() >= 14) return false;
		double rise = GuardWeaponPolicy.combatRise(p.getY(), threats.stream()
			.map(e -> new GuardWeaponPolicy.Threat(e.getY(),
				BorerThreats.isRangedCombatThreat(e,p), p.distanceTo(e)))
			.toList());
		if (rise <= .25) return false;
		cancelDraw(c);rangedMode(false);engine.pauseGuardMovement(c);
		if (!clearWholeRise(c, rise)) {
            return groundDefenseAfterRiseFailure(c, "ceiling_blocked", "头顶没有安全升空通道");
		}
		try {
			escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/guard-hover-flight.bak"));
			if (escapeFlight.acquire(p) != null) {
                return groundDefenseAfterRiseFailure(c, "flight_unavailable", "无法启飞");
			}
			escaping = true;
            riseRetryAfter = 0; lastRiseFailure = "";
			if (!hoverMelee) { engine.host.enablePveMelee(); hoverMelee = true; }
			escapeFlight.speed(.16);
			c.options.keyJump.setDown(true);
			look = RotationAim.lookAt(p, target.getEyePosition());lookTick = p.tickCount;RotationAim.apply(p, look);
			engine.status = "先升空避敌，再反击 " + target.getName().getString();
			return true;
		} catch (IllegalStateException unavailable) {
            return groundDefenseAfterRiseFailure(c, "flight_failed", "升空失败");
		}
	}
    private boolean safetyRise(Minecraft c){
        var p=c.player;
        if(c.level!=combatWorld||c.screen!=null||BorerAreaRunner.physicalMovementHeld(c,c.options.keyUp,c.options.keyDown,
            c.options.keyLeft,c.options.keyRight,c.options.keyJump,c.options.keyShift,c.options.keySprint)){
            safetyRise.cancel();return false;
        }
        var observed=session.targets().stream().filter(e->e instanceof Enemy&&e.isAlive()&&e.level()==c.level
            &&c.level.getEntity(e.getId())==e&&currentServerChunk(c,e.blockPosition())).toList();
        if(observed.isEmpty()){safetyRise.cancel();return false;}
        var near=observed.stream().filter(e->GuardWeaponPolicy.safetyRiseNeeded(engine.standaloneGuard,true,true,
            session.contains(e.getUUID()),BorerThreats.isRangedCombatThreat(e,p),session.canAttack(e.getUUID()),
            p.hasLineOfSight(e),p.distanceTo(e))).min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
        double rise=safetyRise.remaining(c.level,p.getY(),p.tickCount,near!=null);
        if(rise<=.25)return false;
        if(p.tickCount<safetyRiseRetryAfter&&p.getHealth()>=14)return false;
        cancelDraw(c);releaseZombieMelee();rangedMode(true);engine.pauseGuardMovement(c);
        if(!clearWholeRise(c,rise)){
            logThreatEvidence(c,"safety-rise-blocked",near);
            return safetyDefenseAfterRiseFailure(c,"safety_column_or_entity_blocked","当前整段升空身体或远离敌人的路线不安全");
        }
        try{
            // A prior occlusion peek owns a different Flight lease. Close it before borrowing this one.
            peek.close(c);
            escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/guard-hover-flight.bak"));
            if(escapeFlight.acquire(p)!=null)return safetyDefenseAfterRiseFailure(c,"safety_flight_unavailable","无法取得当前飞行设置");
            escaping=true;hoverMelee=false;safetyRiseRetryAfter=0;lastRiseFailure="";
            escapeFlight.speed(.16);c.options.keyJump.setDown(true);
            safetyRise.attempted(p.tickCount);
            // Keep the current view: hidden/unattackable entities receive no bow/attack input.
            logThreatEvidence(c,"safety-rise",near);
            engine.status="先沿当前安全柱升空，保留未解决敌人记录";return true;
        }catch(IllegalStateException unavailable){
            return safetyDefenseAfterRiseFailure(c,"safety_flight_failed","安全升空飞行设置未确认");
        }
    }
    private boolean safetyDefenseAfterRiseFailure(Minecraft c,String code,String reason){
        safetyRiseRetryAfter=c.player.tickCount+40;
        return defendAfterRiseFailure(c,code,reason);
    }
    /** A ceiling blocks ascent, not defense. Work remains paused by the enclosing combat session. */
    private boolean groundDefenseAfterRiseFailure(Minecraft c, String code, String reason) {
        riseRetryAfter = c.player.tickCount + 40;
        return defendAfterRiseFailure(c,code,reason);
    }
    private boolean defendAfterRiseFailure(Minecraft c,String code,String reason){
        releaseEscape(c); cancelDraw(c); rangedMode(false);
        engine.mobs.raiseShield(c, c.player);
        if (!lastRiseFailure.equals(code)) {
            engine.fileLog(c, "guard-ascent-fallback reason=" + code + " action=ground_defense");
            lastRiseFailure = code;
        }
        engine.status = reason + "，保持停工并改为原地防御";
        if (GuardWeaponPolicy.riseFailureNeedsExit(c.player.getHealth()))
            return engine.host.requestEmergencyExit(c, "遇敌且" + reason);
        return false; // Continue the existing melee/bow path, including its visibility and ammunition checks.
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
                &&e.level()==c.level&&c.level.getEntity(e.getId())==e
                &&(GuardWeaponPolicy.safetyRiseNeeded(engine.standaloneGuard,true,true,
                    session.contains(e.getUUID())||BorerThreats.currentReceivedMobHit(e,p),BorerThreats.isRangedCombatThreat(e,p),
                    session.canAttack(e.getUUID()),p.hasLineOfSight(e),p.distanceTo(e))
                    ||p.distanceTo(e) <= (BorerThreats.isRangedCombatThreat(living,p) ? 12 : 9)
				    && (p.hasLineOfSight(e) || p.distanceTo(e) < 3)));
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
    private boolean onlyZombiesNearby(Minecraft c,java.util.List<LivingEntity> nearby){
        boolean found=false;
        for(var mob:nearby){
            if(!mob.isAlive()||c.level.getEntity(mob.getId())!=mob)continue;
            if(BorerThreats.isRangedCombatThreat(mob,c.player))return false;
            if(c.player.distanceTo(mob)>12)continue;
            if(!ordinaryZombie(c.player,mob))return false;
            found=true;
        }
        return found;
    }
    private static boolean ordinaryZombie(net.minecraft.client.player.LocalPlayer p,LivingEntity mob) {
        return GuardWeaponPolicy.ordinaryZombie(
            net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(mob.getType()).toString(),
            BorerThreats.isRangedCombatThreat(mob,p));
    }
    private boolean durableSwordAvailable(Minecraft c){
        for(int slot=0;slot<36;slot++){
            var stack=c.player.getInventory().getItem(slot);
            if(BorerItems.isSwordWithReserve(stack,GuardWeaponPolicy.SWORD_RESERVE))return true;
        }
        return false;
    }
    /** Move at most a few collision-checked hover steps; never borrow material navigation. */
    private boolean swordZombieFromHover(Minecraft c,java.util.List<LivingEntity> nearby){
        var p=c.player;
        if(p.getHealth()<19||p.hurtTime>0||p.isInWater()||p.isInLava()||p.isOnFire()
                ||!durableSwordAvailable(c)||p.distanceTo(target)>=9||!p.hasLineOfSight(target)){
            zombieApproach.reset();releaseZombieMelee();return false;
        }
        double highest=nearby.stream().filter(e->ordinaryZombie(p,e)
                &&e.isAlive()&&p.distanceTo(e)<=12).mapToDouble(LivingEntity::getY).max().orElse(target.getY());
        double safeFeet=highest+3.0;
        double horizontal=Math.hypot(target.getX()-p.getX(),target.getZ()-p.getZ());
        if(horizontal>9.0){
            var unavailable=zombieApproach.step(target.getUUID(),p.tickCount,p.getX(),p.getZ(),
                target.getX(),target.getZ(),false,true,false);
            if(!unavailable.reason().equals("retry_cooldown"))engine.fileLog(c,"guard-zombie-approach-unavailable reason="+unavailable.reason());
            return false;
        }
        double projectedFeet=p.getY()+Math.min(0,p.getDeltaMovement().y)*10;
        double rise=Math.max(0,safeFeet-p.getY());
        double verticalStep=GuardWeaponPolicy.hoverVerticalStep(p.getY(),projectedFeet,highest);
        boolean columnClear=verticalStep>=0 ? rise<=0||clearWholeRise(c,rise)
            : clearZombieVerticalStep(c,verticalStep,highest);
        var choice=GuardWeaponPolicy.hover(projectedFeet,highest,columnClear);
        if(choice==GuardWeaponPolicy.Hover.FALLBACK){zombieApproach.reset();releaseZombieMelee();return false;}
        try{
            escapeFlight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/guard-hover-flight.bak"));
            if(escapeFlight.acquire(p)!=null){releaseZombieMelee();return false;}
            escaping=true;
            cancelDraw(c);engine.pauseGuardMovement(c);
            if(choice==GuardWeaponPolicy.Hover.RISE || choice==GuardWeaponPolicy.Hover.DESCEND){
                releaseZombieMelee(); hoverMelee=false; rangedMode(true);
                escapeFlight.speed(Math.abs(verticalStep)/5);
                c.options.keyJump.setDown(verticalStep>0);
                c.options.keyShift.setDown(verticalStep<0);
                engine.status=verticalStep<0 ? "缓降到僵尸头顶安全高度，再交给杀戮光环" : "先升高避开僵尸，再交给杀戮光环";
                return true;
            }
            escapeFlight.hover();
            if(!BorerItems.selectWeapon(c,p,GuardWeaponPolicy.SWORD_RESERVE)
                    ||c.level.getEntity(target.getId())!=target||!target.isAlive()||!p.hasLineOfSight(target)){
                releaseZombieMelee();releaseEscape(c);return false;
            }
            boolean safeHover=GuardWeaponPolicy.safeHoverHeight(
                Boolean.TRUE.equals(BorerFlight.meteorFlightActive()),p.getY(),projectedFeet,highest);
            double reach=Math.sqrt(target.getBoundingBox().distanceToSqr(p.getEyePosition()));
            boolean attackReach=GuardWeaponPolicy.swordHoverReady(true,
                Boolean.TRUE.equals(BorerFlight.meteorFlightActive()),
                BorerItems.isSwordWithReserve(p.getMainHandItem(),GuardWeaponPolicy.SWORD_RESERVE),
                p.getY(),projectedFeet,highest,reach,p.entityInteractionRange());
            double dx=target.getX()-p.getX(),dz=target.getZ()-p.getZ();
            double distance=Math.hypot(dx,dz);
            Vec3 destination=distance<.001?p.position():new Vec3(
                target.getX()-dx/distance*.7,p.getY(),target.getZ()-dz/distance*.7);
            var input=BorerFlyPath.input(p.position(),destination,p.getYRot());
            boolean clearStep=input.forward()&&clearZombieApproachStep(c,input.delta());
            var step=zombieApproach.step(target.getUUID(),p.tickCount,p.getX(),p.getZ(),
                target.getX(),target.getZ(),attackReach,safeHover,clearStep);
            if(step.decision()==GuardZombieApproach.Decision.UNAVAILABLE){
                if(!step.reason().equals("retry_cooldown"))
                    engine.fileLog(c,"guard-zombie-approach-unavailable reason="+step.reason());
                releaseZombieMelee();releaseEscape(c);return false;
            }
            if(step.decision()==GuardZombieApproach.Decision.MOVE){
                releaseZombieMelee(); hoverMelee=false; rangedMode(true);
                escapeFlight.speed(GuardZombieApproach.sprintSafeSpeed(input.speed()));
                look=new RotationAim.Look(input.yaw(),0);lookTick=p.tickCount;RotationAim.apply(p,look);
                c.options.keyUp.setDown(true);
                engine.status="安全悬停靠近僵尸，路径逐格核验";return true;
            }
            engine.mobs.lowerShield(c);
            if(p.isUsingItem()&&p.getUseItem().is(Items.SHIELD))p.stopUsingItem();
            // The installed host already exposes the verified Meteor target lease.
            // Never disable its aura or overwrite its rotation while it owns melee.
            boolean meteorReady=false, stalled=false;
            if(!zombieMeleeFallback) {
                rangedMode(false);
                zombieMeleeLease=true;
                meteorReady=BorerMeteorThreatLease.acquire(engine.host,c,target);
                stalled=zombieMeleeProgress.stalled(target.getUUID(),p.tickCount,target.getHealth());
            }
            if(zombieMeleeFallback || !meteorReady || stalled) {
                if(!zombieMeleeFallback)engine.fileLog(c,"guard-zombie-melee-owner id="+target.getId()
                    +" meteorReady="+meteorReady+" noDamageGraceExpired="+stalled+" fallback=true");
                zombieMeleeFallback=true; hoverMelee=false; rangedMode(true);
                look=RotationAim.lookAt(p,target.getEyePosition());lookTick=p.tickCount;RotationAim.apply(p,look);
                if(p.getAttackStrengthScale(0)>=.95F){
                    c.gameMode.attack(p,target);p.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
                }
                engine.status="安全悬停，杀戮光环无进展后用剑反击 "+target.getName().getString();
            } else {
                hoverMelee=true;look=null;
                engine.status="安全悬停，杀戮光环用剑清除 "+target.getName().getString()+"；施工暂停";
            }
            return true;
        }catch(IllegalStateException unavailable){releaseZombieMelee();releaseEscape(c);return false;}
    }
    private boolean clearZombieVerticalStep(Minecraft c,double delta,double highest) {
        if(!Double.isFinite(delta)||Math.abs(delta)>.151||c.player.getY()+delta<highest+3.0)return false;
        var swept=c.player.getBoundingBox().expandTowards(0,delta,0).inflate(.02);
        if(!c.level.noCollision(c.player,swept))return false;
        for(var pos:net.minecraft.core.BlockPos.betweenClosed(
                net.minecraft.core.BlockPos.containing(swept.minX,swept.minY,swept.minZ),
                net.minecraft.core.BlockPos.containing(swept.maxX,swept.maxY,swept.maxZ)))
            if(!safeAir(c,pos))return false;
        return true;
    }
    private boolean clearZombieApproachStep(Minecraft c,Vec3 delta){
        if(Math.abs(delta.y)>1e-6||delta.horizontalDistanceSqr()>.201*.201)return false;
        var swept=c.player.getBoundingBox().expandTowards(delta).inflate(.02);
        if(!c.level.noCollision(c.player,swept))return false;
        for(var pos:net.minecraft.core.BlockPos.betweenClosed(
                net.minecraft.core.BlockPos.containing(swept.minX,swept.minY,swept.minZ),
                net.minecraft.core.BlockPos.containing(swept.maxX,swept.maxY,swept.maxZ)))
            if(!safeAir(c,pos))return false;
        return true;
    }
    private boolean clearWholeRise(Minecraft c,double rise){
        if(c.player==null||c.level==null||!Double.isFinite(rise)||rise<0
            ||!GuardWeaponPolicy.finiteVector(c.player.position())||!GuardWeaponPolicy.finiteVector(c.player.getDeltaMovement())
            ||!GuardWeaponPolicy.finiteBox(c.player.getBoundingBox()))return false;
        var swept=c.player.getBoundingBox().expandTowards(0,rise+.15,0);
        if(!GuardWeaponPolicy.finiteBox(swept)||swept.maxY>=319||!c.level.noCollision(c.player,swept))return false;
        for(var pos:net.minecraft.core.BlockPos.betweenClosed(net.minecraft.core.BlockPos.containing(swept.minX,swept.minY,swept.minZ),
            net.minecraft.core.BlockPos.containing(swept.maxX-1e-7,swept.maxY-1e-7,swept.maxZ-1e-7)))if(!safeAir(c,pos))return false;
        for(var entity:c.level.getEntities(c.player,swept.inflate(40))){
            if(!(entity instanceof LivingEntity)||!(entity instanceof Enemy)||!entity.isAlive())continue;
            if(entity.level()!=c.level||c.level.getEntity(entity.getId())!=entity
                ||!GuardWeaponPolicy.finiteVector(entity.position())||!GuardWeaponPolicy.finiteBox(entity.getBoundingBox()))return false;
            if(GuardWeaponPolicy.boxDistanceSquared(swept,entity.getBoundingBox())>12*12)continue;
            if(!currentServerChunk(c,entity.blockPosition()))return false;
            double radius=entity instanceof Creeper creeper?(creeper.isPowered()?12:6):
                BorerThreats.isRangedCombatThreat(entity,c.player)?12:9;
            if(!GuardWeaponPolicy.riseThreatClear(c.player.getBoundingBox(),swept,entity.getBoundingBox(),radius))return false;
        }
        return true;
    }
    private boolean currentServerChunk(Minecraft c,net.minecraft.core.BlockPos pos){
        if(c.level==null)return false;
        var chunk=c.level.getChunkSource().getChunk(pos.getX()>>4,pos.getZ()>>4,
            net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    /** Real observations only; changing status is logged once, steady states at most every two seconds. */
    private void logThreatEvidence(Minecraft c,String stage,LivingEntity hinted){
        if(c.player==null||c.level==null)return;
        var p=c.player;LivingEntity mob=hinted;
        if(mob==null)mob=session.targets().stream().filter(e->e.level()==c.level&&c.level.getEntity(e.getId())==e&&e.isAlive())
            .min(java.util.Comparator.comparingDouble(p::distanceTo)).orElse(null);
        boolean current=mob!=null&&mob.level()==c.level&&c.level.getEntity(mob.getId())==mob&&mob.isAlive();
        boolean visible=current&&p.hasLineOfSight(mob),attack=current&&session.canAttack(mob.getUUID());
        String reason=!current?"unknown_current_entity":!visible?"no_los":
            !attackEligible(c,mob)?"outside_attack_distance":
            !attack?"unresolved_attack_budget":"attack_available";
        String key=stage+'|'+(current?mob.getUUID():"unknown")+'|'+reason;
        if(key.equals(evidenceLogKey)&&(long)p.tickCount-evidenceLogTick<40)return;
        evidenceLogKey=key;evidenceLogTick=p.tickCount;
        var source=p.getLastDamageSource();var direct=source==null?null:source.getDirectEntity();var owner=source==null?null:source.getEntity();
        boolean directCurrent=direct!=null&&direct.level()==c.level&&c.level.getEntity(direct.getId())==direct;
        boolean ownerCurrent=owner!=null&&owner.level()==c.level&&c.level.getEntity(owner.getId())==owner&&owner.isAlive();
        engine.fileLog(c,"guard-threat-evidence stage="+stage+" current_entity="+current+" reason="+reason
            +" player="+p.position()+" player_box="+p.getBoundingBox()+" health="+p.getHealth()
            +" player_main="+net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(p.getMainHandItem().getItem())
            +" player_off="+net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(p.getOffhandItem().getItem())
            +" using_shield="+p.getUseItem().is(Items.SHIELD)
            +(current?" id="+mob.getId()+" uuid="+mob.getUUID()+" mob="+mob.position()+" mob_box="+mob.getBoundingBox()
                +" mob_main="+net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(mob.getMainHandItem().getItem())
                +" mob_off="+net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(mob.getOffhandItem().getItem())
                +" mob_health="+mob.getHealth()+" ranged="+BorerThreats.isRangedCombatThreat(mob,p)+" distance="+p.distanceTo(mob)
                +" visible="+visible+" can_attack="+attack:" mob=unknown")
            +" damage_msg="+(source==null?"unknown":source.getMsgId())
            +" damage_trident="+(source!=null&&source.is(net.minecraft.world.damagesource.DamageTypes.TRIDENT))
            +" direct_current="+directCurrent+" direct="+(directCurrent?direct.getId()+":"+direct.getUUID():"unknown")
            +" owner_current="+ownerCurrent+" owner="+(ownerCurrent?owner.getId()+":"+owner.getUUID():"unknown")
            +" fixed_rise_target="+(Double.isFinite(safetyRise.target())?safetyRise.target():"unplanned")
            +" unresolved="+session.targets().size());
    }
	private boolean clearRise(Minecraft c){
		if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(0,1.1,0)))return false;
		for(int i=1;i<=3;i++)if(!safeAir(c,c.player.blockPosition().above(i)))return false;
		return true;
	}
	private boolean safeAir(Minecraft c,net.minecraft.core.BlockPos p){
		if(!currentServerChunk(c,p))return false;var s=c.level.getBlockState(p);
		return s.getFluidState().isEmpty()&&!s.is(net.minecraft.world.level.block.Blocks.FIRE)&&!s.is(net.minecraft.world.level.block.Blocks.SOUL_FIRE)&&!s.is(net.minecraft.world.level.block.Blocks.COBWEB)&&!s.is(net.minecraft.world.level.block.Blocks.POWDER_SNOW);
	}
	private void releaseEscape(Minecraft c){
		if(!escaping)return;engine.pauseGuardMovement(c);
		if(c.player!=null&&!c.player.onGround())escapeFlight.closeKeepingFlight();else escapeFlight.close();
		escaping=false;escapeFlightFailed=false;hoverMelee=false;
	}
	private static int rank(net.minecraft.client.player.LocalPlayer p,LivingEntity e) {
		return BorerDefensePolicy.priority(e instanceof Creeper,
            BorerThreats.isRangedCombatThreat(e,p));
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
    boolean usableGuardBow(Minecraft c){
        if(c.player==null)return false;
        for(int i=0;i<36;i++){
            var stack=c.player.getInventory().getItem(i);
            if(usableBow(stack)&&!c.player.getProjectile(stack).isEmpty())return true;
        }
        return false;
    }
    private boolean attackEligible(Minecraft c,LivingEntity enemy){
        var p=c.player;boolean visible=p.hasLineOfSight(enemy);double distance=p.distanceTo(enemy);
        if(BorerDefensePolicy.eligible(true,enemy.isAlive(),visible,rank(p,enemy),distance))return true;
        return rank(p,enemy)==2&&BorerDefensePolicy.trackedBowEligible(enemy instanceof Enemy,
            enemy.isAlive(),visible,session.contains(enemy.getUUID()),usableGuardBow(c),distance);
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
        safetyRise.cancel();
		if (c.player != null) trialCreeperMelee.pause(c.player.tickCount);
		if (c.player != null) trialCreeperFlight.pause(c.player.tickCount);
		if (c.player != null) session.pause(c.player.tickCount);
		if (c.player != null && c.player.isUsingItem() && c.player.getUseItem().is(Items.BOW)) {
			c.player.stopUsingItem();
			c.options.keyUse.setDown(false);
		}
		drawing = false; releasePending = false; look = null; viewGate.reset(); viewWaitTicks = 0;
	}
	void end(Minecraft c) {
		trialCreeperMelee.reset();trialCreeperEvidence="";
		trialCreeperFlight.reset();trialCreeperFlightEvidence="";trialCreeperRoute=java.util.List.of();trialCreeperRouteGoal=null;trialCreeperRouteTarget=null;
        safetyRise.clear();evidenceLogKey="";evidenceLogTick=Integer.MIN_VALUE;
        riseRetryAfter = safetyRiseRetryAfter = 0; lastRiseFailure = "";
		session.clear(); continuation.clear(); separation.clear(); combatWorld=null; holdReason = "";
        miningMeleeProgress.clear(); miningMeleeFallback = false;
		releaseControls(c);
	}
	/** A menu suspends input, not our knowledge of the unfinished fight. */
	void pause(Minecraft c) {
        safetyRise.cancel();
		if (c.player != null) trialCreeperMelee.pause(c.player.tickCount);
		if (c.player != null) trialCreeperFlight.pause(c.player.tickCount);
		if (c.player != null) session.pause(c.player.tickCount);
		releaseControls(c);
	}
    private void resetMiningMelee() {
        rangedMode(false);
        releaseMiningMelee();
        miningMeleeProgress.clear();
        miningMeleeFallback = false;
    }
    private void releaseZombieMelee() {
        if(zombieMeleeLease)BorerMeteorThreatLease.release(engine.host);
        zombieMeleeLease=false;zombieMeleeFallback=false;zombieMeleeProgress.clear();
    }
    private void releaseMiningMelee() {
        if (!miningMeleeLease) return;
        BorerMeteorThreatLease.release(engine.host);
        miningMeleeLease = false;
    }
	private void releaseControls(Minecraft c) {
		zombieApproach.reset();
        releaseZombieMelee();
		peek.close(c);
        rangedMode(false);
        releaseMiningMelee();
		if (target == null && !drawing && previousSlot < 0 && !escaping) return;
		releaseEscape(c);
		cancelDraw(c);
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
		engine.fileLog(c, "area-defense-shot id=" + target.getId() + " rank=" + rank(c.player,target) + " visible=true look=" + look
			+ " target=" + target.position() + " " + engine.host.borerBowDiagnostics());
		return true;
	}
}
