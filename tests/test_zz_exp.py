import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa
import harness as h  # noqa
panels = h.module("features.storyboard.panels")
tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
events = h.module("timeline.events")


def steps():
    yield 1.0
    sc = bpy.context.scene
    ch = tracks.channel_of(sc, tracks.video_tracks(sc)[-1])
    first = panels.all_panels(sc)[0]
    b = panels.create(sc, ch, clips.end(first), 48)
    c = panels.create(sc, ch, clips.end(b), 48)
    events.clips_changed(sc)
    tl = h.area('SEQUENCE_EDITOR')
    reg = h.region(tl)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.5
    print("EXP before", [(s.name, clips.start(s), clips.end(s), s.channel) for s in panels.all_panels(sc)], flush=True)
    v2d = reg.view2d
    x0, y0 = v2d.view_to_region(clips.start(b) + 24, ch + 0.5, clip=False)
    x1, _ = v2d.view_to_region(clips.end(c) + 10, ch + 0.5, clip=False)
    yield from h.drag((reg.x + x0, reg.y + y0), (reg.x + x1, reg.y + y0), steps=12)
    yield 1.0
    wm = bpy.context.window_manager
    op = wm.operators[-1]
    print("EXP op", op.bl_idname, {k: tuple(getattr(op.properties, k)) if hasattr(getattr(op.properties, k), '__len__') and not isinstance(getattr(op.properties, k), str) else getattr(op.properties, k) for k in op.properties.keys()}, flush=True)
    print("EXP after", [(s.name, clips.start(s), clips.end(s), s.channel) for s in panels.all_panels(sc)], flush=True)
    print("EXP overlap", sc.tool_settings.sequencer_tool_settings.overlap_mode, flush=True)
    h.check("exp", True)


h.run(steps())
