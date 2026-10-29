"""Runs Plastron's portable Blender for tests and builds (Linux, headless).

Mirrors Ollie's Windows install: a private copy of Blender with a `portable`
folder, and Plastron linked in as an app template. Nothing touches the
system Blender's settings.
"""

import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, ".cache")
OUTPUT = os.path.join(REPO, "tests", "output")
TEMPLATE_NAME = "plastron"


def system_blender():
    path = os.environ.get("PLASTRON_BLENDER") or shutil.which("blender")
    if not path:
        sys.exit("Blender not found: set PLASTRON_BLENDER to the blender executable.")
    return os.path.realpath(path)


def portable_blender():
    """Path to the test copy of Blender, creating it on first use."""
    src_dir = os.path.dirname(system_blender())
    dst_dir = os.path.join(CACHE, "blender")
    if not os.path.isdir(dst_dir):
        os.makedirs(CACHE, exist_ok=True)
        # Hard links: instant and uses no extra disk space.
        if subprocess.call(["cp", "-al", src_dir, dst_dir]) != 0:
            shutil.copytree(src_dir, dst_dir, symlinks=True)
    portable = os.path.join(dst_dir, "portable")
    templates = os.path.join(portable, "scripts", "startup", "bl_app_templates_user")
    os.makedirs(templates, exist_ok=True)
    link = os.path.join(templates, TEMPLATE_NAME)
    if not os.path.islink(link):
        if os.path.exists(link):
            shutil.rmtree(link)
        os.symlink(os.path.join(REPO, TEMPLATE_NAME), link)
    # Fresh settings every run, like a first launch on Ollie's machine.
    shutil.rmtree(os.path.join(portable, "config"), ignore_errors=True)
    return os.path.join(dst_dir, "blender")


def run(args, gui=True, timeout=300, env=None):
    """Run Blender with args; returns (exit code, combined output)."""
    os.makedirs(OUTPUT, exist_ok=True)
    tmp = os.path.join(CACHE, "tmp")
    os.makedirs(tmp, exist_ok=True)
    full_env = dict(os.environ, TMPDIR=tmp, TEMP=tmp, TMP=tmp, **(env or {}))
    cmd = [portable_blender()] + list(args)
    if gui:
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24"] + cmd
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=timeout, env=full_env)
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout.decode() if isinstance(ex.stdout, bytes) else (ex.stdout or "")
        return -1, out + "\n[timed out]"
