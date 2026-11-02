# Keep runtime observers current across partial engine rebuilds

The installed 1.8.46 engine contained observer classes with the old `1.8.40` version literal inlined by javac. Their same-runtime admission checks rejected current status snapshots, so the villager event file stopped updating. This prevented an ordinary occupied-bed wake and blocked the XP-trading workflow before any purchase.

The generated EngineBuildVersion now initializes VALUE through a method, so it is not a Java compile-time constant. Unchanged consumers read the replacement version class after a partial rebuild. Engine 1.8.47 recompiles all eleven current consumers to remove previously inlined literals; API version remains 3. This is an engine hot update, with no host, inventory or world edit required.

Validation:

- Two Python regressions compile real Java consumers, replace only the version class, and require an unchanged consumer to report the new version.
- The candidate compiled against the actual 26.2 client, installed host, Meteor and nested Fabric dependencies. All engine classes were checked for stale runtime-version literals.
- 46 existing observer, enclosure and idle-thermal tests passed against the candidate.
- The installed unrelated BorerThreats class is byte-for-byte unchanged.
- Live hot reload reports engine/navigation 1.8.47 and a fresh same-world villager-event frame; the occupied-bed wake and ordinary iron-for-emerald purchase then succeeded.

The standard offline Gradle command still stops before compilation because Fabric Loom 1.17-SNAPSHOT is unavailable in the local cache. The isolated checks are not a claim that the complete Gradle suite passed. Other survey consumers were recompiled and covered where listed above; they were not all exercised in a live world during this repair.
