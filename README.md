# Plastron

An audiovisual video editor built as a Blender application template.
Storyboard mode first; more modes to come. GPL-3.0.

## Install (Windows)

Press **Win+X**, choose **Windows PowerShell**, paste this line and press Enter:

```powershell
irm https://raw.githubusercontent.com/olliejoet-glitch/Plastron/main/install/install.ps1 | iex
```

This installs everything into `C:\Plastron` (a private copy of Blender, so your
normal Blender is untouched), adds a Plastron shortcut to the desktop and Start
menu, and starts Plastron. Each time Plastron starts it updates itself from
GitHub.

To uninstall: delete `C:\Plastron` and the two shortcuts.

## For development

See `CLAUDE.md`. Run all tests with `python tests/run_tests.py`.
