package dev.twob2tkit.runtime.engine;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.damagesource.DamageTypes;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.monster.EnderMan;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;

import java.util.Set;

/** 按玩家套装判断附近怪物要不要停手。钻石/下界合金套不怕骷髅这类常规怪。 */
public final class BorerThreats {
	/** 护甲档：无 / 铁 / 钻石 / 下界合金，决定常规怪是否停挖。 */
	public enum ArmorTier {
		NONE,
		IRON,
		DIAMOND,
		NETHERITE
	}

	private static final Set<String> ALWAYS_DANGEROUS = Set.of(
		"creeper", "wither", "warden", "ravager", "wither_skeleton",
		"piglin_brute", "ghast", "elder_guardian", "ender_dragon", "hoglin", "magma_cube"
	);

	private static final Set<String> ROUTINE_FOR_DIAMOND = Set.of(
		"skeleton", "stray", "bogged", "zombie", "husk", "drowned", "zombie_villager",
		"spider", "cave_spider", "witch", "slime", "phantom",
		"silverfish", "endermite", "pillager", "enderman", "vindicator"
	);

	private static final Set<String> ROUTINE_FOR_IRON = Set.of(
		"zombie", "husk", "drowned", "zombie_villager", "spider"
	);

	private static final Set<String> RANGED_COMBAT = Set.of(
		"skeleton", "stray", "bogged", "pillager", "blaze", "ghast", "witch", "shulker", "breeze"
	);

	private BorerThreats() {
	}

	/** 根据四件护甲判断当前套装档次。钻石与下界合金可混穿。 */
	static ArmorTier armorTier(LocalPlayer player) {
		int netherite = 0;
		int diamond = 0;
		int iron = 0;
		for (EquipmentSlot slot : new EquipmentSlot[]{
			EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET
		}) {
			Item item = player.getItemBySlot(slot).getItem();
			if (isNetheriteArmor(item)) netherite++;
			else if (isDiamondArmor(item)) diamond++;
			else if (isIronArmor(item)) iron++;
		}
		if (netherite == 4) return ArmorTier.NETHERITE;
		if (netherite + diamond >= 4) return ArmorTier.DIAMOND;
		if (netherite + diamond + iron >= 4) return ArmorTier.IRON;
		return ArmorTier.NONE;
	}

	/** 刚挨打：必须有还在附近的攻击者，岩浆块/火/掉落不算挨打。 */
	public static boolean shouldYieldToCombat(LocalPlayer player) {
		return currentHurtIsFromMob(player) || recentAttackerNearby(player, 12.0);
	}

	/** hurtTime 是否刚亮。 */
	public static boolean recentlyHurt(LocalPlayer player) {
		return player.hurtTime > 0 || player.invulnerableTime > 10;
	}

	/** 是否刚被怪打（非环境）。 */
	public static boolean recentlyHurtByMob(LocalPlayer player) {
		return currentHurtIsFromMob(player);
	}

	/** 伤害源是否环境类。 */
	public static boolean isEnvironmental(DamageSource source) {
		if (source == null) return false;
		return source.is(DamageTypes.HOT_FLOOR)
			|| source.is(DamageTypes.LAVA)
			|| source.is(DamageTypes.IN_FIRE)
			|| source.is(DamageTypes.ON_FIRE)
			|| source.is(DamageTypes.CAMPFIRE)
			|| source.is(DamageTypes.DROWN)
			|| source.is(DamageTypes.STARVE)
			|| source.is(DamageTypes.CACTUS)
			|| source.is(DamageTypes.FALL)
			|| source.is(DamageTypes.SWEET_BERRY_BUSH)
			|| source.is(DamageTypes.FREEZE)
			|| source.is(DamageTypes.DRY_OUT);
	}

