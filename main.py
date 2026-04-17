from pathlib import Path
import json, os, subprocess, re, asyncio
from bs4 import BeautifulSoup
import aiohttp

APP_DIR = (Path(os.environ.get('APPDATA', Path.home())) if os.name == 'nt' else Path.home() / '.config') / 'btu-dashboard'
BASE_URL = "https://classroom.btu.edu.ge/en/student/me/courses"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"}

def load_config():
    try: return json.loads((APP_DIR / 'config.json').read_text())
    except: return {}


def save_config(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / 'config.json').write_text(json.dumps(cfg, indent=2))

def parse_num(td):
    try: return float(td.get_text(strip=True).replace(",", "."))
    except: return td.get_text(strip=True)

TEMPLATE = '''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="btu.ico" type="image/x-icon"><title>BTU Courses</title><style>*{margin:0;padding:0;box-sizing:border-box}::-webkit-scrollbar{display:none}html{scrollbar-width:none}body{font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(135deg,#0c0c0c,#1a1a2e);color:#e4e4e7;min-height:100vh;padding:2rem}.courses{display:grid;grid-template-columns:repeat(2,1fr);gap:1rem;max-width:1400px;margin:0 auto}@media(max-width:900px){.courses{grid-template-columns:1fr}}.course{background:#18181b;border-radius:12px;padding:1.25rem;border:1px solid #27272a;display:flex;flex-direction:column;gap:.75rem}.course:hover{border-color:#3f3f46}.course-header{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem}.course-info{flex:1}.course-name{font-size:1.1rem;font-weight:600;color:#fafafa;margin-bottom:.25rem}.course-meta{font-size:.85rem;color:#71717a}.ects{font-size:.7rem;padding:.25rem .6rem;background:rgba(139,92,246,.2);color:#a78bfa;border-radius:4px;font-weight:500}.syllabus-link{font-size:.7rem;padding:.25rem .6rem;background:rgba(59,130,246,.15);color:#60a5fa;border-radius:4px;font-weight:500;text-decoration:none;transition:.15s}.syllabus-link:hover{background:rgba(59,130,246,.25);color:#93c5fd}.grade{font-size:2rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;display:flex;align-items:center;gap:.5rem}.pct-badge{font-size:.65rem;padding:.2rem .45rem;border-radius:4px;font-weight:600;opacity:.9}.assessments{display:flex;flex-wrap:wrap;gap:.5rem}.assessment{display:inline-flex;align-items:center;gap:.5rem;font-size:.8rem;padding:.35rem .6rem;background:#27272a;border-radius:6px}.assessment-name{color:#a1a1aa}.assessment-score{color:#4ade80;font-weight:600;font-variant-numeric:tabular-nums}.assessment-score.empty{color:#52525b}.materials-section{border-top:1px solid #27272a;padding-top:.75rem}.materials-toggle{display:flex;align-items:center;gap:.5rem;font-size:.85rem;color:#71717a;cursor:pointer;user-select:none}.materials-toggle:hover{color:#a1a1aa}.materials-toggle .arrow{transition:transform .2s}.materials-section.expanded .materials-toggle .arrow{transform:rotate(90deg)}.materials{display:none;flex-direction:column;gap:.4rem;margin-top:.75rem}.materials-section.expanded .materials{display:flex}.material{font-size:.85rem;padding:.5rem .75rem;background:rgba(59,130,246,.1);color:#60a5fa;text-decoration:none;border-radius:6px;transition:.15s;display:block}.material:hover{background:rgba(59,130,246,.2);color:#93c5fd}.material::before{content:"↓ ";opacity:.5}.summary{grid-column:1/-1;background:linear-gradient(135deg,#18181b,#1f1f23);border-radius:12px;padding:1.5rem;border:1px solid #27272a;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1.5rem}.summary-item{text-align:center}.summary-label{font-size:.75rem;color:#71717a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.5rem}.summary-value{font-size:1.75rem;font-weight:700;font-variant-numeric:tabular-nums;display:flex;align-items:center;justify-content:center;gap:.5rem}</style></head><body><div class="courses">{{COURSES}}{{SUMMARY}}</div><script>document.querySelectorAll('.materials-toggle').forEach(t=>t.addEventListener('click',()=>t.closest('.materials-section').classList.toggle('expanded')))</script></body></html>'''

