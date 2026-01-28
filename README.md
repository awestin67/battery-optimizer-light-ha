# 🔋 Battery Optimizer Light (Home Assistant Integration)

**Battery Optimizer Light** är en hybrid-lösning som kopplar din Home Assistant till en smart molntjänst för Sonnen-batterier.

Den kombinerar **Moln-intelligens** (för prisoptimering och statistik) med **Lokal styrka** (för blixtsnabb effektvakt via Automationer).

---

## ✨ Funktioner

* **📈 Prisoptimering (Arbitrage):** Laddar billigt, säljer dyrt baserat på spotpris och prognos.
* **🛡️ Smart Effektvakt (Peak Shaving):** * Övervakar husets nettolast i realtid.
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
* **Virtuell Nätsensor:** Mäter husets totala in/utmatning i Watt exklusive batteriet.

```yaml
template:
  - sensor:
      - name: "Husets Netto Last Virtuell"
        unique_id: house_net_load_virtual
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: >
          {% set cons = states('sensor.sonnen_consumption_w') | float(0) %}
          {% set prod = states('sensor.sonnen_production_w') | float(0) %}          
          {{ (cons - prod) | int }}
```
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
### 2. Effektvakt (Peak Shaving)
Denna automation väcker bara integrationen när lasten ändras. All logik (Hysteres, Rapportering, Styrning) sker nu automatiskt i Python-koden.
```yaml
alias: ✅ Effektvakt - Trigger
description: >-
  Trigger för batterioptimeringens effektvakt. All logik hanteras av
  integrationen (PeakGuard).
mode: restart
triggers:
  - trigger: state
    entity_id: sensor.husets_netto_last_virtuell
  - trigger: time_pattern
    seconds: /30
actions:
  # Anropar integrationens smarta tjänst
  - action: battery_optimizer_light.run_peak_guard
    data:
      # Peka ut din virtuella sensor
      virtual_load_entity: sensor.husets_netto_last_virtuell
      # Peka ut gränsvärdet (Sensor från molnet ELLER Input Number)
      limit_entity: sensor.optimizer_light_peak_limit
```