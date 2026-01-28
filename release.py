import json
import subprocess
import sys
import os

# --- INSTÄLLNINGAR ---
# Korrekt sökväg baserat på ditt domännamn
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, "custom_components", "battery_optimizer_light", "manifest.json")

def run_command(command):
    """Hjälpfunktion för att köra terminalkommandon"""
    try:
        subprocess.run(command, check=True, shell=False)
    except subprocess.CalledProcessError:
        cmd_str = ' '.join(command) if isinstance(command, list) else command
        print(f"❌ Fel vid kommando: {cmd_str}")
        sys.exit(1)

def get_current_version(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
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

def update_manifest(file_path, new_version):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["version"] = new_version

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def check_for_updates():
    print("\n--- 🔍 KOLLAR EFTER UPPDATERINGAR (SSH) ---")
    try:
        print("Hämtar status från GitHub...")
        run_command(["git", "fetch", "origin"])

        incoming = subprocess.check_output(
            ["git", "log", "HEAD..origin/HEAD", "--oneline"],
            shell=False
        ).decode().strip()

        if incoming:
            print("\n❌ STOPP! GitHub har ändringar som du saknar:")
            print(incoming)
            print("👉 Kör 'git pull' först.")
            sys.exit(1)
        print("✅ Synkad med servern.")

    except subprocess.CalledProcessError:
        print("⚠️  Kunde inte nå GitHub. Fortsätter ändå...")

def check_branch():
    """Varnar om man inte står på main-branchen"""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            shell=False
        ).decode().strip()
        if branch != "main":
            print(f"⚠️  Du står på branch '{branch}'. Rekommenderat är 'main'.")
            confirm = input("Vill du fortsätta ändå? (j/n): ")
            if confirm.lower() != 'j':
                sys.exit(1)
    except subprocess.CalledProcessError:
        pass

def run_tests():
    print("\n--- 🧪 KÖR TESTER ---")
    try:
        test_dir = os.path.join(BASE_DIR, "tests")
        subprocess.run(["pytest", test_dir], check=True, shell=False)
        print("✅ Alla tester godkända.")
    except FileNotFoundError:
        print("⚠️  Kunde inte hitta 'pytest'. Installera det med 'pip install pytest pytest-asyncio'.")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("\n❌ Testerna misslyckades! Åtgärda felen innan release.")
        sys.exit(1)

def run_lint():
    print("\n--- 🧹 KÖR LINT (Ruff) ---")
    try:
        # Kör ruff i BASE_DIR
        subprocess.run(["ruff", "check", "."], cwd=BASE_DIR, check=True, shell=False)
        print("✅ Linting godkänd.")
    except FileNotFoundError:
        print("⚠️  Kunde inte hitta 'ruff'. Installera det med 'pip install ruff' för att köra kodgranskning.")
    except subprocess.CalledProcessError:
        print("\n❌ Linting misslyckades! Åtgärda felen innan release.")
        sys.exit(1)

def main():
    # 1. Säkerhetskollar
    check_branch()
    run_tests()
    run_lint()
    check_for_updates()

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

    print(f"\n✨ KLART! Version {new_ver} är publicerad.")
    print("Kom ihåg att skapa en Release inne på GitHub också om du vill ha release notes!")

if __name__ == "__main__":
    main()
