# 🔋 Battery Optimizer Light (Home Assistant Integration)

![Validate and Test](https://github.com/awestin67/battery-optimizer-light-ha/actions/workflows/run_tests.yml/badge.svg)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**Battery Optimizer Light** är en hybrid-lösning som kopplar din Home Assistant till en smart molntjänst för Sonnen-batterier.

Den kombinerar **Moln-intelligens** (för prisoptimering och statistik) med **Lokal styrka** (för blixtsnabb effektvakt via Automationer).

---

## ✨ Funktioner

* **📈 Prisoptimering (Arbitrage):** Laddar billigt, säljer dyrt baserat på spotpris och prognos.
* **🛡️ Smart Effektvakt (Peak Shaving):** Övervakar husets nettolast i realtid.
    * **Molnstyrning:** Effektvakten kan aktiveras/inaktiveras dynamiskt från molnet. Status visas via `sensor.optimizer_light_peakguard_status`.
    * **Hysteres:** Startar urladdning direkt vid topp, men slutar först när lasten sjunkit rejält (1000W) under gränsen för att undvika "fladder".
    * **Rapportering:** Skickar statistik till molnet (max 1 gång per topp).
* **⛄ Vinterbuffert:** Sparar en valfri % av batteriet som *aldrig* säljs, utan sparas för nödlägen.
* **📊 Statistik:** Se "Top 3" effekttoppar och besparingshistorik i en snygg Web Dashboard.

---

## 🛠️ Förberedelser (Krav)

### 1. Skript
För att systemet ska kunna styra ditt batteri (t.ex. ett Sonnen) måste du ha dessa skript i Home Assistant:
* `script.sonnen_set_auto_mode` (Motsvarar self-consumption)
* `script.sonnen_force_charge` (Måste acceptera `power` som variabel)
* `script.sonnen_force_discharge` (Måste acceptera `power` som variabel)

### 2. Sensorer
Du behöver veta namnet på följande sensorer i din Home Assistant:
* **Batteri SoC:** (t.ex. `sensor.sonnen_usoc`)
* **Batteri Effekt:** (t.ex. `sensor.sonnen_battery_power_w`) – Används i automationen.
* **Grid Sensor:** Mäter husets totala in/utmatning (Import/Export).

**Virtuell Last:** Integrationen räknar automatiskt ut husets nettolast (`Grid + Batteri`).
*Om du saknar en Grid-sensor kan du skapa en egen template-sensor (`Konsumtion - Produktion`) och välja den under "Virtuell Last Sensor" i inställningarna.*

---

## 🚀 Installation

### Alternativ A: HACS (Rekommenderas)
1. Gå till **HACS** -> **Integrationer** -> **Anpassade arkiv** (Custom repositories).
2. Lägg till URL: `https://github.com/awestin67/battery-optimizer-light-ha`
3. Kategori: **Integration**.
4. Installera och starta om Home Assistant.

### Alternativ B: Manuell installation
1. Ladda ner mappen `battery_optimizer_light`.
2. Kopiera den till `/config/custom_components/`.
3. Starta om Home Assistant.

---

## ⚙️ Konfiguration

1. Gå till **Inställningar** -> **Enheter & Tjänster**.
2. Klicka **+ Lägg till integration** -> Sök efter **Battery Optimizer Light**.
3. Fyll i uppgifterna:
    * **API URL:** (Låt stå kvar standardvärdet).
    * **API Key:** Din nyckel från Web Dashboarden.
    * **SoC Sensor:** Välj din batterisensor (%).
    * **Grid Sensor:** Välj sensorn som mäter husets huvudsäkring/nät (W).
    * **Invertera Grid Sensor:** Kryssa i om din mätare visar positivt värde vid export (försäljning).
    * **Battery Power Sensor:** Välj sensorn som mäter batteriets effekt (W).
    * **Virtual Load Sensor:** (Valfritt) Lämna tomt för automatisk beräkning.

---

## 🤖 Automationer (YAML)

Kopiera dessa automationer till din `automations.yaml`. **OBS:** Kontrollera att entity_id för dina sensorer (t.ex. `sensor.sonnen_battery_power_w`) stämmer överens med din installation.

*Dessa automationer ger dig full kontroll lokalt, samtidigt som de rapporterar statistik till molnet.*

### 1. Huvudstyrenhet (Utför Beslut)
*Lyssnar på molnet var 5:e minut och styr batteriet. Om molnet säger "HOLD" parkeras batteriet (0W).*

```yaml
alias: 🔋 Battery Optimizer Light - Utför Beslut (Sonnen API)
description: Styr Sonnen-batteriet via REST commands baserat på optimeraren.
triggers:
  - trigger: state
    entity_id: sensor.optimizer_light_action
  - trigger: time_pattern
    minutes: /5
conditions:
  - condition: not
    conditions:
      - condition: state
        entity_id: sensor.optimizer_light_action
        state:
          - unknown
          - unavailable
actions:
  - variables:
      current_action: "{{ states('sensor.optimizer_light_action') }}"
      target_power: "{{ (states('sensor.optimizer_light_power') | float(0) * 1000) | int }}"
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ current_action == 'CHARGE' }}"
        sequence:
          - data:
              power: "{{ target_power }}"
            action: script.sonnen_force_charge
      - conditions:
          - condition: template
            value_template: "{{ current_action == 'DISCHARGE' }}"
        sequence:
          - data:
              power: "{{ target_power }}"
            action: script.sonnen_force_discharge
      - conditions:
          - condition: template
            value_template: "{{ current_action == 'HOLD' }}"
          - condition: template
            value_template: >-
              {{ states('sensor.sonnen_battery_power_w') | float(0) |
              abs > 100 }}
        sequence:
          - action: script.sonnen_force_charge
            data:
              power: 0
      - conditions:
          - condition: template
            value_template: "{{ current_action == 'IDLE' }}"
        sequence:
          - action: script.sonnen_set_auto_mode
    default:
      - action: script.sonnen_set_auto_mode
mode: single
```