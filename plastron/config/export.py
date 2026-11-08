"""Exports (File menu): animatic video, panel sheet (PDF), shot list (CSV)."""

# Animatic video: size (each panel is re-made at this size, not the small
# timeline thumbnail), container / codecs (Blender's FFmpeg names).
ANIMATIC_SIZE = (1920, 1080)
ANIMATIC_FORMAT = 'MPEG4'
ANIMATIC_CODEC = 'H264'
ANIMATIC_AUDIO = 'AAC'
ANIMATIC_QUALITY = 'HIGH'          # constant rate factor: LOW / MEDIUM / HIGH / PERC_LOSSLESS ...

# Panel sheet (PDF): page size in points (A4 landscape), margin, grid.
SHEET_PAGE = (842, 595)
SHEET_MARGIN = 30
SHEET_COLUMNS = 3
SHEET_ROWS = 2
SHEET_GAP = 14
SHEET_FONT_SIZE = 9
