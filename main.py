from dotenv import load_dotenv
load_dotenv()

import os
import urllib.request
import subprocess
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cookie": os.getenv("cookie"),
}

BASE_URL = "https://classroom.btu.edu.ge/en/student/me/courses"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_binary(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req) as r:
        return r.read()


def copy_to_clipboard(data: str) -> None:
    p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE)
    p.communicate(data.encode("utf-16le"))


def parse_num(td) -> float | str:
    txt = td.get_text(strip=True).replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return txt


def parse_courses(html: str) -> tuple[list[dict], float | str | None]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table.table-striped.table-bordered.table-hover.fluid")
    if not table:
        return [], None

    tbody = table.find("tbody")
    if not tbody:
        return [], None

    courses, total_ects = [], None

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")

        if len(tds) == 2 and not tds[0].get_text(strip=True):
            total_ects = parse_num(tds[-1])
            continue

        if len(tds) != 6:
            continue

        name_a = tds[2].find("a")
        courses.append({
            "name": name_a.get_text(strip=True) if name_a else tds[2].get_text(strip=True),
            "grade": parse_num(tds[3]),
            "ects": parse_num(tds[5]),
            "url": name_a["href"] if name_a and name_a.has_attr("href") else None,
        })

    return courses, total_ects


def extract_course_urls(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = {}

    tabs = soup.select_one("#course_tabs")
    if tabs:
        for link in tabs.find_all("a", href=True):
            href = link["href"]
            if "silabus" in href:
                urls["syllabus"] = href
            elif "groups" in href:
                urls["groups"] = href
            elif "scores" in href:
                urls["scores"] = href
            elif "files" in href:
                urls["files"] = href

    syllabus_file = soup.select_one('a[href*="courseSilabusFile"]')
    if syllabus_file:
        urls["syllabus_file"] = syllabus_file["href"]

    return urls


def parse_scores(html: str) -> dict:
    """Extract scores/evaluations from scores.html"""
    import re
    soup = BeautifulSoup(html, "html.parser")
    data = {"group": None, "lector": None, "assessments": []}

    h4 = soup.select_one(".tab_scores h4")
    if h4:
        text = h4.get_text(" ", strip=True)
        if "Group" in text:
            parts = text.split(" - ", 1)
            data["group"] = parts[0].replace("Group", "").strip()
        lector_link = h4.select_one("a[href*='/lector/']")
        if lector_link:
            data["lector"] = lector_link.get_text(strip=True)

    table = soup.select_one(".tab_scores table")
    if table:
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            
            component = tds[0].get_text(strip=True)
            score = tds[1].get_text(strip=True)
            
            if component in ("სულ", "Credits") or "გამოცდაზე გასვლის" in component:
                continue
            
            if component:
                # Extract max points from component name like "(max. 8)" or "(min. 12.3, max. 30)"
                max_points = None
                max_match = re.search(r'max\.?\s*([\d.,]+)', component)
                if max_match:
                    try:
                        max_points = float(max_match.group(1).replace(',', '.'))
                    except ValueError:
                        pass
                
                data["assessments"].append({"component": component, "score": score or None, "max_points": max_points})

    return data


def parse_files(html: str, my_lector: str | None = None) -> list[dict]:
    """Extract training materials from files.html, optionally filtered by lector"""
    soup = BeautifulSoup(html, "html.parser")
    materials = []
    current_lector = None

    table = soup.select_one("#files")
    if not table:
        return materials

    for tr in table.find_all("tr"):
        lector_link = tr.select_one("a[href*='/lector/']")
        tr_class = tr.get("class") or []
        if lector_link and "info" in tr_class:
            current_lector = lector_link.get_text(strip=True)
            continue

        # Skip materials from other lectors
        if my_lector and current_lector and current_lector.lower() != my_lector.lower():
            continue

        tds = tr.find_all("td")
        if not tds:
            continue

        file_link = tds[0].select_one("a[href*='/uploads/']")
        name = tds[0].get_text(strip=True)
        url = file_link["href"] if file_link and file_link.get("href") else None

        ext_link = tds[1].select_one("a") if len(tds) > 1 else None
        ext_url = ext_link["href"] if ext_link else None

        if name:
            materials.append({
                "name": name,
                "url": url,
                "external_url": ext_url,
            })

    return materials


def parse_groups(html: str) -> dict:
    """Extract group info from groups.html (often empty)"""
    soup = BeautifulSoup(html, "html.parser")
    # Groups page often shows "Groups Not found" - check for available groups
    table = soup.select_one("#groups")
    if not table:
        return {"groups": []}
    
    groups = []
    for tr in table.find_all("tr"):
        if "warning" in (tr.get("class") or []):
            continue
        text = tr.get_text(strip=True)
        if text and "Not found" not in text:
            groups.append(text)
    
    return {"groups": groups}


def parse_course_data(folder: str) -> dict:
    """Parse all HTML files in a course folder"""
    data = {}
    
    scores_path = f"{folder}/scores.html"
    if os.path.exists(scores_path):
        with open(scores_path, encoding="utf-8") as f:
            data["scores"] = parse_scores(f.read())
    
    my_lector = data.get("scores", {}).get("lector")
    
    files_path = f"{folder}/files.html"
    if os.path.exists(files_path):
        with open(files_path, encoding="utf-8") as f:
            data["materials"] = parse_files(f.read(), my_lector)
    
    groups_path = f"{folder}/groups.html"
    if os.path.exists(groups_path):
        with open(groups_path, encoding="utf-8") as f:
            data["groups"] = parse_groups(f.read())
    
    return data


def fetch_course_pages(course: dict) -> str:
    if not course["url"]:
        return ""

    course_name = course["name"]
    html_folder = f"html/{course_name}"
    course_folder = f"courses/{course_name}"
    os.makedirs(html_folder, exist_ok=True)
    os.makedirs(course_folder, exist_ok=True)
    os.makedirs(f"{course_folder}/material", exist_ok=True)

    # Always refetch course page (contains links)
    course_html = fetch(course["url"])
    urls = extract_course_urls(course_html)

    with open(f"{html_folder}/course.html", "w", encoding="utf-8") as f:
        f.write(course_html)

    for name, url in urls.items():
        if name == "syllabus_file":
            # Syllabus PDF doesn't change - skip if exists
            if not os.path.exists(f"{course_folder}/syllabus.pdf"):
                data = fetch_binary(url)
                with open(f"{html_folder}/{name}.pdf", "wb") as f:
                    f.write(data)
                with open(f"{course_folder}/syllabus.pdf", "wb") as f:
                    f.write(data)
        elif name == "scores":
            # Scores change - always refetch
            with open(f"{html_folder}/{name}.html", "w", encoding="utf-8") as f:
                f.write(fetch(url))
        elif name == "files":
            # Files page may have new materials - always refetch
            with open(f"{html_folder}/{name}.html", "w", encoding="utf-8") as f:
                f.write(fetch(url))
        else:
            # syllabus, groups - don't change, skip if exists
            if not os.path.exists(f"{html_folder}/{name}.html"):
                with open(f"{html_folder}/{name}.html", "w", encoding="utf-8") as f:
                    f.write(fetch(url))

    return course_html


def download_materials(materials: list[dict], folder: str) -> None:
    """Download all training materials to folder"""
    for m in materials:
        if not m["url"]:
            continue
        filename = m["url"].split("/")[-1]
        filepath = f"{folder}/{filename}"
        if os.path.exists(filepath):
            continue
        try:
            with open(filepath, "wb") as f:
                f.write(fetch_binary(m["url"]))
        except Exception as e:
            print(f"  Failed to download {filename}: {e}")


def print_course_info(course: dict, data: dict) -> None:
    """Print course information nicely"""
    scores = data.get("scores", {})
    
    print(f"{course['name']} ({int(course['ects'])} ECTS) - {course['grade']}")
    print(f"  Group: {scores.get('group')}, Lector: {scores.get('lector')}")
    
    for a in scores.get("assessments", []):
        if a["score"]:
            print(f"    {a['component']}: {a['score']}")
    
    materials = data.get("materials", [])
    if materials:
        print(f"  Materials ({len(materials)}):")
        for m in materials:
            print(f"    - {m['name']}")
    
    print()


def get_grade_color(grade: float) -> str:
    """Return color based on grade"""
    if grade >= 91:
        return "#22c55e"  # green
    elif grade >= 81:
        return "#84cc16"  # lime
    elif grade >= 71:
        return "#eab308"  # yellow
    elif grade >= 61:
        return "#f97316"  # orange
    elif grade >= 51:
        return "#ef4444"  # red
    else:
        return "#991b1b"  # dark red


def get_percentage_color(percentage: float) -> str:
    """Return color based on percentage (0-100)"""
    if percentage >= 91:
        return "#22c55e"  # green
    elif percentage >= 81:
        return "#84cc16"  # lime
    elif percentage >= 71:
        return "#eab308"  # yellow
    elif percentage >= 61:
        return "#f97316"  # orange
    elif percentage >= 51:
        return "#ef4444"  # red
    else:
        return "#991b1b"  # dark red


def fmt_num(val) -> str:
    """Format number, removing trailing .0"""
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val)


