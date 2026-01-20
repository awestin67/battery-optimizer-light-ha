Här är en instruktion du kan ge till dina användare för att installera och använda integrationen i Home Assistant.

---

# 🔋 Kom igång med Battery Optimizer Light i Home Assistant

Denna integration kopplar din Home Assistant till optimeringsmotorn. Den skickar din batterinivå (SoC) till molnet var 5:e minut och får tillbaka ett optimalt beslut (Ladda, Ladda ur eller Vila) baserat på elpriser och solprognos.

## Steg 1: Installera via HACS (Rekommenderas)
  1. Gå till **HACS** -> **Integrationer** -> **Anpassade arkiv** (Custom repositories).
  2. Lägg till denna URL: `https://github.com/awestin67/battery-optimizer-light-ha`
  3. Välj kategori **Integration** och klicka Lägg till.
  4. Installera "Battery Optimizer Light" och starta om Home Assistant.
  5. **Starta om Home Assistant** (Inställningar -> System -> Starta om).

## Steg 2: Konfiguration

När Home Assistant har startat om:

1. Gå till **Inställningar** -> **Enheter & Tjänster**.
2. Klicka på **+ Lägg till integration** (nere till höger).
3. Sök efter **Battery Optimizer Light**.
4. Fyll i uppgifterna:
* **API URL:** Låt stå kvar (standardvärdet är oftast rätt).
* **API Key:** Klistra in din nyckel från Dashboarden (under Inställningar).
* **SoC Sensor:** Välj den sensor i din Home Assistant som visar batteriets nuvarande procent (t.ex. `sensor.mitt_batteri_soc`).


5. Klicka på **Skicka**.

## Steg 3: Nya Sensorer

Integrationen skapar tre sensorer som uppdateras var 5:e minut:

| Sensor | Beslut | Beskrivning |
| --- | --- | --- |
| `sensor.optimizer_light_action` | **CHARGE** | Du bör ladda batteriet från nätet. |
|  | **DISCHARGE** | Du bör tömma batteriet (sälja eller använda i huset). |
|  | **IDLE** / **HOLD** | Gör ingenting (låt batteriet vila eller vänta på bättre priser). |
| `sensor.optimizer_light_power` | *Siffra (kW)* | Rekommenderad effekt. T.ex. `3.3` betyder ladda/ladda ur med 3,3 kW. |
| `sensor.optimizer_light_reason` | *Text* | Förklaring till beslutet (t.ex. "Optimering: Köpläge" eller "Låg volatilitet"). |

---

## Steg 4: Automation (Styra batteriet)

Integrationen ger bara *rekommendationer*. Du måste skapa en automation som faktiskt ändrar inställningarna på din växelriktare/batteri.

Här är ett exempel på hur en automation kan se ut. **OBS:** Tjänsterna (`service: ...`) beror helt på vilket märke du har på ditt batteri (Huawei, Fronius, Victron, etc.).

**Exempel på logik (YAML):**

```yaml
alias: Battery Optimizer Light - Utför Beslut (Sonnen API)
description: Styr Sonnen-batteriet via REST commands baserat på optimeraren.
triggers:
  - trigger: state
    entity_id: sensor.optimizer_light_action
  - trigger: numeric_state
    entity_id: sensor.solaredge_se15k_solar_power
    above: 2000
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
      current_solar: "{{ states('sensor.solar_production') | float(0) }}"
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ current_solar > 2000 }}"
        sequence:
          - action: script.sonnen_set_auto_mode
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
    default:
      - action: script.sonnen_set_auto_mode
mode: single

```

### Tips för visualisering

För att se status snyggt i din Dashboard kan du använda ett "Entities"-kort:

```yaml
type: entities
title: Batteri Optimering
entities:
  - entity: sensor.optimizer_light_action
    name: Beslut
  - entity: sensor.optimizer_light_power
    name: Effekt
  - entity: sensor.optimizer_light_reason
    name: Orsak
    icon: mdi:information-outline

```