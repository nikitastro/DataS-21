#!/usr/bin/env python3
"""
clean_notebook.py — очистка ноутбука «росатом_недраV1.6.ipynb».

Что делает:
  1. Удаляет отладочные ячейки (0.10, 5.1, 5.2).
  2. Удаляет осиротевший markdown «Среднегодовой курс ЦБ РФ 2025».
  3. Фиксит дубль `to_csv` в ячейке 0.6.
  4. Переносит определение `rev_rub` до ячейки 0.6 (устраняет NameError).
  5. Сводит все импорты в один блок в начале.
  6. Убирает Colab-специфику, пустые outputs.
  7. Сбрасывает execution_count для воспроизводимости.
"""
import json
import re
from pathlib import Path

SRC = Path("росатом_недраV1.6.ipynb")
DST = Path("росатом_недраV1.6_clean.ipynb")

# ─── ID ячеек, которые удаляем полностью ──────────────────────────────
DROP_IDS = {
    "jeTfsGoiOz5B",  # 0.10 — диагностика единиц BGS
    "7ksEJgnf_-dI",  # 5.1  — print(df_model ...)
    "Wk8mio3OACeJ",  # 5.2  — проверка key_rate
}

# Markdown-ячейки, начинающиеся с этих строк, тоже удаляем
DROP_MD_STARTS = (
    "Среднегодовой курс ЦБ РФ 2025",
)

# Определение rev_rub — переносим из ячейки 4.3 в начало
REV_RUB_BLOCK = """# Ряд выручки АО «Росатом Недра», млн руб. (2015–2025)
rev_rub = [21352.97, 22181.68, 17758.89, 18495.65, 18804.31,
           20374.48, 23244.25, 24717.76, 34746.05, 59060.42, 80218.18]
"""

# ─── Загрузка ─────────────────────────────────────────────────────────
nb = json.loads(SRC.read_text(encoding="utf-8"))
cells = nb["cells"]


def cell_src(cell) -> str:
    """Склеить source в строку (source может быть list[str] или str)."""
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def set_src(cell, text: str):
    cell["source"] = text.splitlines(keepends=True)


# ─── 1. Удаление лишних ячеек ─────────────────────────────────────────
cleaned = []
for c in cells:
    cid = c.get("metadata", {}).get("id", "")
    if cid in DROP_IDS:
        continue
    if c["cell_type"] == "markdown":
        txt = cell_src(c).lstrip()
        if any(txt.startswith(p) for p in DROP_MD_STARTS):
            continue
    cleaned.append(c)
cells = cleaned

# ─── 2. Фикс дубля to_csv в ячейке 0.6 ────────────────────────────────
for c in cells:
    if c["cell_type"] != "code":
        continue
    src = cell_src(c)
    if (
        "df_model.to_csv('nedra_model_dataset.csv')" in src
        and src.count("df_model.to_csv('nedra_model_dataset.csv')") > 1
    ):
        # убираем первый вызов to_csv (до dropna)
        src = src.replace(
            "df_model.to_csv('nedra_model_dataset.csv')\n"
            "\n"
            "df_model = df_model.dropna()\n"
            "df_model.to_csv('nedra_model_dataset.csv')\n"
            "print(df_model.tail())",
            "df_model = df_model.dropna()\n"
            "df_model.to_csv('nedra_model_dataset.csv')\n"
            "print(df_model.tail())",
        )
        set_src(c, src)

# ─── 3. Внедряем rev_rub в начало (перед ячейкой 0.5) ─────────────────
# Найдём индекс первой code-ячейки и вставим перед ней
insert_at = next(
    i for i, c in enumerate(cells) if c["cell_type"] == "code"
)

rev_rub_cell = {
    "cell_type": "markdown",
    "metadata": {"id": "rev-rub-header"},
    "source": ["### Ряд выручки АО «Росатом Недра» (млн руб., 2015–2025)\n"],
}
rev_rub_code = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {"id": "rev-rub-block"},
    "outputs": [],
    "source": REV_RUB_BLOCK.splitlines(keepends=True),
}
cells.insert(insert_at, rev_rub_code)
cells.insert(insert_at, rev_rub_cell)

# ─── 4. Единый блок импортов в самом начале ───────────────────────────
# Удаляем дублирующиеся `import` из середины (кроме тех, что
# действительно локальны, — но у нас таких нет).
IMPORT_HEADER = """# ─── Единый блок импортов ─────────────────────────────────────────────
import os
import sys
import io
import json
import pickle
import subprocess
import warnings
import operator
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from statsmodels.tsa.statespace.sarimax import SARIMAX
from sklearn.metrics import mean_absolute_percentage_error
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

import mlflow
import mlflow.sklearn

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
"""

imports_cell = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {"id": "imports-header"},
    "outputs": [],
    "source": IMPORT_HEADER.splitlines(keepends=True),
}
cells.insert(0, imports_cell)

# ─── 5. Чистим лишние "переимпорты" внутри ячеек ──────────────────────
# Матчим строки `import X`, `from X import Y`, `%matplotlib ...` — их убираем
IMPORT_RE = re.compile(
    r"^\s*(?:"
    r"import\s+[\w\s,\.]+"
    r"|from\s+[\w\.]+\s+import\s+[\w\s,\*]+"
    r"|%matplotlib\s+\w+"
    r"|import\s+matplotlib(?:\.\w+)?\s+as\s+\w+"
    r")\s*$"
)

KEEP_IN_CELL = (
    "import subprocess, sys",          # установка библиотек — оставим
    "from io import StringIO",         # не критично, оставим
)

for c in cells:
    if c["cell_type"] != "code":
        continue
    src = cell_src(c)
    if any(k in src for k in KEEP_IN_CELL):
        continue
    lines = src.splitlines()
    out = [ln for ln in lines if not IMPORT_RE.match(ln)]
    # убираем пустые строки, оставшиеся после удаления импортов
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).splitlines()
    set_src(c, "\n".join(out) + ("\n" if out else ""))


# ─── 6. Сброс outputs и execution_count ───────────────────────────────
for c in cells:
    if c["cell_type"] == "code":
        c["outputs"] = []
        c["execution_count"] = None
        c.pop("outputId", None)
    c["metadata"].pop("colab", None)


# ─── 7. Чистим metadata ноутбука ──────────────────────────────────────
nb["metadata"].pop("colab", None)
nb["metadata"] = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.10",
    },
}
nb["nbformat"] = 4
nb["nbformat_minor"] = 5


# ─── 8. Сохранение ────────────────────────────────────────────────────
DST.write_text(
    json.dumps(nb, ensure_ascii=False, indent=1),
    encoding="utf-8",
)
print(f"✓ Готово: {DST}")
print(f"  Ячеек было:  {len(json.loads(SRC.read_text(encoding='utf-8'))['cells'])}")
print(f"  Ячеек стало: {len(cells)}")