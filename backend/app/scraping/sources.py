"""
Registry of all active scraping sources.

Add a new BCBNormativosSource entry here whenever you want to track
a new combination of (querytext, tipoDocumento).
The CLI and the daily cron job iterate over ALL_SOURCES.
"""
from __future__ import annotations

from app.scraping.bcb_normativos import BCBNormativosSource

ALL_SOURCES: list[BCBNormativosSource] = [
    # CCS Comunicados  (the first URL you gave us)
    BCBNormativosSource(
        source_name="bcb_comunicados_ccs",
        querytext="CCS",
        tipo_documento="Comunicado",
    ),
    # Add more sources here, for example:
    # BCBNormativosSource(
    #     source_name="bcb_resolucoes_bcb",
    #     querytext="*",
    #     tipo_documento="Resolução BCB",
    # ),
]