def generate_course_html(course: dict, data: dict) -> str:
    """Generate HTML for a single course card"""
    scores = data.get("scores", {})
    materials = data.get("materials", [])
    grade = course["grade"]
    
    # Calculate max possible grade at this point in the semester
    # Sum up max_points for all assessments that have been graded (have a score)
    max_possible = 0
    for a in scores.get("assessments", []):
        if a.get("score") and a.get("max_points"):
            max_possible += a["max_points"]
    
    # Color based on percentage of max possible, not absolute grade
    if isinstance(grade, (int, float)) and max_possible > 0:
        percentage = (float(grade) / max_possible) * 100
        grade_color = get_percentage_color(percentage)
        grade_display = f"{fmt_num(grade)}/{fmt_num(max_possible)}"
        # Omit badge for 0% and 100% since they're obvious
        if 0 < percentage < 100:
            pct_badge = f'<span class="pct-badge" style="background: {grade_color}20; color: {grade_color}">{percentage:.0f}%</span>'
        else:
            pct_badge = ""
    elif isinstance(grade, (int, float)):
        grade_color = get_grade_color(float(grade))
        grade_display = fmt_num(grade)
        pct_badge = ""
    else:
        grade_color = "#52525b"
        grade_display = str(grade)
        pct_badge = ""
    
    course_folder = f"courses/{course['name']}"
    syllabus_path = f"{course_folder}/syllabus.pdf"
    has_syllabus = os.path.exists(syllabus_path)
    
    # Build assessments HTML
    assessments_html = ""
    for a in scores.get("assessments", []):
        raw_score = a["score"]
        max_points = a.get("max_points")
        if raw_score:
            # Try to format as number
            try:
                score_val = float(raw_score.replace(",", "."))
                score_formatted = fmt_num(score_val)
            except (ValueError, AttributeError):
                score_formatted = raw_score
                score_val = None
            
            # Display as score/max if max_points available
            if max_points:
                score_display = f"{score_formatted}/{fmt_num(max_points)}"
                # Calculate percentage for color
                if score_val is not None:
                    percentage = (score_val / max_points) * 100
                    color = get_percentage_color(percentage)
                    score_class = f'" style="color: {color}'
                    # Omit badge for 0% and 100% since they're obvious
                    if 0 < percentage < 100:
                        pct_badge = f'<span class="pct-badge" style="background: {color}20; color: {color}">{percentage:.0f}%</span>'
                    else:
                        pct_badge = ""
                else:
                    score_class = ""
                    pct_badge = ""
            else:
                score_display = score_formatted
                score_class = ""
                pct_badge = ""
        else:
            score_display = "—"
            score_class = " empty"
            pct_badge = ""
        name = a["component"]
        if "(" in name:
            name = name.split("(")[0].strip()
        assessments_html += f'<span class="assessment"><span class="assessment-name">{name}</span><span class="assessment-score{score_class}">{score_display}</span>{pct_badge}</span>'
    
    # Build syllabus link for header
    syllabus_html = ""
    if has_syllabus:
        syllabus_html = f'<a href="{syllabus_path}" class="syllabus-link" target="_blank">Syllabus</a>'
    
    # Build materials section - expandable
    materials_html = ""
    if materials:
        material_links = ""
        for m in materials:
            if m["url"]:
                filename = m["url"].split("/")[-1]
                filepath = f"{course_folder}/material/{filename}"
                material_links += f'<a href="{filepath}" class="material" target="_blank">{m["name"]}</a>'
        materials_html = f'''<div class="materials-section">
        <div class="materials-toggle"><span class="arrow">▶</span> Materials ({len(materials)})</div>
        <div class="materials">{material_links}</div>
    </div>'''
    
    return f'''<div class="course">
    <div class="course-header">
        <div class="course-info">
            <div class="course-name">{course['name']}</div>
            <div class="course-meta">Group {scores.get('group', '?')} · {scores.get('lector', 'Unknown')}</div>
        </div>
        {syllabus_html}
        <span class="ects">{int(course['ects'])} ECTS</span>
        <div class="grade" style="color: {grade_color}">{grade_display}{pct_badge}</div>
    </div>
    <div class="assessments">{assessments_html}</div>
    {materials_html}
</div>'''


