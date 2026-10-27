# 仓库部分取料后的正常出口观察

本次为牧师、武器匠、盔甲匠取料，实际拿到三块平滑石、三块普通石头和一个铁块。末影箱记录里的烈焰棒位于潜影盒内，普通 exchange 正确返回 complete=false、剩余一根；记录不改写为完成。

原有 exchange_shortage 观察器只接受最后操作是 close_menu，未覆盖已关箱并正常走出房屋的已结算路径。现在还接受有记录的仓库配置、原任务及世界、从关箱到结束全为 done 且无库存变化、健康满值、当前无输入且已落地的正常出口；保留库存总量及剩余量的严格核对。最后一步落地允许半格内平面滑行及一格以内自然下降。这里只发 snapshot，不重复任何取料。

验证：test_village_exchange_shortage 4 项（含出口多种反例）、test_village_queue 27 项通过。反例包括位置超限、仍按键、悬空、缺关箱回执、中间库存变化、任务变化和未知原生动作。实机观察通过后，使用已有 take_packed_materials 取一根烈焰棒，潜影盒完整放回末影箱原槽位。

实机证据：live-village-092/take-packed-blaze-rod-1431-proof.json、craft-three-profession-stations-1432-proof.json、install-three-north-stations-1433-proof.json、profession-server-quotes-1434-proof.json，均在 work/village-trading-20261017 下。三个设施完成安装；牧师、武器匠实际服务器报价各两项。其余四个待核验柜位当前无业且接近休息时段，不声称职业、交易或补货已验收。