	/** 环境伤害中文名。 */
	public static String environmentalLabel(DamageSource source) {
		if (source == null) return "环境伤害";
		if (source.is(DamageTypes.HOT_FLOOR)) return "岩浆块";
		if (source.is(DamageTypes.LAVA)) return "岩浆";
		if (source.is(DamageTypes.IN_FIRE) || source.is(DamageTypes.ON_FIRE) || source.is(DamageTypes.CAMPFIRE)) {
			return "火";
		}
		if (source.is(DamageTypes.DROWN)) return "溺水";
		if (source.is(DamageTypes.FALL)) return "摔落";
		if (source.is(DamageTypes.CACTUS)) return "仙人掌";
		if (source.is(DamageTypes.SWEET_BERRY_BUSH)) return "甜浆果丛";
		if (source.is(DamageTypes.STARVE)) return "饥饿";
		if (source.is(DamageTypes.FREEZE)) return "冰冻";
		if (source.is(DamageTypes.DRY_OUT)) return "干涸";
		String id = source.getMsgId();
		return id == null || id.isBlank() ? "环境伤害" : id;
	}

	/** 本下伤害是否来自怪。 */
	public static boolean currentHurtIsFromMob(LocalPlayer player) {
		DamageSource source = player.getLastDamageSource();
		LivingEntity attacker = player.getLastHurtByMob();
		int since = attacker == null ? Integer.MAX_VALUE : player.tickCount - player.getLastHurtByMobTimestamp();
		boolean env = isEnvironmental(source);
		if (!env && standingOnMagma(player) && since > BorerCombatPolicy.MOB_HIT_WINDOW) {
			env = true;
		}
		return BorerCombatPolicy.treatAsMobHit(recentlyHurt(player), env, since);
	}

	/** 是否站在岩浆块上。 */
	private static boolean standingOnMagma(LocalPlayer player) {
		if (player == null || player.level() == null) return false;
		return player.level().getBlockState(player.blockPosition().below()).is(Blocks.MAGMA_BLOCK);
	}

	/** 最近打你的怪是否还在半径内。 */
	public static boolean recentAttackerNearby(LocalPlayer player, double radius) {
		if (isEnvironmental(player.getLastDamageSource())) return false;
		var attacker = player.getLastHurtByMob();
		if (attacker == null || !attacker.isAlive()) return false;
		if (player.tickCount - player.getLastHurtByMobTimestamp() > 60) return false;
		return player.distanceTo(attacker) <= radius;
	}

	/** 因战斗停挖的原因文案；无则 null。 */
	public static String combatPauseReason(LocalPlayer player) {
		if (isEnvironmental(player.getLastDamageSource())) return null;
		if (standingOnMagma(player) && !currentHurtIsFromMob(player)) return null;
		if (!BorerCombatPolicy.pauseMiningForCombat(currentHurtIsFromMob(player))
			&& !recentAttackerNearby(player, 12.0)) {
			return null;
		}
		var attacker = player.getLastHurtByMob();
		String name = attacker != null && attacker.isAlive() ? attacker.getName().getString() : null;
		if (name == null) {
			DamageSource source = player.getLastDamageSource();
			if (source != null && source.getEntity() instanceof LivingEntity living && living.isAlive()) {
				name = living.getName().getString();
			}
		}
		if (name == null) return null;
		if (currentHurtIsFromMob(player)) return "被" + name + "打了";
		if (recentAttackerNearby(player, 12.0)) return "刚被" + name + "打过";
		return null;
	}

	/**
	 * 玩家这一拍的装备快照。扫一圈怪物只需要算一次，不必每个实体都重新遍历装备槽。
	 * 是不可变值对象，不是静态缓存——引擎类会热加载，静态可变状态在这里不安全。
	 */
	public record Loadout(ArmorTier tier, boolean gold) {
	}

	/** 根据护甲推断装备档。 */
	static Loadout loadout(LocalPlayer player) {
		return new Loadout(armorTier(player), wearingGold(player));
	}

	/** 苦力怕单独处理。钻石套仍会停手的：凋灵、监守者、苦力怕、岩浆怪、没金装的猪灵等。 */
	static boolean shouldPauseMining(Entity entity, LocalPlayer player) {
		return shouldPauseMining(entity, loadout(player));
	}