class Http:
    """Simple async HTTP client with connection pooling"""
    def __init__(self, cookie: str = ""):
        self.cookie, self.session = cookie, None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={**HEADERS, "Cookie": self.cookie},
            timeout=aiohttp.ClientTimeout(total=60)
        )
        return self
    
    async def __aexit__(self, *_):
        if self.session: 
            await self.session.close()
    
    async def get(self, url: str, binary: bool = False) -> bytes | str:
        if not self.session: raise Exception("No session")
        async with self.session.get(url) as r:
            r.raise_for_status()
            return await r.read() if binary else (await r.read()).decode("utf-8", errors="ignore")


def parse_courses(html):
    soup = BeautifulSoup(html, "html.parser")
    if not (table := soup.select_one("table.table.table-striped.table-bordered.table-hover.fluid")):
        return []
    courses = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 6: continue
        name_a = tds[2].find("a")
        courses.append({
            "name": name_a.get_text(strip=True) if name_a else tds[2].get_text(strip=True),
            "grade": parse_num(tds[3]), 
            "ects": parse_num(tds[5]),
            "url": name_a["href"] if name_a and name_a.has_attr("href") else None,
        })
    return courses


def extract_course_urls(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = {}

    if tabs := soup.select_one("#course_tabs"):
        for a in tabs.find_all("a", href=True):
            for key in ("silabus", "groups", "scores", "files"):
                if key in a["href"]: 
                    urls[key.replace("silabus", "syllabus")] = a["href"]
                    
    if sf := soup.select_one('a[href*="courseSilabusFile"]'): 
        urls["syllabus_file"] = sf["href"]

    return urls


def parse_scores(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    data = {"group": None, "lector": None, "assessments": []}

    if h4 := soup.select_one(".tab_scores h4"):
        text = h4.get_text(" ", strip=True)
        if "Group" in text:
            parts = text.split(" - ", 1)
            data["group"] = parts[0].replace("Group", "").strip()
        if lector_link := h4.select_one("a[href*='/lector/']"):
            data["lector"] = lector_link.get_text(strip=True)

    if table := soup.select_one(".tab_scores table"):
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            
            component = tds[0].get_text(strip=True)
            score = tds[1].get_text(strip=True)
            
            if not component or component in ("სულ", "Credits") or "გამოცდაზე გასვლის" in component:
                continue
            
            # Extract max points from component name like "(max. 8)" or "(min. 12.3, max. 30)"
            max_points = None
            if max_match := re.search(r'max\.?\s*([\d.,]+)', component):
                try:
                    max_points = float(max_match.group(1).replace(',', '.'))
                except: pass
            
            data["assessments"].append({"component": component, "score": score or None, "max_points": max_points})

    return data


def parse_files(html: str, my_lector: str | None = None) -> list[dict]:
    """Extract training materials from files.html, optionally filtered by lector"""
    soup = BeautifulSoup(html, "html.parser")
    materials = []
    current_lector = None

    if not (table := soup.select_one("#files")): 
        return materials

    for tr in table.find_all("tr"):
        if (lector_link := tr.select_one("a[href*='/lector/']")) and "info" in (tr.get("class") or []):
            current_lector = lector_link.get_text(strip=True)
            continue

        # Skip materials from other lectors
        if my_lector and current_lector and current_lector.lower() != my_lector.lower():
            continue

        if not (tds := tr.find_all("td")):
            continue

        url = fl["href"] if (fl := tds[0].select_one("a[href*='/uploads/']")) and fl.get("href") else None

        if name := tds[0].get_text(strip=True):
            materials.append({"name": name, "url": url})

    return materials


def write_file(path: Path, data: bytes | str) -> None:
    """Write file with appropriate mode"""
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode, encoding=None if isinstance(data, bytes) else "utf-8") as f:
        f.write(data)


async def fetch_course_pages(course: dict, html_folder: Path, course_folder: Path, http: Http) -> dict:
    if not course["url"]: return {}
    for d in [html_folder, course_folder, course_folder / "material"]: 
        d.mkdir(parents=True, exist_ok=True)

    course_html = str(await http.get(course["url"]))
    urls = extract_course_urls(course_html)
    write_file(html_folder / "course.html", course_html)

    results: dict[str, str] = {}
    async def fetch_and_save(name: str, url: str) -> None:
        try:
            if name == "syllabus_file" and not (course_folder / "syllabus.pdf").exists():
                write_file(course_folder / "syllabus.pdf", await http.get(url, binary=True))
            elif name in ("scores", "files"):
                content = str(await http.get(url))
                results[name] = content
                write_file(html_folder / f"{name}.html", content)
            elif not (html_folder / f"{name}.html").exists():
                write_file(html_folder / f"{name}.html", await http.get(url))
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"  Failed to fetch {name}: {e}")

    await asyncio.gather(*(fetch_and_save(name, url) for name, url in urls.items()), return_exceptions=False)

    data: dict = {}
    if "scores" in results: 
        data["scores"] = parse_scores(results["scores"])
    elif (p := html_folder / "scores.html").exists(): 
        data["scores"] = parse_scores(p.read_text(encoding="utf-8"))
    
    lector = data.get("scores", {}).get("lector")
    if "files" in results: data["materials"] = parse_files(results["files"], lector)
    elif (p := html_folder / "files.html").exists(): 
        data["materials"] = parse_files(p.read_text(encoding="utf-8"), lector)
    
    return data


