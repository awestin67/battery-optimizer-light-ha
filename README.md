Här är en instruktion du kan ge till dina användare för att installera och använda integrationen i Home Assistant.

---

# 🔋 Kom igång med Battery Optimizer Light i Home Assistant

Denna integration kopplar din Home Assistant till optimeringsmotorn. Den skickar din batterinivå (SoC) till molnet var 5:e minut och får tillbaka ett optimalt beslut (Ladda, Ladda ur eller Vila) baserat på elpriser och solprognos.

## Steg 1: Installation (Custom Component)

Eftersom integrationen inte finns i HACS än, måste den installeras manuellt:

1. Använd en filhanterare (t.ex. **File Editor** eller **Samba Share**) i Home Assistant.
2. Gå till mappen `/config/custom_components/`.
3. Skapa en ny mapp som heter: `battery_optimizer_light`
4. Ladda upp följande filer till den mappen:
* `__init__.py`
* `manifest.json`
* `sensor.py`
* `config_flow.py`
* `const.py`
* `coordinator.py`


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
alias: "Styr Batteri via Optimizer"
description: "Ändrar batteriets läge baserat på Battery Optimizer Light"
trigger:
  - platform: state
    entity_id: sensor.optimizer_light_action
action:
  - choose:
      # --- FALL 1: LADDA (KÖP BILLIGT) ---
      - conditions:
          - condition: state
            entity_id: sensor.optimizer_light_action
            state: "CHARGE"
        sequence:
          # Exempel: Ställ in batteriet på att ladda från nätet
          - service: select.select_option
            target:
              entity_id: select.mitt_batteri_mode
            data:
              option: "Force Charge"
          # Ställ in effekten (Hämta värdet från power-sensorn)
          - service: number.set_value
            target:
              entity_id: number.mitt_batteri_ladd_effekt
            data:
              value: "{{ states('sensor.optimizer_light_power') }}"

      # --- FALL 2: LADDA UR (SÄLJ DYRT) ---
      - conditions:
          - condition: state
            entity_id: sensor.optimizer_light_action
            state: "DISCHARGE"
        sequence:
          # Exempel: Ställ in batteriet på att ladda ur max
          - service: select.select_option
            target:
              entity_id: select.mitt_batteri_mode
            data:
              option: "Force Discharge" # Eller "Self Consumption" beroende på märke
          - service: number.set_value
            target:
              entity_id: number.mitt_batteri_urladd_effekt
            data:
              value: "{{ states('sensor.optimizer_light_power') }}"

      # --- FALL 3: VILA (IDLE/HOLD) ---
      - conditions:
          - condition: or
            conditions:
              - condition: state
                entity_id: sensor.optimizer_light_action
                state: "IDLE"
              - condition: state
                entity_id: sensor.optimizer_light_action
                state: "HOLD"
        sequence:
          # Stoppa batteriet eller sätt i "Self Consumption" utan nätladdning
          - service: select.select_option
            target:
              entity_id: select.mitt_batteri_mode
            data:
              option: "Stop" # Eller "Self Consumption"

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