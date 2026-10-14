# Nearby mud conversion check

The user identified two separate devices beside their current position and
confirmed harvesting newly grown pointed dripstone. That report is evidence of
growth output; the growth device must not be diagnosed as failing from the
remaining short cones.

A complete native scan in current world
`95def4e5-1c56-4522-bf16-f565217abe83`, overworld, found 29 mud blocks:

- 16 have mud at Y71, a full support block at Y70, and a downward, unwaterlogged
  tip at Y69. Fifteen supports are dark oak planks and one is cobblestone.
- Two at X761000, Y71, Z797773/797774 have pointed dripstone directly beneath
  the mud, without the intervening support block.
- Eleven currently lack pointed dripstone below their support.

Vanilla code in the installed official 26.1.2 game JAR reads the fluid/mud block
above the stalactite root support; the direct-on-mud pair therefore does not
match that conversion arrangement. The full support need not be dripstone
block. Client bytecode is a mechanics reference, not proof of server settings.
The official Java 1.19 release describes mud above a block with pointed
dripstone underneath converting to clay:
https://www.minecraft.net/de-de/article/the-wild-update-out-today-java

Read-only samples every ten seconds for two minutes found all 16 correctly
arranged columns still mud. A final native scan 253 seconds after the first
sample again found 16 mud and zero clay. Player position was unchanged and
within 11.6 horizontal blocks of all sampled columns. No movement, mining,
placement, or inventory credit was dispatched.

Thirty clay blocks in the wider scan are at Y61–63 in the ground, not at the
farm mud layer Y71. They are not claimed as conversion output. The reason the
16 correct columns did not convert remains unconfirmed; this bounded
observation does not prove a disabled server rule or guarantee a conversion
deadline.

Evidence: `work/live-20261004/user-nearby-mud-farms-619/`,
`mud-valid-columns-observer-620/`, `mud-farm-final-check-621/`.

## Subsequent cross-version identity evidence

The user later showed a crafting result named `26.2 Sulfur`. The public
ViaBackwards 26.2→26.1 mapping maps sulfur spike items and all sulfur spike block
states to pointed dripstone. Sulfur items map to sandstone. Native client IDs
alone therefore cannot distinguish a real dripstone tip from a sulfur spike.
The 16 columns above are correctly arranged according to client-visible states;
their actual server spike identity remains unconfirmed. They must not be
presented as proof of a correctly functioning server clay-conversion device.

The current server-list status advertises `Velocity 1.7.2-26.2`, protocol 776.
This describes the proxy's advertised compatibility, not the exact backend
version. No client upgrade or restart was performed. Public mapping bytes,
identifier tables, decoding reference, and exact substitutions are retained in
`work/live-20261004/viabackwards-26.2to26.1-mapping-623.nbt`,
`server-version-readonly-624.json`, and `verified-sulfur-substitutions-628.json`.
