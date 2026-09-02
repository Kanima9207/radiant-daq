# RADIANT-DAQ RTL-016 Artix-7 implementation constraint.
# Target: XC7A35T-CSG324 class device, 100 MHz implementation clock.
# E3 is used as the clock-capable package location for the implementation model.
# This is a tool-flow target, not a statement that a physical board is present.

set_property PACKAGE_PIN E3 [get_ports clk]
create_clock -name sys_clk -period 10.000 [get_ports clk]
