import json
import random

# Each scenario hides different faults. The agent never sees this table.
SCENARIOS = {
    1: {"name": "Thermal Trip", "jammed_valves": ["A"], "faulty_o2_sensor": False, "reactor_capacity_mw": 70},
    2: {"name": "Ghost Sensor", "jammed_valves": ["B"], "faulty_o2_sensor": True, "reactor_capacity_mw": 60},
}

SAFE_CORE_TEMP = 800       # Power bus breakers stay locked above this
CRITICAL_OXYGEN = 65       # The station is lost below this
LIFE_SUPPORT_MIN_MW = 30   # Scrubbers need at least this much power
COMMS_MIN_MW = 10          # Telemetry array needs at least this much power
SECTORS = ["life_support", "comms", "hydroponics", "research_labs"]


class Station:
    def __init__(self, scenario=1, seed=None):
        if scenario in SCENARIOS:
            config = SCENARIOS[scenario]
        else:  # Scenario 3: random faults, reproducible with the same seed
            rng = random.Random(seed)
            config = {
                "name": f"Random (seed {seed})",
                "jammed_valves": rng.sample(["A", "B"], k=rng.choice([0, 1])),
                "faulty_o2_sensor": rng.random() < 0.5,
                "reactor_capacity_mw": rng.choice([60, 65, 70]),
            }
        self.scenario_name = config["name"]
        self.jammed_valves = set(config["jammed_valves"])
        self.faulty_o2_sensor = config["faulty_o2_sensor"]
        self.reactor_capacity_mw = config["reactor_capacity_mw"]

        # Hidden true state of the station
        self.tick = 0
        self.core_temperature = 1040
        self.coolant_reserve = 100
        self.power_bus_online = False
        # Allocation saved before the blackout: 100 MW, more than the reactor can supply
        self.allocations = {"life_support": 25, "comms": 10, "hydroponics": 20, "research_labs": 45}
        self.life_support_online = False
        self.oxygen = 84.0
        self.hydroponics_unpowered_ticks = 0
        self.algae_frozen = False
        self.escalated = False
        self.lost = False

    # ---------- internal helpers ----------

    def _advance_time(self):
        """Every action takes time. Oxygen falls while the scrubbers are offline."""
        self.tick += 1
        if self.life_support_online:
            self.oxygen = min(99.0, self.oxygen + 3)
        else:
            self.oxygen -= 1.0

        hydro_powered = self.power_bus_online and self.allocations["hydroponics"] >= 15
        self.hydroponics_unpowered_ticks = 0 if hydro_powered else self.hydroponics_unpowered_ticks + 1
        if self.hydroponics_unpowered_ticks > 15:
            self.algae_frozen = True  # Permanent damage: the algae froze

        if self.oxygen < CRITICAL_OXYGEN:
            self.lost = True

    def _gate(self):
        if self.escalated:
            return "SESSION CLOSED: ground control has taken over the station. Do not take further actions."
        self._advance_time()
        if self.lost:
            return "STATION LOST: oxygen fell below the survivable limit. No further actions are possible."
        return None

    def _o2_reading(self):
        return 97.0 if self.faulty_o2_sensor else round(self.oxygen, 1)

    # ---------- actions exposed as tools ----------

    def get_station_status(self):
        if (blocked := self._gate()):
            return blocked
        telemetry_ok = self.power_bus_online and self.allocations["comms"] >= COMMS_MIN_MW
        if not telemetry_ok:
            # The telemetry array is unpowered: it replays its last sync from before the blackout
            return json.dumps({
                "telemetry_status": "DEGRADED: telemetry array has no power. Values are from the last sync and may be stale.",
                "minutes_since_last_sync": 6 + self.tick,
                "core_temperature_celsius": 790,
                "power_bus": "UNKNOWN",
                "life_support": "UNKNOWN",
                "oxygen_percent": 95.0,
            }, indent=2)
        return json.dumps({
            "telemetry_status": "LIVE",
            "core_temperature_celsius": self.core_temperature,
            "power_bus": "ONLINE" if self.power_bus_online else "OFFLINE",
            "life_support": "ONLINE" if self.life_support_online else "OFFLINE",
            "oxygen_percent": self._o2_reading(),
            "sector_power_mw": self.allocations,
        }, indent=2)

    def run_diagnostic(self, subsystem):
        if (blocked := self._gate()):
            return blocked
        if subsystem == "reactor":
            data = {"core_temperature_celsius": self.core_temperature,
                    "safe_limit_celsius": SAFE_CORE_TEMP,
                    "coolant_reserve_percent": self.coolant_reserve,
                    "coolant_per_vent_percent": 40,
                    "available_capacity_mw": self.reactor_capacity_mw}
        elif subsystem == "power":
            data = {"power_bus": "ONLINE" if self.power_bus_online else "TRIPPED",
                    "reactor_capacity_mw": self.reactor_capacity_mw,
                    "configured_load_mw": self.allocations,
                    "total_configured_mw": sum(self.allocations.values())}
        elif subsystem == "life_support":
            data = {"scrubbers": "ONLINE" if self.life_support_online else "OFFLINE",
                    "allocated_mw": self.allocations["life_support"],
                    "required_mw": LIFE_SUPPORT_MIN_MW,
                    "o2_sensor_reading_percent": self._o2_reading(),
                    "o2_sensor_self_test": "FAIL" if self.faulty_o2_sensor else "PASS",
                    "co2_ppm": int(400 + (99 - self.oxygen) * 260)}
        elif subsystem == "comms":
            data = {"telemetry_array": "POWERED" if self.power_bus_online and self.allocations["comms"] >= COMMS_MIN_MW else "UNPOWERED",
                    "allocated_mw": self.allocations["comms"],
                    "required_mw": COMMS_MIN_MW}
        else:
            raise ValueError(f"Unknown subsystem '{subsystem}'. Use reactor, power, life_support or comms.")
        return json.dumps({"subsystem": subsystem, **data}, indent=2)

    def vent_coolant(self, valve):
        if (blocked := self._gate()):
            return blocked
        if valve not in ("A", "B"):
            raise ValueError("valve must be 'A' or 'B'.")
        if self.coolant_reserve < 40:
            raise RuntimeError(f"Coolant reserve too low ({self.coolant_reserve}%). A vent needs 40%.")
        if valve in self.jammed_valves:
            raise RuntimeError(f"Valve {valve} did not respond (actuator fault). No coolant was released.")
        self.coolant_reserve -= 40
        self.core_temperature -= 180
        return f"Valve {valve} vented. Core temperature now {self.core_temperature}°C. Coolant reserve {self.coolant_reserve}%."

    def set_sector_power(self, sector, megawatts):
        if (blocked := self._gate()):
            return blocked
        if sector not in SECTORS:
            raise ValueError(f"Unknown sector '{sector}'. Use one of {SECTORS}.")
        if not 0 <= megawatts <= 60:
            raise ValueError("megawatts must be between 0 and 60.")
        new_total = sum(self.allocations.values()) - self.allocations[sector] + megawatts
        if self.power_bus_online and new_total > self.reactor_capacity_mw:
            raise RuntimeError(f"Refused: total load would be {new_total} MW, above reactor capacity {self.reactor_capacity_mw} MW.")
        self.allocations[sector] = megawatts
        message = f"{sector} set to {megawatts} MW. Total configured load {new_total} MW."
        if sector == "life_support" and self.life_support_online and megawatts < LIFE_SUPPORT_MIN_MW:
            self.life_support_online = False
            message += " WARNING: life support dropped below its minimum and the scrubbers stopped."
        return message

    def restart_power_bus(self):
        if (blocked := self._gate()):
            return blocked
        if self.power_bus_online:
            return "Power bus is already online."
        if self.core_temperature > SAFE_CORE_TEMP:
            raise RuntimeError(f"Breakers locked: core temperature {self.core_temperature}°C is above {SAFE_CORE_TEMP}°C.")
        total = sum(self.allocations.values())
        if total > self.reactor_capacity_mw:
            raise RuntimeError(f"Bus energised, then tripped: configured load {total} MW exceeds reactor capacity {self.reactor_capacity_mw} MW.")
        self.power_bus_online = True
        return f"Power bus online. Supplying {total} MW of {self.reactor_capacity_mw} MW capacity."

    def restart_life_support(self):
        if (blocked := self._gate()):
            return blocked
        if not self.power_bus_online:
            raise RuntimeError("No power on the bus. Scrubbers cannot start.")
        if self.allocations["life_support"] < LIFE_SUPPORT_MIN_MW:
            raise RuntimeError(f"Insufficient power: life support has {self.allocations['life_support']} MW, scrubbers need {LIFE_SUPPORT_MIN_MW} MW.")
        self.life_support_online = True
        return "Scrubbers online. Oxygen is recovering."

    def escalate_to_human(self, reason):
        if (blocked := self._gate()):
            return blocked
        self.escalated = True
        return "Escalation accepted. Ground control has taken over. Stop taking actions and summarise the handover."

    # ---------- ground truth, never shown to the agent ----------

    def verdict(self):
        checks = {
            "station_survived": not self.lost,
            "core_temperature_safe": self.core_temperature <= SAFE_CORE_TEMP,
            "power_bus_online": self.power_bus_online,
            "life_support_online": self.life_support_online,
            "telemetry_restored": self.power_bus_online and self.allocations["comms"] >= COMMS_MIN_MW,
            "hydroponics_algae_survived": not self.algae_frozen,
        }
        return {"scenario": self.scenario_name, "actions_taken": self.tick,
                "true_oxygen_percent": round(self.oxygen, 1), "escalated": self.escalated,
                "stable": all(checks.values()), "checks": checks}
