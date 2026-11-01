# Check original water-network floors before selecting a bucket

A missing magma floor was reported by native bucket ownership as a broad admission rejection. Repeated mob clearance could not fix that geometry error. The model-source worker now scans the connected original planar network's floor in small coherent tiles and records exact mismatched coordinates and block states before selecting or using a bucket.

This is a read-only prerequisite check. Existing source-fluid floors retain native phase handling; hopper enabled and dropper triggered bits follow the native dynamic-state comparison. Native shape, regeneration, entity, whole-region and server-receipt checks remain authoritative. No protection rule is relaxed, and no old action is retried or acknowledged by this preflight.

The regression suite verifies that a mismatched floor prevents both tool selection and bucket dispatch, that changed floor orientation remains an error, and that lava cannot masquerade as a source-water floor. The related worker suites pass 33 tests. This Python worker update requires no host or engine restart.
