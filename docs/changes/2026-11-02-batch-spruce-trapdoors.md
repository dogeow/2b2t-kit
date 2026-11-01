# Batch spruce trapdoor crafting

The villa XP-tower preparation needs194 spruce trapdoors. Admit the exact Minecraft26.2 spruce recipe to the existing bounded stack-crafting loop: six spruce planks in the first two workbench rows produce two trapdoors. Wrong wood, shape, output count, recipe id, boolean counts and mixed materials remain rejected. Existing exact inventory distribution, input/output balances, capacity limits and unknown-action receipts remain in force.

This changes recipe eligibility only and reuses existing batching. Tests cover384-plank/128-output batches and final single-recipe leftovers, and compare the plan with the actual26.2 recipe catalog. Forty related tests pass, including grouped distribution, chest/hopper recipes, cobblestone shapes and portion frames. The Python worker was updated with an exact-baseline check and backup; no game restart is needed. Actual194-item crafting remains a separate game receipt, not claimed by these tests.
