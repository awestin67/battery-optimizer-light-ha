# Battery Optimizer Light
# Copyright (C) 2026 @awestin67
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import subprocess
import sys
import os
import shutil
from collections import OrderedDict
from pathlib import Path

def get_project_python() -> Path:
    """Tries to find the python executable in the local .venv"""
    project_root = Path(__file__).resolve().parent
    venv_path_win = project_root / ".venv" / "Scripts" / "python.exe"
    venv_path_nix = project_root / ".venv" / "bin" / "python"

    if venv_path_win.exists():
        return venv_path_win
    elif venv_path_nix.exists():
        return venv_path_nix
    return Path(sys.executable)

python_exe = get_project_python()

# Förhindra att skriptet körs utanför den lokala virtuella miljön
if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(os.path.abspath(python_exe)):
    print("❌ Varning: Skriptet verkar köras utanför den virtuella miljön!")
    print(f"👉 Vänligen aktivera din .venv och kör skriptet igen (t.ex: '{python_exe} release.py')")
    sys.exit(1)

try:
    import requests
    # Kontrollera att det är rätt requests-bibliotek och inte en lokal mapp
    if not hasattr(requests, "post"):
        print("❌ FEL: Det finns en lokal mapp som heter 'requests' i projektet som skuggar biblioteket.")
        print("   Detta gör att Python laddar din mapp istället för 'requests'-paketet.")
        print("   👉 Lösning: Ta bort mapparna 'requests', 'Lib' och 'site-packages' från projektroten.")
        sys.exit(1)
except ImportError:
    sys.exit("❌ Modulen 'requests' saknas. Installera den med: pip install requests")

# Försök ladda .env om python-dotenv finns
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- INSTÄLLNINGAR ---
# Korrekt sökväg baserat på ditt domännamn
BASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = BASE_DIR / "custom_components" / "battery_optimizer_light" / "manifest.json"

IGNORED_DIRS = {
    ".venv", "venv", "env", "__pycache__", ".git", ".pytest_cache",
    "requests", "Lib", "site-packages", "build", "dist"
}

def run_command(command, capture_output=False, exit_on_error=True):
    """Hjälpfunktion för att köra terminalkommandon enhetligt."""
    try:
        if capture_output:
            return subprocess.check_output(command, stderr=subprocess.DEVNULL, shell=False).decode('utf-8').strip()
        subprocess.run(command, check=True, shell=False)
        return ""
    except subprocess.CalledProcessError as e:
        if exit_on_error:
            cmd_str = ' '.join(command) if isinstance(command, list) else command
            print(f"❌ Fel vid kommando: {cmd_str}")
            sys.exit(1)
        raise e

def get_current_version(file_path: Path):
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except FileNotFoundError:
        print(f"❌ Hittade inte filen: {file_path}")
        print("👉 Kontrollera att mappen 'custom_components/battery_optimizer_light' finns.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Filen {file_path} innehåller ogiltig JSON.")
        sys.exit(1)

def bump_version(version, part):
    major, minor, patch = map(int, version.split('.'))
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    return f"{major}.{minor}.{patch}"

def update_manifest(file_path: Path, new_version):
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data["version"] = new_version

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

def check_for_updates():
    print("\n--- 🔍 KOLLAR EFTER UPPDATERINGAR (SSH) ---")
    try:
        print("Hämtar status från GitHub...")
        run_command(["git", "fetch", "origin"])

        incoming = run_command(
            ["git", "log", "HEAD..origin/HEAD", "--oneline"], capture_output=True, exit_on_error=False
        )

        if incoming:
            print("\n❌ STOPP! GitHub har ändringar som du saknar:")
            print(incoming)
            print("👉 Kör 'git pull' först.")
            sys.exit(1)
        print("✅ Synkad med servern.")

    except Exception:
        print("⚠️  Kunde inte nå GitHub. Fortsätter ändå...")

def check_branch():
    """Varnar om man inte står på main-branchen"""
    try:
        branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, exit_on_error=False)
        if branch != "main":
            print(f"⚠️  Du står på branch '{branch}'. Rekommenderat är 'main'.")
            confirm = input("Vill du fortsätta ändå? (j/n): ")
            if confirm.lower() != 'j':
                sys.exit(1)
    except Exception:
        pass

