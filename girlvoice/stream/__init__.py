from amaranth import *
from amaranth.lib import wiring, stream
from amaranth.lib.wiring import In, Out

async def stream_get(ctx, stream: stream.Interface):
    ctx.set(stream.ready, 1)
    (payload,) = await ctx.tick().sample(stream.payload).until(stream.valid)
    ctx.set(stream.ready, 0)
    return payload

async def stream_put(ctx, stream: stream.Interface, payload):
    ctx.set(stream.valid, 1)
    ctx.set(stream.payload, payload)
    await ctx.tick().until(stream.ready)
    ctx.set(stream.valid, 0)

async def stream_watch(ctx, stream: stream.Interface):
    payload = await ctx.tick().sample(stream.payload).until(stream.valid & stream.ready)
    return payload

def new_observer(stream: stream.Interface, output_arr):
    async def observe(ctx):
        while True:
            output_arr.append(await stream_watch(ctx, stream))

    return observe
