"""Where each word of a clip's transcript goes in its transcript bar. Pure
maths (no Blender), so it's easy to test.

Zoomed in far enough that every word fits at its exact time without
touching the next: words sit at their times on one line. Otherwise they
wrap inside the clip's edges, as many lines as the bar has, the last shown
line ending in "…" if more don't fit. Words in trimmed-off parts of the
clip are only shown wrapped (greyed out by the drawing code).
"""

ELLIPSIS = "…"


def layout(words, clip_x0, clip_x1, line_count, gap, ellipsis_width):
    """words: [(time_x, width, trimmed)] in order.
    Returns (mode, [(word index, x, line)], ellipsis (x, line) or None)."""
    shown = [i for i, (_x, _w, trimmed) in enumerate(words) if not trimmed]
    exact = True
    for n, i in enumerate(shown):
        x, w, _t = words[i]
        right = words[shown[n + 1]][0] - gap if n + 1 < len(shown) else clip_x1
        if x < clip_x0 or x + w > right:
            exact = False
            break
    if exact:
        return "EXACT", [(i, words[i][0], 0) for i in shown], None

    placed = []
    x, line = clip_x0 + gap, 0
    right = clip_x1 - gap
    for i, (_tx, w, _trimmed) in enumerate(words):
        if x + w > right and x > clip_x0 + gap:          # wrap
            line += 1
            x = clip_x0 + gap
        if line >= line_count or x + w > right:
            placed, ellipsis = _make_room_for_ellipsis(placed, words, right, ellipsis_width, gap,
                                                       line_count, clip_x0)
            return "WRAPPED", placed, ellipsis
        placed.append((i, x, line))
        x += w + gap
    return "WRAPPED", placed, None


def _make_room_for_ellipsis(placed, words, right, ellipsis_width, gap, line_count, clip_x0):
    """Drop words from the end of the last line until "…" fits after them."""
    last_line = min(line_count - 1, placed[-1][2]) if placed else 0
    placed = [p for p in placed if p[2] <= last_line]
    while placed and placed[-1][2] == last_line and \
            placed[-1][1] + words[placed[-1][0]][1] + gap + ellipsis_width > right:
        placed.pop()
    if placed and placed[-1][2] == last_line:
        i, x, _line = placed[-1]
        ellipsis = (x + words[i][1] + gap, last_line)
    else:
        ellipsis = (clip_x0 + gap, last_line)
    return placed, ellipsis
