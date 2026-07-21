"""
首页路由模块
"""
from flask import Blueprint, Response, request

home_bp = Blueprint("home", __name__)

REPO_URL = "https://github.com/JerryFish123/ai-cr-lab"


def _home_html(dashboard_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ai-cr-lab · API</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --ink: #0c1222;
      --fog: #e8eef8;
      --mist: rgba(232, 238, 248, 0.72);
      --accent: #3dd6c6;
      --accent-2: #f0b429;
      --line: rgba(232, 238, 248, 0.14);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ min-height: 100%; }}
    body {{
      font-family: "Outfit", system-ui, sans-serif;
      color: var(--fog);
      background:
        radial-gradient(1200px 600px at 12% -10%, rgba(61, 214, 198, 0.22), transparent 55%),
        radial-gradient(900px 500px at 90% 10%, rgba(240, 180, 41, 0.14), transparent 50%),
        linear-gradient(165deg, #070b14 0%, #121a2e 48%, #0a1628 100%);
      display: grid;
      place-items: center;
      padding: 2.5rem 1.25rem;
      overflow-x: hidden;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(var(--line) 1px, transparent 1px),
        linear-gradient(90deg, var(--line) 1px, transparent 1px);
      background-size: 48px 48px;
      mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
      pointer-events: none;
      animation: gridDrift 28s linear infinite;
    }}
    @keyframes gridDrift {{
      from {{ transform: translateY(0); }}
      to {{ transform: translateY(48px); }}
    }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(18px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes pulse {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(61, 214, 198, 0.45); }}
      50% {{ box-shadow: 0 0 0 10px rgba(61, 214, 198, 0); }}
    }}
    .stage {{
      position: relative;
      width: min(720px, 100%);
      animation: rise 0.7s ease-out both;
    }}
    .brand {{
      font-size: clamp(2.6rem, 8vw, 4.2rem);
      font-weight: 700;
      letter-spacing: -0.04em;
      line-height: 0.95;
      margin-bottom: 0.85rem;
    }}
    .brand span {{
      background: linear-gradient(120deg, var(--accent) 0%, #7ee8dc 45%, var(--accent-2) 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 0.55rem;
      font-family: "IBM Plex Mono", monospace;
      font-size: 0.82rem;
      color: var(--mist);
      margin-bottom: 1.35rem;
      animation: rise 0.7s ease-out 0.12s both;
    }}
    .status i {{
      width: 0.55rem;
      height: 0.55rem;
      border-radius: 50%;
      background: var(--accent);
      animation: pulse 2.2s ease-out infinite;
    }}
    h1 {{
      font-size: clamp(1.35rem, 3.6vw, 1.85rem);
      font-weight: 600;
      letter-spacing: -0.02em;
      max-width: 28ch;
      margin-bottom: 0.65rem;
      animation: rise 0.7s ease-out 0.18s both;
    }}
    .lead {{
      color: var(--mist);
      font-size: 1.05rem;
      line-height: 1.55;
      max-width: 42ch;
      margin-bottom: 1.75rem;
      animation: rise 0.7s ease-out 0.24s both;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      animation: rise 0.7s ease-out 0.32s both;
    }}
    a.btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.78rem 1.2rem;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.95rem;
      transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease;
    }}
    a.btn:hover {{ transform: translateY(-2px); }}
    a.btn-primary {{
      background: var(--accent);
      color: var(--ink);
    }}
    a.btn-primary:hover {{ background: #63e4d6; }}
    a.btn-ghost {{
      border: 1px solid var(--line);
      color: var(--fog);
      background: rgba(12, 18, 34, 0.35);
      backdrop-filter: blur(8px);
    }}
    a.btn-ghost:hover {{ border-color: rgba(61, 214, 198, 0.45); }}
    .meta {{
      margin-top: 2.25rem;
      padding-top: 1.1rem;
      border-top: 1px solid var(--line);
      font-family: "IBM Plex Mono", monospace;
      font-size: 0.75rem;
      color: rgba(232, 238, 248, 0.45);
      animation: rise 0.7s ease-out 0.4s both;
    }}
  </style>
</head>
<body>
  <main class="stage">
    <p class="brand"><span>ai-cr-lab</span></p>
    <p class="status"><i></i> API server is running</p>
    <h1>Git AI Code Review 服务已就绪</h1>
    <p class="lead">推送与合并请求会触发自动审查。源码与部署说明见 GitHub；审查统计在 Dashboard。</p>
    <div class="actions">
      <a class="btn btn-primary" href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub · JerryFish123/ai-cr-lab</a>
      <a class="btn btn-ghost" href="{dashboard_url}" rel="noopener noreferrer">打开 Dashboard</a>
    </div>
    <p class="meta">webhook: /review/webhook · repo: {REPO_URL}</p>
  </main>
</body>
</html>
"""


@home_bp.route("/")
def home():
    host = request.host.split(":")[0]
    dashboard_url = f"http://{host}:5002/"
    return Response(_home_html(dashboard_url), mimetype="text/html; charset=utf-8")
