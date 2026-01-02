if {[catch {

# define run engine funtion
source [file join {/home/dev/lscc/radiant} scripts tcl flow run_engine.tcl]
# define global variables
global para
set para(gui_mode) "0"
set para(prj_dir) "/build"
if {![file exists {/build/impl}]} {
  file mkdir {/build/impl}
}
cd {/build/impl}
# synthesize IPs
# synthesize VMs
# synthesize top design
file delete -force -- top_impl.vm top_impl.ldc
if {[file normalize "/build/impl/top_impl_synplify.tcl"] != [file normalize "./top_impl_synplify.tcl"]} {
  file copy -force "/build/impl/top_impl_synplify.tcl" "./top_impl_synplify.tcl"
}
if {[ catch {::radiant::runengine::run_engine synpwrap -prj "top_impl_synplify.tcl" -log "top_impl.srf"} result options ]} {
    file delete -force -- top_impl.vm top_impl.ldc
    return -options $options $result
}
::radiant::runengine::run_postsyn [list -a LIFCL -p LIFCL-17 -t QFN72 -sp 8_High-Performance_1.0V -oc Commercial -top -w -o top_impl_syn.udb top_impl.vm] [list top_impl.ldc]

} out]} {
   ::radiant::runengine::runtime_log $out
   exit 1
}
