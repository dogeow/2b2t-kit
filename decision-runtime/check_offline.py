"""Run the deterministic offline regression set; never starts or connects Minecraft."""
from pathlib import Path
import argparse,os,subprocess,sys

TESTS = (
    'test_material_client', 'test_material_health_exit', 'test_material_shutdown', 'test_cave_escape_cli',
    'test_torch_planning', 'test_pipeline_dispatch', 'test_pipeline_experience', 'test_experience_recording',
    'test_mineral_pipeline', 'test_material_wood_pipeline', 'test_colored_pipeline', 'test_colored_sources',
    'test_natural_block_pipeline', 'test_mud_pipeline', 'test_material_stripped_wood_pipeline',
    'test_terrain_replace_south', 'test_terrain_replace_south_cli',
    'test_live_snapshot', 'test_job_progress', 'test_safety_interlock', 'test_server_probe',
    'test_inventory_session', 'test_stack_recipe', 'test_material_manufacture', 'test_craft_recovery',
    'test_container_access', 'test_material_depots', 'test_concrete_soil', 'test_shore_concrete', 'test_concrete_shelter',
    'test_furnace_batches', 'test_furnace_bank', 'test_smelting_workflow', 'test_journal', 'test_decision_advisor',
    'test_construction_materials', 'test_construction_obstruction',
    'test_construction_obstruction_cli', 'test_goal_workflow',
    'test_projection_material_plan', 'test_projection_advice', 'test_material_jobs', 'test_material_processing',
    'test_material_jobs_backend', 'test_projection_ready_supply', 'test_targeted_supply',
    'test_material_jobs_acquisition', 'test_material_discovery', 'test_snow_biome_search',
    'test_seed_snow_search',
    'test_material_snow_plan', 'test_material_snow_acquisition',
    'test_construction_access_plan', 'test_construction_access_journal', 'test_construction_access_receipts', 'test_construction_access',
    'test_material_task_client', 'test_quarry_vegetation', 'test_approved_supply',
    'test_material_equipment', 'test_material_packed_capacity', 'test_material_worker_release', 'test_material_jobs_navigation',
    'test_diagnostic_events', 'test_diagnose', 'test_run_evidence',
    'test_sensitive_data', 'test_kit_release',
)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java',action='store_true',help='Also build and run Java tests using the existing offline Gradle cache')
    args=parser.parse_args();here=Path(__file__).resolve().parent
    subprocess.run([sys.executable,'-m','unittest',*TESTS,'-q'],cwd=here,check=True)
    if args.java:
        env=os.environ.copy();env['JAVA_HOME']=str(here.parents[1]/'jdk25/Contents/Home')
        subprocess.run(['./gradlew','test','jar','verifyRuntimeEngineJar','--offline'],cwd=here.parent,env=env,check=True)

if __name__=='__main__':main()
