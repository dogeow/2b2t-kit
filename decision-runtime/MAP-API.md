# 原生地图与铁砧读取接口

这是宿主客户端新增接口，修改后需要完整重启 Minecraft。仅更新运行时引擎不会提供这些接口。快照中的 `map_create_protocol` 和 `map_audit_protocol` 均为 `1`。

## 创建一张地图

现有 `MaterialClient` 自动补充服务器、工作点、世界会话、材料任务、控制版本和有效期。先把一张空地图放在当前主手，再调用：

```python
result = client.request('map_create', expected_center=[761088, 797696])
```

需要当前存活、健康、空闲的生存模式材料租约与 PvE 防护；背包界面、光标、移动控制器和伐木器必须空闲，附近不能有敌对实体。空地图数量大于一时，还需要一个空背包格，防止生成的地图掉落。

接口只调用一次正常的 `gameMode.useItem`，不按住使用键，不构造物品或服务器地图数据，不自动重试。最多等待 100 个客户端 tick，确认空地图总数减少一、原有地图 ID 数量全部不变、背包出现恰好一个新的地图 ID，才返回 `phase=done`。`map_creation`（终态快照为 `last_map_creation`）包含 `use_count`、`inventory_delta_confirmed`、新 `map_id` 和预计生成网格。

`waiting`、断线或错误均不能作为重发指令的依据：检查背包和新地图，避免再消耗一张。`expected_center` 是使用时玩家位置所在的零级地图网格，属于生成位置预测，不是服务器地图地理元数据的读取证明。

## 读取真实地图像素

```python
result = client.request('map_audit', map_id=created_map_id)
audit = result['map_audit']
```

也可指定当前背包 `slot`；没有选择参数时读取主手。目标必须是当前背包中的填充地图。只能读取当前 `ClientLevel` 已加载的数据；数据未收到时返回错误，需手持该填充地图等待正常服务器更新。

`audit` 提供 `map_id`、`scale`、`locked`、原始客户端缓存 `center_x/center_z/dimension`，以及 `colors`：

- `packed_colors`：恰好 16,384 个原始字节的 Base64，`packed_color_encoding=base64-u8`。
- `colors_sha256`：原始字节的 SHA256。
- `index=z*128+x`，X 向东、Z 向南；无符号字节高六位为地图颜色 ID，低两位为亮度。
- `map_color_none_pixels`：颜色 ID 为零的像素数。

不会用图纸补齐颜色，也不会宣称缓存刚刚完成刷新。`freshness_verified=false`；比较全部像素与期望画面后，才能证明这份地图缓存的颜色正确。

原版远端地图更新包不发送地理中心和维度。`createForClient` 把中心设为零、维度设为当前客户端世界。因此 `geographic_center_verified` 和 `geographic_dimension_verified` 均为 `false`，`geography_source=client_cache_placeholder_not_server_geographic_metadata`。不要把这些缓存字段当作服务器真实地理坐标。零级地图施工坐标由已验证投影和实际生成位置确认。

普通物品快照新增 `map_id`、`map_data_loaded`，数据已加载时附小型 `map` 元数据；不在反复写入的背包快照中携带全部像素。

## 铁砧当前报价

当前菜单是 `AnvilMenu` 时，`snapshot.menu` 新增：

- `anvil_cost`：直接读取当前菜单 `getCost()`，不根据玩家经验级别推算。
- `anvil_result_present`：实际结果槽是否有物品。
- `anvil_result_may_pickup`：实际结果槽 `mayPickup(player)`。
- `anvil_too_expensive`：非无限材料模式且当前报价至少 40 级。

这些字段只读取当前界面，不领取结果、扣经验或合并工具。
