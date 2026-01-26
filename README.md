# 🔋 Battery Optimizer Light (Home Assistant Integration)

**Battery Optimizer Light** är en hybrid-lösning som kopplar din Home Assistant till en smart molntjänst för Sonnen-batterier.

Den kombinerar **Moln-intelligens** (för prisoptimering och statistik) med **Lokal styrka** (för blixtsnabb effektvakt via Automationer).

---

## ✨ Funktioner

* **📈 Prisoptimering (Arbitrage):** Laddar billigt, säljer dyrt baserat på spotpris och prognos.
* **🛡️ Effektvakt (Peak Shaving):** Övervakar husets förbrukning i realtid via dina lokala sensorer. Kapar toppar direkt via automationer och rapporterar statistiken till molnet.
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
* **Nätsensor (Grid):** Mäter husets totala in/utmatning i Watt (t.ex. `sensor.beraknad_nateffekt` eller `sensor.power_meter_active_power`).
* **Batterieffekt:** Mäter vad batteriet gör just nu i Watt (t.ex. `sensor.sonnen_battery_power`).

```yaml
template:
  - sensor:
      - name: "Beräknad Näteffekt"
        unique_id: calculated_grid_power
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: >
          {% set cons = states('sensor.sonnen_consumption_w') | float(0) %}
          {% set prod = states('sensor.sonnen_production_w') | float(0) %}
          {% set batt = states('sensor.sonnen_battery_power_w') | float(0) %}
          {{ (cons - prod - batt) | int }}

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
    * **Battery Power Sensor:** Välj sensorn som mäter batteriets effekt (W).

---

## 🤖 Automationer (YAML)

Kopiera dessa automationer till din `automations.yaml`. 

*Dessa automationer ger dig full kontroll lokalt, samtidigt som de rapporterar statistik till molnet.*

### 1. Huvudstyrenhet (Utför Beslut)
*Lyssnar på molnet var 5:e minut och styr batteriet. Om molnet säger "IDLE" parkeras batteriet (0W).*

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
        sequence:
          - data:
              power: 0
            action: script.sonnen_force_charge
      - conditions:
          - condition: template
            value_template: "{{ current_action == 'IDLE' }}"
        sequence:
          - action: script.sonnen_set_auto_mode
    default:
      - action: script.sonnen_set_auto_mode
mode: single