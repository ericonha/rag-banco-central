"""
Registry of all active scraping sources.

Add a new BCBNormativosSource entry here whenever you want to track
a new combination of (querytext, tipoDocumento).
The CLI and the daily cron job iterate over ALL_SOURCES.
"""
from __future__ import annotations

from app.scraping.bcb_normativos import BCBNormativosSource

ALL_SOURCES: list[BCBNormativosSource] = [
    # CCS Comunicados
    BCBNormativosSource(
        source_name="bcb_comunicados_ccs",
        querytext="CCS",
        tipo_documento="Comunicado",
    ),
    # BCB Resolutions (main regulations)
    BCBNormativosSource(
        source_name="bcb_resolucoes",
        querytext="*",
        tipo_documento="Resolução BCB",
    ),
    # Central Bank Circulars
    BCBNormativosSource(
        source_name="bcb_circulares",
        querytext="*",
        tipo_documento="Circular BCB",
    ),
    # Normative Instructions
    BCBNormativosSource(
        source_name="bcb_instrucoes_normativas",
        querytext="*",
        tipo_documento="Instrução Normativa",
    ),
]