def run_tests():
    print("\n--- 🧪 KÖR TESTER ---")
    try:
        test_dir = BASE_DIR / "tests"
        if not test_dir.exists() or not any(test_dir.iterdir()):
            print("⚠️  Inga tester hittades i 'tests/'. Hoppar över.")
            return

        subprocess.run(["pytest", "-v", str(test_dir)], check=True, shell=False)
        print("✅ Alla tester godkända.")
    except FileNotFoundError:
        print("⚠️  Kunde inte hitta 'pytest'.")
        print("👉 Kör: pip install -r requirements_test.txt")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("\n❌ Testerna misslyckades! Åtgärda felen innan release.")
        sys.exit(1)

def run_lint():
    print("\n--- 🧹 KÖR LINT (Ruff) ---")
    try:
        # Kör ruff i BASE_DIR
        subprocess.run(["ruff", "check", "."], cwd=str(BASE_DIR), check=True, shell=False)
        print("✅ Linting godkänd.")
    except FileNotFoundError:
        print("⚠️  Kunde inte hitta 'ruff'. Installera det med 'pip install ruff' för att köra kodgranskning.")
    except subprocess.CalledProcessError:
        print("\n❌ Linting misslyckades! Åtgärda felen innan release.")
        sys.exit(1)

def check_license_headers():
    """Kontrollerar att alla python-filer har rätt licens-header."""
    print("\n--- 📄 KONTROLLERAR LICENS-HEADERS ---")

    short_header = "Copyright (C) 2026 @awestin67"
    # Del av den långa GPL-texten för verifiering
    long_header_part = "This program is free software: you can redistribute it"

    missing_short = []
    missing_long = []

    for file_path in BASE_DIR.rglob("*.py"):
        # Ignorera mappar i IGNORED_DIRS
        if any(part in IGNORED_DIRS for part in file_path.parts):
            continue

        rel_path = file_path.relative_to(BASE_DIR)
        try:
            content = file_path.read_text(encoding="utf-8")

            # 1. Alla filer ska ha Copyright-raden
            if short_header not in content:
                missing_short.append(str(rel_path))
                continue

            # 2. Filer under custom_components ska ha lång header
            if "custom_components" in file_path.parts:
                if long_header_part not in content:
                    missing_long.append(str(rel_path))

        except Exception as e:
            print(f"⚠️  Kunde inte läsa {file_path}: {e}")

    failed = False
    if missing_short:
        print("❌ Följande filer saknar Copyright-header:")
        for f in missing_short:
            print(f"   - {f}")
        failed = True

    if missing_long:
        print("❌ Följande filer under custom_components saknar fullständig GPL-licenstext:")
        for f in missing_long:
            print(f"   - {f}")
        failed = True

    if failed:
        sys.exit(1)

    print("✅ Alla Python-filer har korrekt licens-header.")

def sort_manifest_keys(file_path: Path):
    """Sorterar nycklar i manifest.json enligt Hassfest-krav: domain, name, sedan alfabetiskt."""
    print(f"\n--- 🔧 FIXAR SORTERING I {file_path.name} ---")
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Spara undan domain och name
        domain = data.pop("domain", None)
        name = data.pop("name", None)

        # Skapa en ny OrderedDict
        new_data = OrderedDict()
        if domain:
            new_data["domain"] = domain
        if name:
            new_data["name"] = name

        # Lägg till resten sorterat
        for key in sorted(data.keys()):
            new_data[key] = data[key]

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
            f.write("\n") # Lägg till nyrad på slutet

        print("✅ Manifest sorterat korrekt.")
    except Exception as e:
        print(f"⚠️  Kunde inte sortera manifest: {e}")

def run_hassfest_local():
    """Försöker köra hassfest via Docker om det finns tillgängligt."""
    print("\n--- 🏠 KÖR HASSFEST (Docker) ---")

    if not shutil.which("docker"):
        print("⚠️  Docker hittades inte i PATH. Hoppar över lokal Hassfest-validering.")
        print("   (Installera Docker Desktop för att köra detta lokalt)")
        return

    # Kolla om Docker daemon faktiskt svarar (är igång)
    try:
        run_command(["docker", "info"], capture_output=True, exit_on_error=False)
    except Exception:
        print("⚠️  Docker är installerat men verkar inte vara igång (Starta Docker Desktop!).")
        print("   Hoppar över lokal Hassfest-validering.")
        return

    try:
        cmd = [
            "docker", "run", "--rm", "-v", f"{BASE_DIR}:/github/workspace",
            "ghcr.io/home-assistant/hassfest:latest"
        ]
        run_command(cmd, exit_on_error=False)
        print("✅ Hassfest (Local) godkänd!")
    except subprocess.CalledProcessError:
        print("\n❌ Hassfest (eller Docker) returnerade ett fel.")
        print("   Om Docker inte är igång kan du ignorera detta (GitHub Actions kör kollen sen).")
        if input("   Vill du fortsätta ändå? (j/n): ").lower() != 'j':
            sys.exit(1)

