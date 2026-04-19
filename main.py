from pathlib import Path
import argparse, json, os, subprocess, re, asyncio, zipfile
from bs4 import BeautifulSoup
import aiohttp

APP_DIR = (Path(os.environ.get('APPDATA', Path.home())) if os.name == 'nt' else Path.home() / '.config') / 'btu-dashboard'
BASE_URL = "https://classroom.btu.edu.ge/en/student/me/courses"
SCHEDULE_URL = "https://classroom.btu.edu.ge/en/student/me/schedule"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"}
COOKIE_FILE = APP_DIR / 'cookie.txt'

def load_config():
    try: return json.loads((APP_DIR / 'config.json').read_text())
    except: return {}


def save_config(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / 'config.json').write_text(json.dumps(cfg, indent=2))


def save_cookie(cookie: str) -> None:
    cfg = load_config()
    save_config({**cfg, "cookie": cookie})
    APP_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(cookie, encoding='utf-8')


def read_cookie_file(path: str | None) -> str:
    if not path:
        return ""

    cookie_path = Path(path)
    if cookie_path.is_file():
        return cookie_path.read_text(encoding='utf-8').strip()

    return ""


def resolve_cookie(cli_cookie: str = "", cookie_file: str = "") -> str:
    if cli_cookie.strip():
        return cli_cookie.strip()

    if env_cookie := os.environ.get('BTU_COOKIE', '').strip():
        return env_cookie

    if file_cookie := read_cookie_file(cookie_file):
        return file_cookie

    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text(encoding='utf-8').strip()

    return ""

def parse_num(td):
    try: return float(td.get_text(strip=True).replace(",", "."))
    except: return td.get_text(strip=True)


def clean_text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_time_range(value: str) -> tuple[int, int] | None:
    match = re.match(r'^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$', value)
    if not match:
        return None
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    return start, end


def format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def merge_schedule_entries(entries: list[dict]) -> list[dict]:
    merged: list[dict] = []

    for entry in entries:
        current_range = parse_time_range(entry.get("time", ""))
        if not merged or not current_range:
            copied = dict(entry)
            copied["_slot_end"] = current_range[1] if current_range else None
            merged.append(copied)
            continue

        previous = merged[-1]
        previous_range = parse_time_range(previous.get("time", ""))
        same_course = all(
            previous.get(key) == entry.get(key)
            for key in ("day", "room", "course", "group", "lecturers", "notes")
        )

        if previous_range and same_course and previous.get("_slot_end") is not None and previous["_slot_end"] + 10 == current_range[0]:
            previous["_slot_end"] = current_range[1]
            display_end = previous["_slot_end"] + 10
            previous["time"] = f"{format_time(previous_range[0])} - {format_time(display_end)}"
            continue

        copied = dict(entry)
        copied["_slot_end"] = current_range[1]
        merged.append(copied)

    for entry in merged:
        entry.pop("_slot_end", None)

    return merged

def generate_tabs_html() -> str:
    return '''<div class="tabs" role="tablist" aria-label="Dashboard sections"><button class="tab-button active" type="button" data-tab="grades" role="tab" aria-selected="true">Grades</button><button class="tab-button" type="button" data-tab="calendar" role="tab" aria-selected="false">Calendar</button><button class="tab-button" type="button" data-tab="exams" role="tab" aria-selected="false">Exams</button></div>'''


TEMPLATE = (Path(__file__).with_name("template.html").read_text(encoding="utf-8"))

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


