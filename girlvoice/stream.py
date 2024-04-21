from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

class Stream(wiring.Signature):
    def __init__(self, width):
        super().__init__({
            "data": Out(width),
            "valid": Out(1),
            "ready": In(1)
        })