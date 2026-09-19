"""
El ritmo del turno de noche: cuánto trabaja y cuánto descansa.

UNA PAUSA FIJA NO SIRVE. Quince segundos después de una descripción que tardó cuatro minutos
al tope del procesador no es un descanso, es una pestañeada. Y quince segundos después de una
que tardó veinte es tiempo perdido. El descanso tiene que ser proporcional al esfuerzo, como
en cualquier trabajo.

CÓMO SE MIDE EL CALOR SIN TERMÓMETRO. KUSTOS corre dentro de un contenedor y desde ahí no se
pueden leer los sensores de Windows. Pero no hace falta: cuando un procesador se acalora se
frena solo —se llama limitación térmica— y eso sí se nota desde adentro, porque las mismas
descripciones empiezan a tardar más. Aquí se guarda cuánto tardaron las primeras, que son las
de la máquina fría, y se compara con las de ahora. Si el turno se vuelve notoriamente más
lento haciendo el mismo trabajo, la conclusión razonable es que el equipo está caliente, y
entonces se alarga el descanso en lugar de seguir apretando.

TRES DESCANSOS DISTINTOS.
  El corto, después de cada descripción, proporcional a lo que acaba de costar.
  El largo, cada tantas descripciones, para que la temperatura baje de verdad y no solo se
  estabilice alta.
  Y el refuerzo, que se suma a los dos anteriores cuando se detecta la limitación térmica.

Nada de esto acelera el turno; al contrario. Pero un procesador que se frena solo termina
rindiendo menos que uno al que se le dio aire, y una máquina de oficina que se cocina ocho
horas cada noche dura menos. El turno no tiene afán: lo que se describa esta noche se revisa
mañana de todos modos.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from statistics import median

# Descanso corto: una fracción de lo que acaba de costar la descripción.
PROPORCION = float(os.getenv("NOCTURNO_PROPORCION", "0.35"))
PAUSA_MINIMA = int(os.getenv("NOCTURNO_PAUSA", "15"))
PAUSA_MAXIMA = int(os.getenv("NOCTURNO_PAUSA_MAXIMA", "180"))

# Descanso largo: cada cuántas descripciones y de cuánto.
CADA = int(os.getenv("NOCTURNO_CADA", "8"))
DESCANSO_LARGO = int(os.getenv("NOCTURNO_DESCANSO_LARGO", "300"))

# A partir de qué tanto más lento se concluye que el equipo está caliente, y cuánto se
# multiplica el descanso cuando pasa.
UMBRAL_CALOR = float(os.getenv("NOCTURNO_UMBRAL_CALOR", "1.4"))
REFUERZO = float(os.getenv("NOCTURNO_REFUERZO", "2.0"))

# Cuántas descripciones se toman como referencia de máquina fría.
_EN_FRIO = 3


@dataclass
class Ritmo:
    """Lleva la cuenta de cuánto costó cada descripción y decide cuánto se descansa."""
    duraciones: list[float] = field(default_factory=list)
    descanso_total: float = 0.0
    veces_con_calor: int = 0

    @property
    def referencia(self) -> float:
        """Cuánto tardaba con la máquina fría. Es la vara contra la que se compara."""
        if len(self.duraciones) < _EN_FRIO:
            return 0.0
        return median(self.duraciones[:_EN_FRIO])

    @property
    def ritmo_actual(self) -> float:
        """Cuánto está tardando ahora, promediando las tres últimas."""
        if not self.duraciones:
            return 0.0
        return median(self.duraciones[-_EN_FRIO:])

    @property
    def hay_calor(self) -> bool:
        """
        Si el equipo parece estar frenándose por temperatura.

        Hace falta un mínimo de descripciones antes de concluir nada: las dos primeras
        siempre son atípicas porque el modelo se está cargando en memoria.
        """
        base = self.referencia
        if not base or len(self.duraciones) < _EN_FRIO + 2:
            return False
        return self.ritmo_actual > base * UMBRAL_CALOR

    @property
    def cuanto_mas_lento(self) -> float:
        base = self.referencia
        return (self.ritmo_actual / base) if base else 1.0

    def anotar(self, duracion: float) -> None:
        self.duraciones.append(max(0.0, float(duracion)))

    def descanso(self) -> tuple[float, str]:
        """
        Cuánto hay que descansar ahora y por qué.

        El porqué se devuelve junto con el número porque queda escrito en la bitácora: en la
        mañana se tiene que poder saber si el turno fue lento porque el modelo es lento o
        porque el equipo se estaba cocinando. Son dos problemas distintos.
        """
        if not self.duraciones:
            return 0.0, ""
        ultima = self.duraciones[-1]
        segundos = min(PAUSA_MAXIMA, max(PAUSA_MINIMA, ultima * PROPORCION))
        motivo = f"descanso de {segundos:.0f}s tras {ultima:.0f}s de trabajo"

        if self.hay_calor:
            self.veces_con_calor += 1
            segundos = min(PAUSA_MAXIMA * REFUERZO, segundos * REFUERZO)
            motivo = (f"descanso REFORZADO de {segundos:.0f}s: el turno va "
                      f"{self.cuanto_mas_lento:.1f} veces más lento que en frío, así que el "
                      "equipo parece estar caliente")

        if CADA and len(self.duraciones) % CADA == 0:
            segundos += DESCANSO_LARGO
            motivo += f" · más el descanso largo de {DESCANSO_LARGO}s, que toca cada {CADA}"

        self.descanso_total += segundos
        return segundos, motivo

    def parte(self) -> dict:
        """El resumen del ritmo, para la bitácora y para la mañana siguiente."""
        return {
            "descripciones": len(self.duraciones),
            "segundos_por_descripcion": round(self.ritmo_actual, 1),
            "en_frio": round(self.referencia, 1),
            "cuanto_mas_lento": round(self.cuanto_mas_lento, 2),
            "hubo_calor": self.veces_con_calor > 0,
            "veces_con_calor": self.veces_con_calor,
            "minutos_de_descanso": round(self.descanso_total / 60, 1),
        }


def en_palabras(parte: dict) -> str:
    """El parte del ritmo dicho de una manera que sirva para decidir algo."""
    if not parte["descripciones"]:
        return "No alcanzó a describir nada."
    partes = [f"{parte['descripciones']} descripción(es) a "
              f"{parte['segundos_por_descripcion']:.0f} segundos cada una"]
    if parte["en_frio"]:
        partes.append(f"en frío tardaba {parte['en_frio']:.0f}")
    partes.append(f"descansó {parte['minutos_de_descanso']:.0f} minutos")
    texto = "; ".join(partes) + "."
    if parte["hubo_calor"]:
        texto += (f" El equipo se frenó por temperatura {parte['veces_con_calor']} vez(ces) y "
                  "el turno alargó los descansos solo. Si se repite todas las noches, use un "
                  "modelo más pequeño o limpie las rejillas de ventilación.")
    return texto