def run_hacs_validation_local():
    """Validerar specifika HACS-krav lokalt (filer och manifest-data)."""
    print("\n--- 📦 HACS VALIDERING (Lokal) ---")

    # 1. Krav på informationsfil
    readme = BASE_DIR / "README.md"
    info = BASE_DIR / "info.md"

    if not readme.exists() and not info.exists():
        print("❌ HACS kräver att antingen 'README.md' eller 'info.md' finns i roten.")
        sys.exit(1)

    # 2. hacs.json (Valfritt men måste vara giltigt om det finns)
    hacs_path = BASE_DIR / "hacs.json"
    if hacs_path.exists():
        try:
            with hacs_path.open("r", encoding="utf-8") as f:
                json.load(f)
            print("✅ hacs.json är giltig.")
        except json.JSONDecodeError:
            print("❌ hacs.json innehåller ogiltig JSON.")
            sys.exit(1)

    # 3. Manifest-koll för länkar (HACS rekommendationer/krav)
    try:
        with MANIFEST_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        missing_keys = [k for k in ["documentation", "issue_tracker"] if k not in data]
        if missing_keys:
            print(f"⚠️  Manifest saknar fält som HACS rekommenderar: {', '.join(missing_keys)}")
        else:
            print("✅ Manifest innehåller dokumentationslänkar.")

    except Exception as e:
        print(f"⚠️  Kunde inte läsa manifest för HACS-koll: {e}")

def check_images():
    """Kollar att bilder finns för HA UI och skapar icon.png om den saknas."""
    print("\n--- 🖼️  KOLLAR BILDER ---")
    comp_dir = BASE_DIR / "custom_components" / "battery_optimizer_light"
    logo_path = comp_dir / "logo.png"
    icon_path = comp_dir / "icon.png"

    if logo_path.exists() and (not icon_path.exists() or icon_path.stat().st_size == 0):
        print("⚠️  icon.png saknas (krävs för integrationslistan).")
        print("   Kopierar logo.png till icon.png...")
        shutil.copyfile(logo_path, icon_path)
        print("✅ icon.png skapad.")
    elif icon_path.exists():
        print("✅ icon.png finns.")
    else:
        print("⚠️  Ingen logo.png hittades. Integrationen kommer sakna bilder i HA.")

def get_github_repo_slug():
    """Hämtar 'user/repo' från git config."""
    try:
        remote_url = run_command(
            ["git", "config", "--get", "remote.origin.url"], capture_output=True, exit_on_error=False
        )
        if "github.com" in remote_url:
            slug = remote_url.split("github.com")[-1].replace(":", "/").lstrip("/")
            if slug.endswith(".git"):
                slug = slug[:-4]
            return slug
    except Exception:
        pass
    return None

def check_github_metadata(repo_slug, token):
    """Kontrollerar och uppdaterar GitHub-metadata (Beskrivning & Ämnen)."""
    if not repo_slug:
        return

    print("\n--- 🏷️  GITHUB METADATA ---")

    if not token:
        print("⚠️  Ingen GITHUB_TOKEN hittad. Hoppar över automatisk kontroll av metadata.")
        print("   👉 Du måste manuellt ange Beskrivning och Topics på GitHub för att HACS-valideringen ska passera.")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"https://api.github.com/repos/{repo_slug}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"⚠️  Kunde inte hämta metadata: {resp.status_code}")
            return

        data = resp.json()
        description = data.get("description")
        topics = data.get("topics", [])

        needs_update = False
        new_description = description
        new_topics = topics

        if not description:
            print("❌ Repository saknar beskrivning (Krävs av HACS).")
            new_description = input("Ange beskrivning: ").strip()
            if new_description:
                needs_update = True

        if not topics:
            print("❌ Repository saknar ämnen/topics (Krävs av HACS).")
            print("Förslag: home-assistant, integration, hacs, sonnen, battery")
            topics_str = input("Ange topics (komma-separerad): ").strip()
            if topics_str:
                new_topics = [t.strip() for t in topics_str.split(",") if t.strip()]
                needs_update = True

        if needs_update:
            print("Uppdaterar GitHub...")
            patch_data = {}
            if new_description:
                patch_data["description"] = new_description
            if new_topics:
                patch_data["topics"] = new_topics

            p_resp = requests.patch(url, json=patch_data, headers=headers, timeout=10)
            if p_resp.status_code == 200:
                print("✅ GitHub-metadata uppdaterad!")
            else:
                print(f"❌ Misslyckades uppdatera: {p_resp.status_code}")
        else:
            print("✅ Metadata OK.")

    except Exception as e:
        print(f"⚠️  Fel vid metadatakontroll: {e}")