async def download_materials(materials: list[dict], folder: Path, http: Http) -> None:
    async def fetch_and_save_material(material: dict):
        if not material["url"]:
            return
        path = folder / material["url"].split("/")[-1]
        if path.exists():
            return
        try:
            write_file(path, await http.get(material["url"], binary=True))
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"  Failed: {path.name}: {e}")
    
    await asyncio.gather(*(fetch_and_save_material(m) for m in materials), return_exceptions=False)

def grade_color(pct):
    if pct >= 91: return "#22c55e"
    if pct >= 81: return "#84cc16"
    if pct >= 71: return "#eab308"
    if pct >= 61: return "#f97316"
    if pct >= 51: return "#ef4444"
    return "#991b1b"

def fmt(v) -> str:
    return str(int(v)) if isinstance(v, float) and v == int(v) else str(v) # removes trailing .0

def pct_badge(pct: float, color: str) -> str:
    """Generate percentage badge HTML, omitting 0% and 100%"""
    return f'<span class="pct-badge" style="background:{color}20;color:{color}">{pct:.0f}%</span>' if 0 < pct < 100 else ""


def generate_course_html(course: dict, data: dict, base: Path) -> str:
    scores, materials = data.get("scores", {}), data.get("materials", [])
    grade = course["grade"]
    max_pts = sum(a["max_points"] for a in scores.get("assessments", []) if a.get("score") and a.get("max_points"))
    
    if isinstance(grade, (int, float)) and max_pts > 0:
        pct = grade / max_pts * 100
        color = grade_color(pct)
        grade_html = f'{fmt(grade)}/{fmt(max_pts)}{pct_badge(pct, color)}'
    elif isinstance(grade, (int, float)):
        color, grade_html = grade_color(grade), fmt(grade)
    else:
        color, grade_html = "#52525b", str(grade)
    
    folder = f"courses/{course['name']}"
    syllabus = f'<a href="{folder}/syllabus.pdf" class="syllabus-link" target="_blank">Syllabus</a>' if (base / course['name'] / "syllabus.pdf").exists() else ""
    
    assess_html = ""
    for a in scores.get("assessments", []):
        raw, max_p = a["score"], a.get("max_points")
        name = a["component"].split("(")[0].strip()
        if raw:
            try: val = float(raw.replace(",", "."))
            except: val = None
            if max_p and val is not None:
                p = val / max_p * 100
                c = grade_color(p)
                assess_html += f'<span class="assessment"><span class="assessment-name">{name}</span><span class="assessment-score" style="color:{c}">{fmt(val)}/{fmt(max_p)}</span>{pct_badge(p, c)}</span>'
            else:
                assess_html += f'<span class="assessment"><span class="assessment-name">{name}</span><span class="assessment-score">{fmt(val) if val else raw}</span></span>'
        else:
            assess_html += f'<span class="assessment"><span class="assessment-name">{name}</span><span class="assessment-score empty">—</span></span>'
    
    mat_html = ""
    if materials:
        links = "".join(f'<a href="{folder}/material/{m["url"].split("/")[-1]}" class="material" target="_blank">{m["name"]}</a>' for m in materials if m["url"])
        mat_html = f'<div class="materials-section"><div class="materials-toggle"><span class="arrow">▶</span> Materials ({len(materials)})</div><div class="materials">{links}</div></div>'
    
    return f'''<div class="course"><div class="course-header"><div class="course-info"><div class="course-name">{course['name']}</div><div class="course-meta">Group {scores.get('group', '?')} · {scores.get('lector', 'Unknown')}</div></div>{syllabus}<span class="ects">{int(course['ects'])} ECTS</span><div class="grade" style="color:{color}">{grade_html}</div></div><div class="assessments">{assess_html}</div>{mat_html}</div>'''


