#
# This file is part of LUNA.
#
# Copyright (c) 2023 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

from .top_level_cli import *

# Mildly evil hack to vendor in amaranth_soc and amaranth_stdio if they're
# not installed:
try:
    try:
        import amaranth_soc
        import amaranth_stdio
    except:
        import os
        path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(path, "gateware", "vendor")
        sys.path.append(path)
except:
    pass
