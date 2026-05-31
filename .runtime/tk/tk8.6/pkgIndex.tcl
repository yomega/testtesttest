if {![package vsatisfies [package provide Tcl] 8.6.0]} return
if {($::tcl_platform(platform) eq "unix") && ([info exists ::env(DISPLAY)]
	|| ([info exists ::argv] && ("-display" in $::argv)))} {
    package ifneeded Tk 8.6.12 [list load "C:/Users/yomeg/AppData/Local/Programs/Python/Python311/DLLs/tk86t.dll"]
} else {
    package ifneeded Tk 8.6.12 [list load "C:/Users/yomeg/AppData/Local/Programs/Python/Python311/DLLs/tk86t.dll"]
}
