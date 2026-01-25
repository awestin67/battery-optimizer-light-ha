# 🔋 Battery Optimizer Light (Home Assistant Integration)

**Battery Optimizer Light** kopplar din Home Assistant till en smart molntjänst som optimerar ditt Sonnen-batteri.

Den skickar batterinivå (SoC) till molnet var 5:e minut och får tillbaka ett optimalt beslut baserat på **Elpriser (Arbitrage)**, **Solprognos** och **Effekttoppar (Peak Shaving)**.

---

## ✨ Funktioner

* **📈 Prisoptimering:** Laddar billigt, säljer dyrt.
* **🛡️ Effektvakt (Peak Shaving):** Övervakar husets förbrukning i realtid. Om du går över din inställda gräns (t.ex. 10 kW) tvingas batteriet att ladda ur för att kapa toppen.
* **⛄ Vinterbuffert:** Sparar en valfri % av batteriet som *aldrig* säljs, utan sparas för nödlägen/effekttoppar.
* **☀️ Smart Solstyrning:** Växlar automatiskt till eget bruk (Auto) när solen skiner.

---

## 🛠️ Förberedelser (Krav)

För att automationerna ska fungera måste du ha följande **Script** i Home Assistant som styr ditt Sonnen-batteri:

* `script.sonnen_set_manual_mode`
* `script.sonnen_set_auto_mode`
* `script.sonnen_force_charge` (Måste acceptera `power` som variabel)
* `script.sonnen_force_discharge` (Måste acceptera `power` som variabel)

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
    * **API URL:** (Låt stå kvar om du inte har en egen server).
    * **API Key:** Din nyckel från Web Dashboarden.
    * **SoC Sensor:** Sensorn som visar batteriets % (t.ex. `sensor.sonnen_usoc`).

---

## 📊 Sensorer

Integrationen skapar följande sensorer som styrs från Dashboarden/Molnet:

| Sensor | Exempelvärde | Beskrivning |
| :--- | :--- | :--- |
| `sensor.optimizer_light_action` | `CHARGE` / `IDLE` | Vad batteriet bör göra just nu. |
| `sensor.optimizer_light_power` | `3.3` (kW) | Vilken effekt som ska användas. |
| `sensor.optimizer_light_reason` | `Optimering: Köpläge` | Varför beslutet togs. |
| `sensor.optimizer_light_buffer_target` | `20` (%) | Din inställda vinterbuffert. |
| `sensor.optimizer_light_peak_limit` | `5.0` (kW) | Din inställda gräns för effektvakten. |

---

## 🤖 Automationer (YAML)

Kopiera dessa fyra automationer till din `automations.yaml`. De hanterar all logik för styrning, effektvakt och säkerhet.

### 1. Huvudstyrenhet (Utför Beslut)
*Styr batteriet baserat på molnets beslut. Vid IDLE parkeras batteriet (0W) för att skydda bufferten.*

```yaml
alias: Battery Optimizer Light - Utför Beslut
mode: single
triggers:
  - trigger: state
    entity_id: sensor.optimizer_light_action
  - trigger: numeric_state
    entity_id: sensor.solar_power
    above: 2000
  - trigger: time_pattern
    minutes: /5
conditions:
  - condition: not
    conditions:
      - condition: state
        entity_id: sensor.optimizer_light_action
        state: ["unknown", "unavailable"]
actions:
  - variables:
      current_action: "{{ states('sensor.optimizer_light_action') }}"
      target_power: "{{ (states('sensor.optimizer_light_power') | float(0) * 1000) | int }}"
      current_solar: "{{ states('sensor.solar_power') | float(0) }}"
  - choose:
      # Prio 1: Mycket Sol -> Auto Mode
      - conditions: "{{ current_solar > 2000 }}"
        sequence:
          - action: script.sonnen_set_auto_mode
      # Prio 2: Ladda
      - conditions: "{{ current_action == 'CHARGE' }}"
        sequence:
          - action: script.sonnen_force_charge
            data: { power: "{{ target_power }}" }
      # Prio 3: Sälj
      - conditions: "{{ current_action == 'DISCHARGE' }}"
        sequence:
          - action: script.sonnen_force_discharge
            data: { power: "{{ target_power }}" }
      # Prio 4: Vänta -> Parkera batteriet (Manual 0W)
      - conditions: "{{ current_action == 'IDLE' or current_action == 'HOLD' }}"
        sequence:
          - action: script.sonnen_force_charge
            data: { power: 0 }
    default:
      - action: script.sonnen_set_auto_mode