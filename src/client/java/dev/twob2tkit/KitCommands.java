package dev.twob2tkit;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.BoolArgumentType;
import com.mojang.brigadier.arguments.DoubleArgumentType;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;

import java.util.Locale;

import static net.fabricmc.fabric.api.client.command.v2.ClientCommands.argument;
import static net.fabricmc.fabric.api.client.command.v2.ClientCommands.literal;
import dev.twob2tkit.borer.BorerAreaMarks;
import dev.twob2tkit.borer.BorerAreaProjects;
import dev.twob2tkit.borer.TunnelBorer;
import dev.twob2tkit.builder.MachineBuilder;

/** `/twob2tkit` 客户端指令，从入口类拆出以免 Client 继续变长。 */
final class KitCommands {
	private KitCommands() {
	}

	/** 注册 /twob2tkit 及其子命令。 */
	static void register(
		CommandDispatcher<FabricClientCommandSource> dispatcher,
		KitConfig config,
		KitController controller,
		MachineBuilder machineBuilder
	) {
		dispatcher.register(
			literal("twob2tkit")
				.executes(context -> help(context.getSource()))
				.then(literal("help").executes(context -> help(context.getSource())))
				.then(literal("scenery")
					.executes(context -> { context.getSource().getClient().setScreen(new SceneryScreen(null, config)); return 1; })
					.then(literal("start").then(argument("radius", IntegerArgumentType.integer(16, 4096)).executes(context -> {
						int radius = IntegerArgumentType.getInteger(context, "radius");
						boolean ok = KitClient.startScenery(context.getSource().getClient(), radius, false);
						if (ok) { config.sceneryRadiusBlocks = radius; config.save(); }
						else context.getSource().sendError(Component.literal(KitClient.borer().sceneryStatus()));
						return ok ? 1 : 0;
					})))
					.then(literal("resume").executes(context -> KitClient.startScenery(context.getSource().getClient(), config.sceneryRadiusBlocks, true) ? 1 : 0))
					.then(literal("stop").executes(context -> { if (KitClient.borer().isSceneryActive()) KitClient.borer().stop(context.getSource().getClient(), "手动暂停风景预加载"); return 1; }))
					.then(literal("status").executes(context -> { context.getSource().sendFeedback(Component.literal(KitClient.borer().sceneryStatus())); return 1; })))
				.then(literal("gui").executes(context -> {
					dev.twob2tkit.automation.AutomationBridge.requestGui();
					return 1;
				}))
				.then(literal("start")
					.then(argument("x", DoubleArgumentType.doubleArg())
						.then(argument("z", DoubleArgumentType.doubleArg())
							.then(argument("y", DoubleArgumentType.doubleArg(-64.0, 2048.0))
								.executes(context -> {
									controller.start(
										context.getSource().getClient(),
										DoubleArgumentType.getDouble(context, "x"),
										DoubleArgumentType.getDouble(context, "z"),
										DoubleArgumentType.getDouble(context, "y")
									);
									return 1;
								})
							)
						)
					)
				)
				.then(literal("resume").executes(context -> {
					if (!controller.resume(context.getSource().getClient())) {
						context.getSource().sendError(Component.literal("还没有保存过目标，请先使用 /twob2tkit start <x> <z> <y>"));
						return 0;
					}
					return 1;
				}))
				.then(literal("stop").executes(context -> {
					KitClient.emergencyStop("命令停止全部");
					return 1;
				}))
				.then(literal("status").executes(context -> status(context.getSource(), config, controller)))
				.then(literal("reload").executes(context -> {
					TunnelBorer.ReloadResult result = KitClient.reloadBorerRuntime(context.getSource().getClient(), false);
					if (result.success()) context.getSource().sendFeedback(Component.literal(result.message()));
					else context.getSource().sendError(Component.literal(result.message()));
					return result.success() ? 1 : 0;
				}))
				.then(literal("villagers").executes(context -> {
					KitClient.toggleVillagerScan(context.getSource().getClient());
					return 1;
				}))
				.then(literal("print").executes(context -> {
					machineBuilder.toggle(context.getSource().getClient());
					return 1;
				}))
				.then(literal("set")
					.then(literal("arrival")
						.then(argument("blocks", DoubleArgumentType.doubleArg(1.0, 128.0)).executes(context -> {
							config.arrivalRadius = DoubleArgumentType.getDouble(context, "blocks");
							return saved(context.getSource(), config, "到达半径", config.arrivalRadius);
						})))
					.then(literal("player-radius")
						.then(argument("blocks", DoubleArgumentType.doubleArg(0.0, 256.0)).executes(context -> {
							config.playerRadius = DoubleArgumentType.getDouble(context, "blocks");
							return saved(context.getSource(), config, "陌生玩家保护半径", config.playerRadius);
						})))
					.then(literal("min-health")
						.then(argument("health", DoubleArgumentType.doubleArg(0.0, 20.0)).executes(context -> {
							config.minHealth = DoubleArgumentType.getDouble(context, "health");
							return saved(context.getSource(), config, "最低生命值", config.minHealth);
						})))
					.then(literal("stuck-seconds")
						.then(argument("seconds", IntegerArgumentType.integer(0, 600)).executes(context -> {
							config.stuckSeconds = IntegerArgumentType.getInteger(context, "seconds");
							config.save();
							context.getSource().sendFeedback(Component.literal("已保存：卡住保护 " + config.stuckSeconds + " 秒（0 为关闭）"));
							return 1;
						})))
					.then(literal("disconnect-on-arrival")
						.then(argument("enabled", BoolArgumentType.bool()).executes(context -> {
							config.disconnectOnArrival = BoolArgumentType.getBool(context, "enabled");
							config.save();
							context.getSource().sendFeedback(Component.literal("已保存：到达后自动离线 " + config.disconnectOnArrival));
							return 1;
						})))
				)
				.then(literal("area")
					.executes(context -> {
						context.getSource().sendFeedback(Component.literal("区域：" + BorerAreaMarks.sizeLabel(config)
							+ "。工程 " + config.areaProjects.size() + " 个。"
							+ " area a|b [x y z] · area save [名] · area load <名> · area list · area start"));
						return 1;
					})
					.then(literal("a").executes(context -> areaLook(context.getSource(), config, 1))
						.then(argument("x", IntegerArgumentType.integer(-30_000_000, 30_000_000))
							.then(argument("y", IntegerArgumentType.integer(-64, 320))
								.then(argument("z", IntegerArgumentType.integer(-30_000_000, 30_000_000))
									.executes(context -> {
										BorerAreaMarks.setA(config, new BlockPos(
											IntegerArgumentType.getInteger(context, "x"),
											IntegerArgumentType.getInteger(context, "y"),
											IntegerArgumentType.getInteger(context, "z")));
										context.getSource().sendFeedback(Component.literal("点A已设  " + BorerAreaMarks.sizeLabel(config)));
										return 1;
									})))))
					.then(literal("b").executes(context -> areaLook(context.getSource(), config, 2))
						.then(argument("x", IntegerArgumentType.integer(-30_000_000, 30_000_000))
							.then(argument("y", IntegerArgumentType.integer(-64, 320))
								.then(argument("z", IntegerArgumentType.integer(-30_000_000, 30_000_000))
									.executes(context -> {
										BorerAreaMarks.setB(config, new BlockPos(
											IntegerArgumentType.getInteger(context, "x"),
											IntegerArgumentType.getInteger(context, "y"),
											IntegerArgumentType.getInteger(context, "z")));
										context.getSource().sendFeedback(Component.literal("点B已设  " + BorerAreaMarks.sizeLabel(config)));
										return 1;
									})))))
					.then(literal("40").executes(context -> {
						var client = context.getSource().getClient();
						if (client.player == null) return 0;
						BorerAreaMarks.sizeFromFeet(config, client.player.blockPosition(), client.player.getDirection(), 40);
						config.borerLastMode = TunnelBorer.Mode.AREA.name();
						config.save();
						context.getSource().sendFeedback(Component.literal("已标脚下 40×40  " + BorerAreaMarks.sizeLabel(config)));
						return 1;
					}))
					.then(literal("clear").executes(context -> {
						if (KitClient.borer() != null && KitClient.borer().isActive()) {
							context.getSource().sendError(Component.literal("请先停止自动动作再清除选区；只取消显示请用 /twob2tkit area hide"));
							return 0;
						}
						BorerAreaMarks.clear(config);
						context.getSource().sendFeedback(Component.literal("已清除当前 A/B 选择，已保存的工程与进度保留"));
						return 1;
					}))
					.then(literal("hide").executes(context -> {
						KitClient.dismissAreaPreview();
						context.getSource().sendFeedback(Component.literal("已隐藏区域黄框，坐标、工程与进度保留")); return 1;
					}))
					.then(literal("show").executes(context -> {
						var borer = KitClient.borer();
						if (!config.borerAreaASet || !config.borerAreaBSet || borer == null) {
							context.getSource().sendError(Component.literal("请先设置并应用区域两角")); return 0;
						}
						if (borer.isActive() && (borer.isSceneryActive() || borer.mode() != TunnelBorer.Mode.AREA)) {
							context.getSource().sendError(Component.literal("请先停止其它自动功能再显示区域")); return 0;
						}
						borer.previewArea(context.getSource().getClient()); return 1;
					}))
					.then(literal("save")
						.executes(context -> areaSave(context.getSource(), config, ""))
						.then(argument("name", StringArgumentType.greedyString()).executes(context ->
							areaSave(context.getSource(), config, StringArgumentType.getString(context, "name")))))
					.then(literal("load").then(argument("name", StringArgumentType.greedyString()).executes(context -> {
						String name = StringArgumentType.getString(context, "name").trim();
						if (!config.loadAreaProject(name)) {
							context.getSource().sendError(Component.literal("找不到工程：" + name));
							return 0;
						}
						context.getSource().sendFeedback(Component.literal("已加载工程  " + BorerAreaMarks.sizeLabel(config)));
						return 1;
					})))
					.then(literal("list").executes(context -> {
						if (config.areaProjects.isEmpty()) {
							context.getSource().sendFeedback(Component.literal("还没有保存的区域工程"));
							return 1;
						}
						for (KitConfig.AreaProject project : config.areaProjects) {
							boolean active = project.id.equals(config.activeAreaProjectId);
							context.getSource().sendFeedback(Component.literal(BorerAreaProjects.listLine(project, active)));
						}
						return 1;
					}))
					.then(literal("delete").then(argument("name", StringArgumentType.greedyString()).executes(context -> {
						String name = StringArgumentType.getString(context, "name").trim();
						if (!config.removeAreaProject(name)) {
							context.getSource().sendError(Component.literal("找不到工程：" + name));
							return 0;
						}
						context.getSource().sendFeedback(Component.literal("已删除工程：" + name));
						return 1;
					})))
					.then(literal("start").executes(context -> {
						if (!config.borerAreaASet || !config.borerAreaBSet) {
							context.getSource().sendError(Component.literal("先设点A和点B"));
							return 0;
						}
						var client = context.getSource().getClient();
						config.borerLastMode = TunnelBorer.Mode.AREA.name();
						config.save();
						TunnelBorer borer = KitClient.borer();
						if (borer == null) return 0;
						KitClient.prepareForBorer(client);
						borer.start(client, TunnelBorer.Mode.AREA);
						return 1;
					}))
				)
				.then(literal("whitelist")
					.then(literal("list").executes(context -> {
						String names = config.trustedPlayers.isEmpty() ? "（空）" : String.join(", ", config.trustedPlayers);
						context.getSource().sendFeedback(Component.literal("玩家白名单：" + names));
						return 1;
					}))
					.then(literal("add").then(argument("name", StringArgumentType.word()).executes(context -> {
						String name = StringArgumentType.getString(context, "name");
						boolean added = config.addTrusted(name);
						context.getSource().sendFeedback(Component.literal(added ? "已加入白名单：" + name : "已在白名单中：" + name));
						return added ? 1 : 0;
					})))
					.then(literal("remove").then(argument("name", StringArgumentType.word()).executes(context -> {
						String name = StringArgumentType.getString(context, "name");
						boolean removed = config.removeTrusted(name);
						context.getSource().sendFeedback(Component.literal(removed ? "已移出白名单：" + name : "白名单中没有：" + name));
						return removed ? 1 : 0;
					})))
				)
		);
	}