def generate_summary_html(courses_data: list[tuple[dict, dict]], total_ects: float | str | None) -> str:
    """Generate HTML for summary section"""
    total_score = 0
    total_max_possible = 0
    total_ects_earned = 0
    course_count = len(courses_data)
    
    # Calculate totals per course (score earned vs max possible so far)
    course_percentages = []  # List of (percentage, ects) for GPA calculation
    
    for course, data in courses_data:
        grade = course["grade"]
        ects = course["ects"]
        
        if isinstance(grade, (int, float)):
            total_score += grade
        
        # Calculate max possible from assessments that have been graded
        course_max = 0
        for a in data.get("scores", {}).get("assessments", []):
            if a.get("score") and a.get("max_points"):
                course_max += a["max_points"]
        
        total_max_possible += course_max
        
        # Calculate current percentage for this course
        if isinstance(grade, (int, float)) and course_max > 0 and isinstance(ects, (int, float)):
            pct = (grade / course_max) * 100
            course_percentages.append((pct, ects))
            total_ects_earned += ects
    
    # GPA calculation based on current percentages (weighted by ECTS, converted to 4.0 scale)
    # 91-100 = 4.0, 81-90 = 3.0, 71-80 = 2.0, 61-70 = 1.0, 51-60 = 0.5, <51 = 0
    weighted_gpa = 0
    for pct, ects in course_percentages:
        if pct >= 91:
            gpa_points = 4.0
        elif pct >= 81:
            gpa_points = 3.0
        elif pct >= 71:
            gpa_points = 2.0
        elif pct >= 61:
            gpa_points = 1.0
        elif pct >= 51:
            gpa_points = 0.5
        else:
            gpa_points = 0.0
        weighted_gpa += gpa_points * ects
    
    gpa = weighted_gpa / total_ects_earned if total_ects_earned > 0 else 0
    # Color based on GPA (4.0 scale -> percentage)
    gpa_pct = (gpa / 4.0) * 100
    gpa_color = get_percentage_color(gpa_pct)
    
    # Score percentage
    score_pct = (total_score / total_max_possible * 100) if total_max_possible > 0 else 0
    score_color = get_percentage_color(score_pct)
    # Omit badge for 0% and 100% since they're obvious
    if total_max_possible > 0 and 0 < score_pct < 100:
        score_pct_badge = f'<span class="pct-badge" style="background: {score_color}20; color: {score_color}">{score_pct:.0f}%</span>'
    else:
        score_pct_badge = ""
    
    return f'''<div class="summary">
    <div class="summary-item">
        <div class="summary-label">GPA</div>
        <div class="summary-value" style="color: {gpa_color}">{gpa:.2f}</div>
    </div>
    <div class="summary-item">
        <div class="summary-label">Total Score</div>
        <div class="summary-value" style="color: {score_color}">{fmt_num(total_score)}/{fmt_num(total_max_possible)} {score_pct_badge}</div>
    </div>
    <div class="summary-item">
        <div class="summary-label">Courses</div>
        <div class="summary-value" style="color: #a78bfa">{course_count}</div>
    </div>
    <div class="summary-item">
        <div class="summary-label">ECTS</div>
        <div class="summary-value" style="color: #a78bfa">{fmt_num(total_ects_earned)}</div>
    </div>
</div>'''


