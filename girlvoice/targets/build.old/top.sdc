create_clock -name "clk12_clk" -period 83.33333333333333 [get_nets "clk12_clk"]
create_clock -name "clk" -period 16.666666666666668 [get_nets "soc/wb_to_csr/clk"]
create_clock -name "fast_clk" -period 8.333333333333334 [get_nets "soc/spi0/cs_cdc/fast_clk"]
create_clock -name "clk12_0__io" -period 83.33333333333333 [get_ports "clk12_0__io"]
ldc_set_sysconfig {{CONFIGIO_VOLTAGE_BANK0=3.3 CONFIGIO_VOLTAGE_BANK1=3.3 JTAG_PORT=DISABLE SLAVE_SPI_PORT=DISABLE MASTER_SPI_PORT=DISABLE}}
ldc_set_attribute {USE_PRIMARY=FALSE} [get_ports "i2c_0__scl__io"]