	/** 打印用法与按键摘要。 */
	private static int help(FabricClientCommandSource source) {
		source.sendFeedback(Component.literal("twob2tkit：/twob2tkit start <x> <z> <巡航Y>"));
		source.sendFeedback(Component.literal("按键：" + KitKeys.hintLine()));
		source.sendFeedback(Component.literal("也可在界面「按键」或「选项 → 控制 → twob2tkit」中改键"));
		source.sendFeedback(Component.literal("设置：/twob2tkit set <arrival|player-radius|min-health|stuck-seconds|disconnect-on-arrival> <值>"));
		source.sendFeedback(Component.literal("白名单：/twob2tkit whitelist <add|remove|list> [玩家名]"));
		source.sendFeedback(Component.literal("运行引擎：/twob2tkit reload（盾构/找矿更新后无需退出游戏）"));
		source.sendFeedback(Component.literal("村庄职业：/twob2tkit villagers"));
		source.sendFeedback(Component.literal("投影建造：/twob2tkit print（需已装 Litematica 并放置投影）"));
		source.sendFeedback(Component.literal("风景预加载：/twob2tkit scenery · scenery start <半径格数> · scenery resume|stop|status"));
		source.sendFeedback(Component.literal("区域挖：/twob2tkit area a|b [x y z] · area save [名] · area load · area list · area start"));
		source.sendFeedback(Component.literal("区域显示：/twob2tkit area hide|show；clear 仅清除当前 A/B，保留已保存工程"));
		return 1;
	}