def generate_html(courses_data: list[tuple[dict, dict]], total_ects: float | str | None = None) -> str:
    """Generate HTML dashboard from template"""
    with open("template.html", encoding="utf-8") as f:
        template = f.read()
    
    courses_html = ""
    for course, data in courses_data:
        courses_html += generate_course_html(course, data)
    
    summary_html = generate_summary_html(courses_data, total_ects)
    
    return template.replace("{{COURSES}}", courses_html).replace("{{SUMMARY}}", summary_html)


def serve_and_open(port: int = 1111) -> None:
    import http.server
    import socketserver
    import webbrowser
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    
    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda self, *args: None  # type: ignore  # Suppress logs
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"Serving at {url}")
        
        # Open browser
        if "microsoft" in os.uname().release.lower():
            subprocess.run(["cmd.exe", "/c", "start", url], capture_output=True)
        else:
            webbrowser.open(url)
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")


if __name__ == "__main__":
    html = fetch(BASE_URL)
    courses, total_ects = parse_courses(html)

    courses_data = []
    
    for course in courses:
        fetch_course_pages(course)
        
        html_folder = f"html/{course['name']}"
        course_folder = f"courses/{course['name']}"
        data = parse_course_data(html_folder)
        
        materials = data.get("materials", [])
        if materials:
            download_materials(materials, f"{course_folder}/material")
        
        courses_data.append((course, data))
    
    # Generate HTML dashboard
    dashboard = generate_html(courses_data, total_ects)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(dashboard)
    print("Generated index.html")
    
    serve_and_open(1111)