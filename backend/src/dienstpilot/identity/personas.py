"""Demo personas from UI_SPEC §1. Roles follow PROCESS §1."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """A demo login: a physician by their staff display name, or a non-clinical user."""

    key: str
    display_name: str
    role: str  # staff | staff_plus | planner | oversight | admin
    is_physician: bool


PERSONAS: list[Persona] = [
    Persona("kaya", "Dr. Aylin Kaya", "staff", True),
    Persona("mehta", "Dr. Rohan Mehta", "staff", True),
    Persona("weber", "Dr. Jonas Weber", "staff", True),
    Persona("alvarez", "Dr. Sofía Alvarez", "staff", True),
    Persona("nowak", "Dr. Marek Nowak", "staff", True),
    Persona("lorenz", "Dr. Lea Lorenz", "staff_plus", True),
    Persona("schulz", "Dr. Hannah Schulz", "staff_plus", True),
    Persona("brandt", "Dr. Thomas Brandt", "planner", True),
    Persona("hoffmann", "Prof. Dr. Claudia Hoffmann", "planner", True),
    Persona("vogel", "Katrin Vogel", "oversight", False),
    Persona("it-admin", "IT-Administration (Demo)", "admin", False),
]