	/** 把当前点 A/B 存成区域工程。 */
	private static int areaSave(FabricClientCommandSource source, KitConfig config, String name) {
		if (!config.borerAreaASet || !config.borerAreaBSet) {
			source.sendError(Component.literal("先设点A和点B"));
			return 0;
		}
		String trimmed = name == null ? "" : name.trim();
		if (trimmed.isEmpty()) {
			trimmed = BorerAreaProjects.activeName(config);
			if (trimmed.isEmpty()) trimmed = BorerAreaProjects.defaultName(config);
		}
		var client = source.getClient();
		boolean added = config.upsertAreaProject(trimmed, BorerAreaProjects.currentDimension(client));
		source.sendFeedback(Component.literal((added ? "已保存工程：" : "已更新工程：") + trimmed
			+ "  " + BorerAreaMarks.sizeLabel(config)));
		return 1;
	}

	/** 用准星方块设点 A 或 B。 */
	private static int areaLook(FabricClientCommandSource source, KitConfig config, int corner) {
		BlockPos hit = BorerAreaMarks.lookBlock(source.getClient());
		if (hit == null) {
			source.sendError(Component.literal("准星没有方块。看向目标，或 /twob2tkit area " + (corner == 2 ? "b" : "a") + " <x> <y> <z>"));
			return 0;
		}
		if (corner == 2) BorerAreaMarks.setB(config, hit);
		else BorerAreaMarks.setA(config, hit);
		source.sendFeedback(Component.literal((corner == 2 ? "点B " : "点A ") + hit.getX() + " " + hit.getY() + " " + hit.getZ()
			+ "  " + BorerAreaMarks.sizeLabel(config)));
		return 1;
	}

	/** 打印巡航状态与关键保护参数。 */
	private static int status(FabricClientCommandSource source, KitConfig config, KitController controller) {
		source.sendFeedback(Component.literal(controller.statusLine(source.getClient())));
		source.sendFeedback(Component.literal(String.format(Locale.ROOT,
			"到达半径 %.1f；到达离线 %s；玩家半径 %.1f；最低生命 %.1f；卡住 %d 秒；障碍绕行 %s",
			config.arrivalRadius, config.disconnectOnArrival, config.playerRadius, config.minHealth, config.stuckSeconds, config.obstacleAvoidance)));
		return 1;
	}

	/** 保存配置并反馈数值项。 */
	private static int saved(FabricClientCommandSource source, KitConfig config, String label, double value) {
		config.save();
		source.sendFeedback(Component.literal(String.format(Locale.ROOT, "已保存：%s %.1f（0 为关闭）", label, value)));
		return 1;
	}
}
