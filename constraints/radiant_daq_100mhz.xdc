# RADIANT-DAQ RTL-015 timing intent for future Xilinx 7-series implementation.
# This constraint declares a 100 MHz target clock only. It is not evidence of
# timing closure because placement/routing/static timing analysis are not run.

create_clock -name radiant_clk -period 10.000 [get_ports clk]