def create_github_release(version, repo_slug=None, diff_uncommitted=""):
    print("\n--- 🚀 SKAPA GITHUB RELEASE ---")

    # Hitta repo-namn från git config
    repo_part = repo_slug
    if not repo_part:
        repo_part = get_github_repo_slug()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("\n⚠️  Ingen GITHUB_TOKEN hittad.")
        print("   (GitHub kräver token för att skapa releaser via API, även för publika repon)")
        print("   (Tips: Lägg GITHUB_TOKEN i .env och kör 'pip install python-dotenv')")

        url = f"https://github.com/{repo_part}/releases/new?tag=v{version}" if repo_part else f"https://github.com/awestin67/battery-optimizer-light-ha/releases/new?tag=v{version}"
        print(f"👉 Skapa release manuellt här: {url}")
        return

    if not repo_part:
        print("⚠️  Kunde inte identifiera GitHub-repo (ingen github.com i remote).")
        return

    if input("Vill du skapa en GitHub Release nu? (j/n): ").lower() != 'j':
        print(f"👉 Du kan skapa releasen manuellt här: https://github.com/{repo_part}/releases/new?tag=v{version}")
        return

    # Försök hämta commits sedan förra taggen
    commits = ""
    try:
        tags_str = run_command(["git", "tag", "--sort=-creatordate"], capture_output=True, exit_on_error=False)
        tags = tags_str.splitlines() if tags_str else []

        if len(tags) >= 2:
            prev_tag = tags[1]
            commits_out = run_command(
                ["git", "log", f"{prev_tag}..HEAD", "--pretty=format:- %s"],
                capture_output=True,
                exit_on_error=False,
            )
        else:
            # Om det inte finns någon tidigare tagg, ta de 20 senaste commitarna
            commits_out = run_command(
                ["git", "log", "-n", "20", "--pretty=format:- %s"],
                capture_output=True,
                exit_on_error=False,
            )

        # Filtrera bort release-commiten
        lines = [
            line for line in commits_out.splitlines()
            if f"Release {version}" not in line and f"Release v{version}" not in line
        ]
        commits = "\n".join(lines)
    except Exception:
        pass

    diff = ""
    if diff_uncommitted:
        # Trunkera diffen till max 20 000 tecken ifall den skulle bli gigantisk
        if len(diff_uncommitted) > 20000:
            diff = diff_uncommitted[:20000] + "\n... [diff trunkerad]"
        else:
            diff = diff_uncommitted

    suggested_notes = ""
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key and (commits or diff):
        print("\n🤖 Ber Gemini AI att summera release notes...")
        prompt = f"Skapa snygga, kategoriserade release notes på engelska för version {version}.\n"
        prompt += "Kategorisera dem med emojis (t.ex. 🚀 Features, 🐛 Fixes, 🔧 Refactoring).\n\n"

        if commits:
            prompt += f"Här är commit-historiken:\n{commits}\n\n"

        if diff:
            prompt += f"Här är osparade kodändringar (diff):\n{diff}\n\n"

        url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers_gemini = {"Content-Type": "application/json"}
        payload_gemini = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            resp_gemini = requests.post(url_gemini, json=payload_gemini, headers=headers_gemini, timeout=30)
            if resp_gemini.status_code == 200:
                data = resp_gemini.json()
                ai_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if ai_text:
                    print("✅ AI-förslag skapat!")
                    suggested_notes = ai_text.strip()
            else:
                print(f"⚠️ Kunde inte generera AI-release notes: API svarade med {resp_gemini.status_code}")
        except Exception as e:
            print(f"⚠️ Kunde inte generera AI-release notes: {e}")

    # Fallback om vi inte har AI eller det misslyckades
    if not suggested_notes and commits:
        suggested_notes = commits

    if suggested_notes:
        print("\n📝 Föreslagna release notes:")
        print("-" * 40)
        print(suggested_notes)
        print("-" * 40)
        print("Tryck ENTER för att använda dessa, eller skriv egna nedan.")
        print("(Avsluta inmatningen genom att trycka ENTER på en tom rad)")
    else:
        print("Skriv in release notes.")
        print("(Avsluta inmatningen genom att trycka ENTER på en tom rad)")

    notes = ""
    lines = []
    first_line = True
    try:
        while True:
            line = input("> ")
            if first_line and not line and suggested_notes:
                notes = suggested_notes
                break

            if not line:
                break
            lines.append(line)
            first_line = False
    except KeyboardInterrupt:
        print("\n⚠️  Avbröt inmatning. Hoppar över GitHub Release.")
        return

    if lines:
        notes = "\n".join(lines).strip()

    if not notes:
        notes = f"Release v{version}"

    print(f"🚀 Skapar GitHub Release på {repo_part}...")

    url = f"https://api.github.com/repos/{repo_part}/releases"
    payload = {
        "tag_name": f"v{version}",
        "name": f"v{version}",
        "body": notes,
        "draft": False,
        "prerelease": False
    }
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 201:
            print(f"✅ Release v{version} skapad på GitHub!")
            print(f"🔗 Länk: {resp.json().get('html_url')}")
        else:
            print(f"❌ Misslyckades skapa release: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"❌ Fel vid API-anrop: {e}")

def main():
    # 1. Säkerhetskollar
    check_branch()
    repo_slug = get_github_repo_slug()

    run_tests()
    run_lint()
    check_license_headers()
    sort_manifest_keys(MANIFEST_PATH) # Fixar sorteringen automatiskt före release
    run_hassfest_local() # Kör Hassfest via Docker
    run_hacs_validation_local() # Kör lokal HACS-koll
    check_images()
    check_for_updates()
    check_github_metadata(repo_slug, os.getenv("GITHUB_TOKEN"))

    # 2. Hämta nuvarande version
    current_ver = get_current_version(MANIFEST_PATH)
    print(f"\n🔹 Nuvarande HA-version: {current_ver}")

    # 3. Fråga om ny version
    print("\nVilken typ av uppdatering?")
    print("1. Patch (Bugfix) -> x.x.+1")
    print("2. Minor (Feature) -> x.+1.0")
    print("3. Major (Breaking) -> +1.0.0")
    choice = input("Val: ")

    type_map = {"1": "patch", "2": "minor", "3": "major"}
    if choice not in type_map:
        print("❌ Ogiltigt val. Avbryter.")
        return

    new_ver = bump_version(current_ver, type_map[choice])
    print(f"➡️  Ny version blir: {new_ver}")

    confirm = input("Vill du uppdatera manifest.json och pusha? (j/n): ")
    if confirm.lower() != 'j':
        return

    # Hämta osparade ändringar (diff) INNAN vi committar dem
    try:
        uncommitted_diff = run_command(["git", "diff", "HEAD"], capture_output=True, exit_on_error=False)
    except Exception:
        uncommitted_diff = ""

    # 4. Uppdatera filen
    update_manifest(MANIFEST_PATH, new_ver)
    print(f"\n✅ {MANIFEST_PATH} uppdaterad.")

    # 5. Git Commit & Push & Tag
    print("\n--- 💾 SPARAR TILL GITHUB ---")

    # VIKTIGT: Lägg till alla ändringar (inklusive om du ändrade länken manuellt nyss)
    run_command(["git", "add", "."])

    run_command(["git", "commit", "-m", f"Release {new_ver}"])

    # Skapa tagg för HACS
    tag_name = f"v{new_ver}"
    print(f"🏷️  Skapar tagg: {tag_name}")
    run_command(["git", "tag", tag_name])

    print("☁️  Pushar commit och taggar...")
    run_command(["git", "push"])
    run_command(["git", "push", "--tags"])

    create_github_release(new_ver, repo_slug, uncommitted_diff)

    print(f"\n✨ KLART! Version {new_ver} är publicerad.")

if __name__ == "__main__":
    main()