def generate_summary_html(data: list[tuple[dict, dict]]) -> str:
    """Generate HTML for summary section"""
    total, max_total, ects, weighted = 0, 0, 0, 0
    for c, d in data:
        g, e = c["grade"], c["ects"]
        if isinstance(g, (int, float)): total += g
        cmax = sum(a["max_points"] for a in d.get("scores", {}).get("assessments", []) if a.get("score") and a.get("max_points"))
        max_total += cmax
        if isinstance(g, (int, float)) and cmax > 0 and isinstance(e, (int, float)):
            p = g / cmax * 100
            ects += e
            gpa = 4.0 if p >= 91 else 3.0 if p >= 81 else 2.0 if p >= 71 else 1.0 if p >= 61 else 0.5 if p >= 51 else 0
            weighted += gpa * e
    gpa = weighted / ects if ects else 0
    pct = total / max_total * 100 if max_total else 0
    return f'''<div class="summary"><div class="summary-item"><div class="summary-label">GPA</div><div class="summary-value" style="color:{grade_color(gpa/4*100)}">{gpa:.2f}</div></div><div class="summary-item"><div class="summary-label">Total Score</div><div class="summary-value" style="color:{grade_color(pct)}">{fmt(total)}/{fmt(max_total)} {pct_badge(pct, grade_color(pct))}</div></div><div class="summary-item"><div class="summary-label">Courses</div><div class="summary-value" style="color:#a78bfa">{len(data)}</div></div><div class="summary-item"><div class="summary-label">ECTS</div><div class="summary-value" style="color:#a78bfa">{fmt(ects)}</div></div></div>'''


def generate_html(data: list[tuple[dict, dict]], base: Path) -> str:
    return TEMPLATE.replace("{{COURSES}}", "".join(generate_course_html(c, d, base) for c, d in data)).replace("{{SUMMARY}}", generate_summary_html(data))


def has_display() -> bool:
    """Check if a display server is available; on Linux returns False when no DISPLAY/WAYLAND_DISPLAY is set"""
    import sys
    if sys.platform.startswith('linux'):
        return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    return True


def open_browser(url: str) -> None:
    import webbrowser
    # Check if running WSL
    if os.path.exists('/proc/version') and 'microsoft' in Path('/proc/version').read_text().lower():
        subprocess.run(['cmd.exe', '/c', 'start', url], stderr=subprocess.DEVNULL)
    else: webbrowser.open(url)