def parse_schedule(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table#groups")
    if not table:
        return {"semester": None, "days": [], "entries": []}

    semester = clean_text(soup.select_one(".custom_pre_tag")) or None
    days: list[dict] = []
    entries: list[dict] = []
    current_day: dict | None = None

    for tr in table.select("tbody tr"):
        if tr.find("h4"):
            if current_day:
                days.append(current_day)
            current_day = {"day": clean_text(tr.find("h4")), "entries": []}
            continue

        cells = tr.find_all("td")
        if len(cells) != 6:
            continue

        row = [clean_text(cell) for cell in cells]
        if row[0].lower() in ("დრო", "time") or row[2].lower() in ("კურსის დასახელება", "course name"):
            continue
        if not current_day or not row[0]:
            continue

        entry = {
            "day": current_day["day"],
            "time": row[0],
            "room": row[1],
            "course": row[2],
            "group": row[3],
            "lecturers": row[4],
            "notes": row[5],
        }
        current_day["entries"].append(entry)
        entries.append(entry)

    if current_day:
        days.append(current_day)

    for day in days:
        day["entries"] = merge_schedule_entries(day["entries"])

    entries = merge_schedule_entries(entries)

    return {"semester": semester, "days": days, "entries": entries}


def parse_exams(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table")
    if not table:
        return {"title": None, "entries": []}

    entries: list[dict] = []
    for tr in table.select("tbody tr"):
        cells = [clean_text(cell) for cell in tr.find_all("td")]
        if len(cells) != 6:
            continue
        if cells[0].lower() in ("საგანი", "subject") or cells[1].lower() in ("დღე", "date"):
            continue

        entries.append({
            "subject": cells[0],
            "date": cells[1],
            "time": cells[2],
            "room": cells[3],
            "seat": cells[4],
            "format": cells[5],
        })

    return {"title": "Exam Schedule", "entries": entries}


def extract_course_urls(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = {}

    anchors = soup.select("a[href]")
    for a in anchors:
        href = a["href"]
        text = a.get_text(" ", strip=True).lower()
        for key, needles in {
            "syllabus": ("silabus", "syllabus"),
            "groups": ("groups",),
            "scores": ("scores",),
            "files": ("files", "materials", "training materials"),
        }.items():
            if any(needle in href.lower() or needle in text for needle in needles):
                urls[key] = href

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

    table = soup.select_one("#files")
    if not table:
        for candidate in soup.find_all("table"):
            if candidate.select_one('a[href*="/uploads/"]'):
                table = candidate
                break

    if not table:
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


def create_material_zip(folder: Path, zip_path: Path) -> None:
    if not folder.exists():
        return

    files = [path for path in folder.iterdir() if path.is_file()]
    if not files:
        return

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)

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
        zip_link = f'<a href="{folder}/material.zip" class="material" target="_blank">Download ZIP</a>' if (base / course['name'] / "material.zip").exists() else ""
        links = "".join(f'<a href="{folder}/material/{m["url"].split("/")[-1]}" class="material" target="_blank">{m["name"]}</a>' for m in materials if m["url"])
        mat_html = f'<div class="materials-section"><div class="materials-toggle"><span class="arrow">▶</span> Materials ({len(materials)})</div><div class="materials">{zip_link}{links}</div></div>'
    
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


def generate_html(data: list[tuple[dict, dict]], base: Path, schedule: dict) -> str:
    schedule_json = json.dumps(schedule, ensure_ascii=False).replace("</", "<\\/")
    exams_json = json.dumps(schedule.get("exams", {"title": None, "entries": []}), ensure_ascii=False).replace("</", "<\\/")
    return (
        TEMPLATE.replace("{{TABS}}", generate_tabs_html())
        .replace("{{COURSES}}", "".join(generate_course_html(c, d, base) for c, d in data))
        .replace("{{SUMMARY}}", generate_summary_html(data))
        .replace("{{COURSE_COUNT}}", str(len(data)))
        .replace("{{SCHEDULE_SEMESTER}}", schedule.get("semester") or "Schedule")
        .replace("{{SCHEDULE_JSON}}", schedule_json)
        .replace("{{EXAMS_JSON}}", exams_json)
    )


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
    print("Please login in the browser...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False)
        except Exception:
            print("Installing browser...")
            import sys
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://classroom.btu.edu.ge/login")
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


async def get_cookie(cli_cookie: str = "", cookie_file: str = "", headless: bool = False) -> tuple[str, str]:
    cfg = load_config()

    cookie = resolve_cookie(cli_cookie, cookie_file)
    if not cookie and (cfg_cookie := cfg.get("cookie", "")):
        cookie = cfg_cookie

    html = ""
    if cookie:
        html = await test_cookie(cookie)
        if not html:
            print("Saved cookie expired or is invalid.")

    if not html:
        if headless:
            raise RuntimeError("No valid BTU cookie found. Pass --cookie, --cookie-file, or set BTU_COOKIE.")
        cookie = await login()
        save_cookie(cookie)
        html = await test_cookie(cookie)

    if not html:
        raise RuntimeError("Unable to authenticate with BTU Classroom.")

    return cookie, html


async def process_course(course: dict, html_base: Path, course_base: Path, http: Http) -> tuple[dict, dict]:
    name = course['name']
    html_folder, course_folder = html_base / name, course_base / name
    try:
        data = await fetch_course_pages(course, html_folder, course_folder, http)
        if materials := data.get("materials"):
            await download_materials(materials, course_folder / "material", http)
            create_material_zip(course_folder / "material", course_folder / "material.zip")
        return course, data
    except Exception as e:
        print(f"  Error processing {name}: {e}")
        return course, {}


async def main(cli_cookie: str = "", cookie_file: str = "", headless: bool = False):
    cookie, html = await get_cookie(cli_cookie, cookie_file, headless)
    courses = parse_courses(html)
    if not courses:
        print("No courses found")
        save_config({k: v for k, v in load_config().items() if k != "cookie"})
        return

    schedule = {"semester": None, "days": [], "entries": [], "exams": {"title": None, "entries": []}}
    APP_DIR.mkdir(parents=True, exist_ok=True)

    async with Http(cookie) as http:
        try:
            schedule_html = str(await http.get(SCHEDULE_URL))
            schedule = parse_schedule(schedule_html)
            html_dir = APP_DIR / "html"
            html_dir.mkdir(parents=True, exist_ok=True)
            write_file(html_dir / "schedule.html", schedule_html)
            write_file(APP_DIR / "schedule.json", json.dumps(schedule, ensure_ascii=False, indent=2))
            print(f"Extracted schedule: {len(schedule['days'])} days, {len(schedule['entries'])} classes")
        except Exception as e:
            print(f"Schedule extraction failed: {e}")

        try:
            exams_html = str(await http.get("https://classroom.btu.edu.ge/en/exams/list"))
            exams = parse_exams(exams_html)
            schedule["exams"] = exams
            write_file(html_dir / "exams.html", exams_html)
            write_file(APP_DIR / "exams.json", json.dumps(exams, ensure_ascii=False, indent=2))
            print(f"Extracted exams: {len(exams['entries'])} items")
        except Exception as e:
            print(f"Exams extraction failed: {e}")

        print(f"Fetching {len(courses)} courses...")
        data: list[tuple[dict, dict]] = []
        for i, course in enumerate(courses, 1):
            print(f"  [{i}/{len(courses)}] {course['name']}")
            try:
                data.append(await process_course(course, APP_DIR / "html", APP_DIR / "courses", http))
            except Exception as e:
                print(f"    Error: {e}")
                data.append((course, {}))

    write_file(APP_DIR / "index.html", generate_html(data, APP_DIR / "courses", schedule))
    # Copy favicon to APP_DIR if it exists
    icon_src = Path(__file__).parent / "btu.ico"
    if icon_src.exists():
        import shutil
        shutil.copy(icon_src, APP_DIR / "btu.ico")
    print(f"Generated {APP_DIR / 'index.html'}")
    if not headless:
        os.chdir(APP_DIR)
        serve_and_open(1111)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BTU Classroom dashboard")
    parser.add_argument("--cookie", default="", help="BTU session cookie string")
    parser.add_argument("--cookie-file", default="", help="Path to a file containing the BTU session cookie")
    parser.add_argument("--headless", action="store_true", help="Do not open a browser for login; require an existing cookie")
    args = parser.parse_args()
    asyncio.run(main(args.cookie, args.cookie_file, args.headless))

# pyinstaller -n btu --onedir --clean --noupx --windowed --optimize 2 --icon btu.ico main.py