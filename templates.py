"""
templates.py — Render template pakai Jinja2, return HTMLResponse.
Fix untuk menghindari bug cache 'unhashable type: dict' di starlette.Jinja2Templates.
"""
from pathlib import Path

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

_APP_DIR = Path(__file__).resolve().parent

_env = Environment(
    loader=FileSystemLoader(str(_APP_DIR / "templates")),
    auto_reload=True,
    cache_size=50,
)


def TemplateResponse(name: str, context: dict):
    """Render template → HTMLResponse. Signature mirip starlette.Jinja2Templates."""
    tpl = _env.get_template(name)
    html = tpl.render(**context)
    return HTMLResponse(html)
