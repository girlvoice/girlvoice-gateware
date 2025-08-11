from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


class StreamSignature(wiring.Signature):
    def __init__(self, width):
        super().__init__({"data": Out(width), "valid": Out(1), "ready": In(1)})


async def stream_get(ctx, stream):
    ctx.set(stream.ready, 1)
    (payload,) = await ctx.tick().sample(stream.payload).until(stream.valid)
    ctx.set(stream.ready, 0)
    return payload


async def stream_put(ctx, stream, payload):
    ctx.set(stream.valid, 1)
    ctx.set(stream.payload, payload)
    await ctx.tick().until(stream.ready)
    ctx.set(stream.valid, 0)


async def stream_watch(ctx, stream):
    payload = await ctx.tick().sample(stream.payload).until(stream.valid & stream.ready)
    return payload


def new_observer(stream, output_arr):
    async def observe(ctx):
        while True:
            output_arr.append(await stream_watch(ctx, stream))

    return observe
