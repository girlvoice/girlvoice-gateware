prj_create -name top -impl impl \
    -dev LIFCL-17-8SG72C \
    -synthesis synplify
prj_add_source "vexriscv_imac+dcache.v"
prj_add_source top.v
prj_add_source top.sdc
prj_add_source top.pdc
prj_set_impl_opt top \"top\"
# (script_project placeholder)
prj_save
prj_run Synthesis -impl impl -forceOne
prj_run Map -impl impl
prj_run PAR -impl impl
prj_run Export -impl impl -task Bitgen
# (script_after_export placeholder)