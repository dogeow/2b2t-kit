# 固化前先加载工位，部分扫描不推断围墙变化

232 核验图面后仍在地图上方，进入固化步骤时先读取远处围护工位；其区块尚未加载。旧 `concrete_shelter.scan` 只检查回复存在 blocks 字段，把 0/270 格的 waiting 回复中的空列表当成空气，随后报 Enclosure wall or roof changed。233 只读复核确认了该回复实际为 Server chunk is not loaded，并没有证明围墙消失；没有据此补墙或改现场。

`Backend.harden` 现在先沿已登记基地接近路线加载工位，再开始围护读取和进入。`concrete_shelter.scan` 拒绝 waiting/error/stopped 或不完整格数，即使有空 blocks 列表也不推断空气；完整读取 270/270 格的空列表才可作为空气观察。既有配方与固化余额核验保留。

321 项相关 Python 回归及 worker 独立导入验证通过。234 bundle `596b17d913cd73e2bd89b7f484d4e9eb119ef912ed0b42daa7ce87ecdc052869`，manifest `3b66142db748657c4b530950247840fefffa28e005a4f04ac97bce31c2e7da1b`，已在真实满血高空驻留、旧任务结束后部署。235 从全新当前意图继续，原错误回复、进入前停止和实际材料均保留；旧固化 batches 为空，没有放置动作可重放。主包仍按用户要求等待下次更新。