def serve_and_open(port: int = 1111) -> None:
    import http.server, socketserver, signal, sys

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args): 
            pass

        def handle(self):
            try: 
                super().handle()
            except BrokenPipeError: 
                pass

    def shutdown(*_):
        print("\nStopped")
        server.server_close()
        sys.exit(0)

    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("", port), QuietHandler)
    signal.signal(signal.SIGINT, shutdown)
    print(f"Serving at http://localhost:{port}")
    open_browser(f"http://localhost:{port}")
    server.serve_forever(poll_interval=0.1)


async def login() -> str:
    """Open browser for user to login, return session cookie"""
    try: from playwright.async_api import async_playwright
    except: subprocess.run(["pip", "install", "playwright"], check=True); from playwright.async_api import async_playwright

    headless = not has_display()
    async with async_playwright() as p:
        browser = None
        for attempt in range(3):
            try:
                browser = await p.chromium.launch(headless=headless)
                break
            except Exception:
                if attempt == 0:
                    print("Installing browser...")
                    import sys
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                elif attempt == 1 and not headless:
                    headless = True
                else:
                    raise
        page = await browser.new_page()
        await page.goto("https://classroom.btu.edu.ge/login")
        if headless:
            import getpass
            print("No display server detected. Enter your BTU credentials:")
            username = input("Username: ")
            password = getpass.getpass("Password: ")
            await page.locator('input[name="username"], input[type="email"], input[name="email"]').fill(username)
            await page.locator('input[type="password"]').fill(password)
            await page.locator('button[type="submit"], input[type="submit"]').click()
        else:
            print("Please login in the browser...")
        await page.wait_for_url("**/student/**", timeout=120000)
        cookies = await page.context.cookies()
        await browser.close()
        return "; ".join(f"{c.get('name')}={c.get('value')}" for c in cookies)


async def test_cookie(cookie: str) -> str:
    try:
        async with Http(cookie) as h:
            html = str(await h.get(BASE_URL))
            return html if parse_courses(html) else ""
    except: 
        return ""


async def get_cookie() -> tuple[str, str]:
    cfg = load_config()
    if (c := cfg.get("cookie")) and (html := await test_cookie(c)): return c, html
    if c: print("Cookie expired...")
    c = await login()
    save_config({**cfg, "cookie": c})
    return c, await test_cookie(c)


async def process_course(course: dict, html_base: Path, course_base: Path, http: Http) -> tuple[dict, dict]:
    name = course['name']
    html_folder, course_folder = html_base / name, course_base / name
    try:
        data = await fetch_course_pages(course, html_folder, course_folder, http)
        if materials := data.get("materials"):
            await download_materials(materials, course_folder / "material", http)
        return course, data
    except Exception as e:
        print(f"  Error processing {name}: {e}")
        return course, {}


async def main():
    cookie, html = await get_cookie()
    courses = parse_courses(html)
    if not courses:
        print("No courses found")
        save_config({k: v for k, v in load_config().items() if k != "cookie"})
        return

    async with Http(cookie) as http:
        print(f"Fetching {len(courses)} courses...")
        data: list[tuple[dict, dict]] = []
        for i, course in enumerate(courses, 1):
            print(f"  [{i}/{len(courses)}] {course['name']}")
            try:
                data.append(await process_course(course, APP_DIR / "html", APP_DIR / "courses", http))
            except Exception as e:
                print(f"    Error: {e}")
                data.append((course, {}))

    write_file(APP_DIR / "index.html", generate_html(data, APP_DIR / "courses"))
    # Copy favicon to APP_DIR if it exists
    icon_src = Path(__file__).parent / "btu.ico"
    if icon_src.exists():
        import shutil
        shutil.copy(icon_src, APP_DIR / "btu.ico")
    print(f"Generated {APP_DIR / 'index.html'}")
    os.chdir(APP_DIR)
    serve_and_open(1111)


if __name__ == "__main__":
    asyncio.run(main())

# pyinstaller -n btu --onedir --clean --noupx --windowed --optimize 2 --icon btu.ico main.py
