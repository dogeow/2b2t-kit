package dev.twob2tkit.mixin;

import net.minecraft.world.entity.projectile.FishingHook;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/**
 * 访问器 Mixin：目标 {@link FishingHook} 的私有字段 {@code biting}。
 * <p>
 * 无 {@code @Inject}；通过 {@link Accessor} 把咬钩状态暴露给自动钓鱼，
 * 以便在鱼咬钩时及时收杆。不改字段语义，只读访问。
 */
@Mixin(FishingHook.class)
public interface FishingHookBiteAccess {
	/** 当前浮标是否处于咬钩状态。 */
	@Accessor("biting")
	boolean kit$biting();
}