	/** 该实体是否该让我们停挖。 */
	static boolean shouldPauseMining(Entity entity, Loadout loadout) {
		if (!(entity instanceof Enemy) || !entity.isAlive()) return false;
		if (entity instanceof Creeper) return false;
		if (!isCombatHostile(entity, loadout)) return false;
		String type = typeId(entity);
		if (ALWAYS_DANGEROUS.contains(type)) return true;
		ArmorTier tier = loadout.tier();
		if (tier == ArmorTier.DIAMOND || tier == ArmorTier.NETHERITE) return !ROUTINE_FOR_DIAMOND.contains(type);
		if (tier == ArmorTier.IRON) return !ROUTINE_FOR_IRON.contains(type);
		return true;
	}

	/**
	 * 旁边有会打人的敌对就停挖。钻石/下界合金套也不把骷髅僵尸当没事。
	 * 没被激怒的僵尸猪灵、金装猪灵、没盯人的末影人仍不算。
	 */
	static boolean shouldYieldWhenNearby(Entity entity, Loadout loadout) {
		if (!(entity instanceof Enemy) || !entity.isAlive()) return false;
		return isCombatHostile(entity, loadout);
	}

	/** 会远程输出的怪：贴近前举盾，通道里也要拐弯躲开。 */
	public static boolean isRangedCombatThreat(Entity entity) {
		if (entity == null || !entity.isAlive()) return false;
		return isRangedCombatType(typeId(entity));
	}

	/** 类型 id 是否远程威胁。 */
	public static boolean isRangedCombatType(String type) {
		return type != null && RANGED_COMBAT.contains(type);
	}

	/** 通道扫描：远程怪一律算威胁；其余仍按装甲过滤。 */
	static boolean shouldAvoidInCorridor(Entity entity, Loadout loadout) {
		if (entity instanceof Creeper) return true;
		if (isRangedCombatThreat(entity)) return shouldYieldWhenNearby(entity, loadout);
		return shouldPauseMining(entity, loadout);
	}

	/** 是否算交战敌对。 */
	private static boolean isCombatHostile(Entity entity, Loadout loadout) {
		String type = typeId(entity);
		// 中立怪：没被激怒就不算威胁，否则下界挖矿会被满地僵尸猪灵打断。
		if (type.equals("zombified_piglin")) return entity instanceof Mob mob && mob.isAggressive();
		if (type.equals("piglin")) return !loadout.gold();
		if (type.equals("enderman") && entity instanceof EnderMan enderman && !enderman.isCreepy()) return false;
		return true;
	}

	/** 是否穿金装（猪灵中立）。 */
	private static boolean wearingGold(LocalPlayer player) {
		for (EquipmentSlot slot : new EquipmentSlot[]{
			EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET, EquipmentSlot.OFFHAND, EquipmentSlot.MAINHAND
		}) {
			Item item = player.getItemBySlot(slot).getItem();
			if (isGoldGear(item)) return true;
		}
		return false;
	}

	/** 物品是否金质装备。 */
	private static boolean isGoldGear(Item item) {
		return item == Items.GOLDEN_HELMET || item == Items.GOLDEN_CHESTPLATE
			|| item == Items.GOLDEN_LEGGINGS || item == Items.GOLDEN_BOOTS
			|| item == Items.GOLDEN_SWORD || item == Items.GOLDEN_AXE
			|| item == Items.GOLDEN_PICKAXE || item == Items.GOLD_INGOT;
	}

	/** 实体类型注册名。 */
	private static String typeId(Entity entity) {
		return BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).getPath();
	}

	/** 是否钻石头盔/甲。 */
	private static boolean isDiamondArmor(Item item) {
		return item == Items.DIAMOND_HELMET || item == Items.DIAMOND_CHESTPLATE
			|| item == Items.DIAMOND_LEGGINGS || item == Items.DIAMOND_BOOTS;
	}

	/** 是否下界合金甲。 */
	private static boolean isNetheriteArmor(Item item) {
		return item == Items.NETHERITE_HELMET || item == Items.NETHERITE_CHESTPLATE
			|| item == Items.NETHERITE_LEGGINGS || item == Items.NETHERITE_BOOTS;
	}

	/** 是否铁甲。 */
	private static boolean isIronArmor(Item item) {
		return item == Items.IRON_HELMET || item == Items.IRON_CHESTPLATE
			|| item == Items.IRON_LEGGINGS || item == Items.IRON_BOOTS;
	}
}
