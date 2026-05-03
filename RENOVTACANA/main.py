"""
RenovTaCana — Backend FastAPI
Base SQLite avec vraies données Métropole Nice Côte d'Azur
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3, os, re
import unicodedata

app = FastAPI(title="RenovTaCana API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.join(os.path.dirname(__file__), "sqlite", "renovtacana.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.create_function("normalize_text", 1, normalize_text)
    return conn


def normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Parametres metier du score de priorite (faciles a ajuster)
SCORE_REFERENCE_YEAR = 2024
SCORE_FUITE_MULTIPLIER = 2.0
SCORE_MAX_AGE_BONUS = 20.0
SCORE_AGE_BONUS_PER_YEAR = 0.5
SCORE_ANCIENNETE_50_PLUS_LABEL = "superieur a 50 ans"


def calculate_score_priorite_details(criticite, nb_fuites, annee_pose, anciennete):
    """
    Detaille le calcul du score de priorite pour une canalisation.

    Formule:
    - base_criticite = criticite
    - bonus_fuites = nb_fuites * SCORE_FUITE_MULTIPLIER
    - bonus_age:
      * SCORE_MAX_AGE_BONUS si anciennete == "sup??rieur ?? 50 ans"
      * sinon min(SCORE_MAX_AGE_BONUS, age_years * SCORE_AGE_BONUS_PER_YEAR)
    - score_priorite = base_criticite + bonus_fuites + bonus_age
    """
    base_criticite = float(criticite or 0)
    nb_fuites_val = int(nb_fuites or 0)
    bonus_fuites = nb_fuites_val * SCORE_FUITE_MULTIPLIER

    year_pose = annee_pose if annee_pose is not None else SCORE_REFERENCE_YEAR
    age_years = max(0, SCORE_REFERENCE_YEAR - year_pose)

    anciennete_norm = normalize_text(anciennete or "")
    is_50_plus = anciennete_norm == SCORE_ANCIENNETE_50_PLUS_LABEL
    if is_50_plus:
        bonus_age = SCORE_MAX_AGE_BONUS
    else:
        bonus_age = min(SCORE_MAX_AGE_BONUS, age_years * SCORE_AGE_BONUS_PER_YEAR)

    score = round(base_criticite + bonus_fuites + bonus_age, 1)

    return {
        "score": score,
        "base_criticite": round(base_criticite, 1),
        "bonus_fuites": round(bonus_fuites, 1),
        "bonus_age": round(bonus_age, 1),
        "age_years": age_years,
        "reference_year": SCORE_REFERENCE_YEAR,
        "rules": {
            "fuite_multiplier": SCORE_FUITE_MULTIPLIER,
            "age_bonus_per_year": SCORE_AGE_BONUS_PER_YEAR,
            "age_bonus_max": SCORE_MAX_AGE_BONUS,
            "anciennete_50_plus_label": SCORE_ANCIENNETE_50_PLUS_LABEL,
        },
    }


def calculate_score_priorite(criticite, nb_fuites, annee_pose, anciennete):
    """Compatibilite: retourne uniquement la valeur finale."""
    return calculate_score_priorite_details(
        criticite, nb_fuites, annee_pose, anciennete
    )["score"]


def enrich_with_score(rows):
    """Ajoute score_priorite calcule en Python sur chaque ligne."""
    enriched = []
    for row in rows:
        item = dict(row)
        item["score_priorite"] = calculate_score_priorite(
            item.get("criticite"),
            item.get("nb_fuites"),
            item.get("annee_pose"),
            item.get("anciennete"),
        )
        enriched.append(item)
    return enriched


# ── CANALISATIONS ─────────────────────────────────────────
ALLOWED_SORT_COLS = {
    "facilityid",
    "adresse",
    "materiau",
    "diametre",
    "longueur",
    "annee_pose",
    "nb_fuites",
    "criticite",
    "anciennete",
    "score_priorite",
}


@app.get("/api/canalisations")
def get_canalisations(
    adresse: str = Query(default=""),
    commune: str = Query(default=""),
    materiau: str = Query(default=""),
    anciennete: str = Query(default=""),
    statut: str = Query(default=""),
    search: str = Query(default=""),
    crit_min: float = Query(default=0),
    crit_max: float = Query(default=100),
    sort_col: str = Query(default="score_priorite"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    conn = get_db()
    cur = conn.cursor()

    filters = ["1=1"]
    params = []

    if adresse:
        filters.append("""
            (
                normalize_text(adresse) LIKE '%' || normalize_text(?) || '%'
                OR normalize_text(adresse || ' ' || COALESCE(commune, '')) LIKE '%' || normalize_text(?) || '%'
            )
        """)
        params.extend([adresse, adresse])
    if commune:
        filters.append("normalize_text(commune) LIKE '%' || normalize_text(?) || '%'")
        params.append(commune)
    if materiau:
        filters.append("materiau = ?")
        params.append(materiau)
    if anciennete:
        filters.append("anciennete = ?")
        params.append(anciennete)
    if search:
        filters.append("LOWER(facilityid) LIKE LOWER(?)")
        params.append(f"%{search}%")
    if statut == "critique":
        filters.append("criticite >= 70")
    elif statut == "attention":
        filters.append("criticite >= 40 AND criticite < 70")
    elif statut == "bon":
        filters.append("(criticite < 40 OR criticite IS NULL)")

    filters.append("(criticite IS NULL OR (criticite >= ? AND criticite <= ?))")
    params += [crit_min, crit_max]

    where = " AND ".join(filters)
    col = sort_col if sort_col in ALLOWED_SORT_COLS else "score_priorite"
    direction = "DESC" if sort_dir == "desc" else "ASC"

    cur.execute(f"SELECT COUNT(*) FROM canalisations WHERE {where}", params)
    total = cur.fetchone()[0]

    if col == "score_priorite":
        cur.execute(
            f"""
            SELECT facilityid, adresse, commune, materiau, diametre, longueur,
                   annee_pose, nb_fuites, vetuste, categorie, anciennete,
                   densite, criticite
            FROM canalisations
            WHERE {where}
        """,
            params,
        )
        rows_all = enrich_with_score(cur.fetchall())
        rows_all.sort(
            key=lambda r: (r["score_priorite"] is None, r["score_priorite"]),
            reverse=(direction == "DESC"),
        )
        rows = rows_all[offset : offset + limit]
    else:
        cur.execute(
            f"""
            SELECT facilityid, adresse, commune, materiau, diametre, longueur,
                   annee_pose, nb_fuites, vetuste, categorie, anciennete,
                   densite, criticite
            FROM canalisations
            WHERE {where}
            ORDER BY {col} {direction} NULLS LAST
            LIMIT ? OFFSET ?
        """,
            params + [limit, offset],
        )
        rows = enrich_with_score(cur.fetchall())
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "canalisations": rows}


@app.get("/api/adresses/suggestions")
def get_adresse_suggestions(
    q: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=10),
):
    normalized_query = normalize_text(q)
    if len(normalized_query) < 2:
        return {"query": q, "suggestions": []}

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        WITH base AS (
            SELECT
                adresse,
                commune,
                COUNT(*) AS nb,
                normalize_text(adresse) AS n_adresse,
                normalize_text(COALESCE(commune, '')) AS n_commune,
                normalize_text(adresse || ' ' || COALESCE(commune, '')) AS n_full
            FROM canalisations
            WHERE adresse != ''
            GROUP BY adresse, commune
        ),
        q AS (
            SELECT normalize_text(?) AS nq
        ),
        scored AS (
            SELECT
                b.adresse,
                b.commune,
                b.nb,
                CASE
                    WHEN b.n_adresse = q.nq OR b.n_full = q.nq THEN 0
                    WHEN b.n_adresse LIKE q.nq || '%' THEN 1
                    WHEN b.n_full LIKE q.nq || '%' THEN 2
                    WHEN INSTR(b.n_adresse, ' ' || q.nq) > 0 THEN 3
                    WHEN INSTR(b.n_full, ' ' || q.nq) > 0 THEN 4
                    WHEN INSTR(b.n_adresse, q.nq) > 0 THEN 5
                    WHEN INSTR(b.n_full, q.nq) > 0 THEN 6
                    ELSE 9
                END AS score,
                CASE
                    WHEN INSTR(b.n_adresse, q.nq) = 0 THEN 9999
                    ELSE INSTR(b.n_adresse, q.nq)
                END AS pos
            FROM base b
            CROSS JOIN q
            WHERE b.n_full LIKE '%' || q.nq || '%'
               OR b.n_adresse LIKE '%' || q.nq || '%'
               OR b.n_commune LIKE '%' || q.nq || '%'
        )
        SELECT adresse, commune, nb
        FROM scored
        ORDER BY score ASC, pos ASC, LENGTH(adresse) ASC, nb DESC
        LIMIT ?
    """,
        (q, limit),
    )

    suggestions = []
    for row in cur.fetchall():
        adresse = row["adresse"] or ""
        commune = row["commune"] or ""
        full_label = f"{adresse}, {commune}" if commune else adresse
        suggestions.append(
            {
                "adresse": adresse,
                "commune": commune,
                "label": full_label,
                "count": row["nb"],
            }
        )

    conn.close()
    return {"query": q, "suggestions": suggestions}


# ── DASHBOARD ─────────────────────────────────────────────
@app.get("/api/dashboard")
def get_dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*), SUM(longueur)/1000, AVG(criticite), SUM(nb_fuites) FROM canalisations"
    )
    r = cur.fetchone()
    total, km, moy_crit, total_fuites = (
        r[0],
        round(r[1] or 0, 1),
        round(r[2] or 0, 1),
        int(r[3] or 0),
    )

    cur.execute("SELECT COUNT(*) FROM canalisations WHERE criticite >= 70")
    critiques = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM canalisations WHERE criticite >= 40 AND criticite < 70"
    )
    attention = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM canalisations WHERE criticite < 40 AND criticite IS NOT NULL"
    )
    bon = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM canalisations WHERE criticite IS NULL")
    non_eval = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM chantiers")
    nb_chantiers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chantiers WHERE etat='Planifié'")
    planifies = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chantiers WHERE etat='Validé en planification'")
    valides = cur.fetchone()[0]

    # Matériaux
    cur.execute("""
        SELECT materiau, COUNT(*) as n, ROUND(AVG(criticite),1) as moy
        FROM canalisations WHERE materiau != ''
        GROUP BY materiau ORDER BY n DESC LIMIT 8
    """)
    materiaux = [{"nom": r[0], "count": r[1], "crit_moy": r[2]} for r in cur.fetchall()]

    # Années de pose
    cur.execute("""
        SELECT
            CASE
                WHEN annee_pose < 1950 THEN 'Avant 1950'
                WHEN annee_pose < 1970 THEN '1950–1969'
                WHEN annee_pose < 1990 THEN '1970–1989'
                WHEN annee_pose < 2000 THEN '1990–1999'
                WHEN annee_pose < 2010 THEN '2000–2009'
                WHEN annee_pose IS NOT NULL THEN '2010+'
                ELSE 'Inconnue'
            END as periode,
            COUNT(*) as n,
            ROUND(AVG(criticite),1) as moy_crit
        FROM canalisations GROUP BY periode ORDER BY periode
    """)
    annees = [
        {"periode": r[0], "count": r[1], "crit_moy": r[2]} for r in cur.fetchall()
    ]

    # Top 15 rues prioritaires (score calcule en Python)
    cur.execute(
        """
        SELECT adresse, commune, criticite, nb_fuites, annee_pose, anciennete, longueur
        FROM canalisations
        WHERE adresse != '' AND criticite IS NOT NULL
    """
    )
    grouped = {}
    for r in cur.fetchall():
        key = (r["adresse"], r["commune"])
        score = calculate_score_priorite(
            r["criticite"], r["nb_fuites"], r["annee_pose"], r["anciennete"]
        )
        g = grouped.setdefault(
            key,
            {
                "adresse": r["adresse"],
                "commune": r["commune"],
                "nb": 0,
                "crit_sum": 0.0,
                "score": float("-inf"),
                "fuites": 0,
                "longueur": 0.0,
            },
        )
        g["nb"] += 1
        g["crit_sum"] += float(r["criticite"] or 0)
        g["score"] = max(g["score"], score)
        g["fuites"] += int(r["nb_fuites"] or 0)
        g["longueur"] += float(r["longueur"] or 0)

    top_rues = sorted(grouped.values(), key=lambda x: x["score"], reverse=True)[:15]
    top_rues = [
        {
            "adresse": t["adresse"],
            "commune": t["commune"],
            "nb": t["nb"],
            "crit_moy": round((t["crit_sum"] / t["nb"]) if t["nb"] else 0, 1),
            "score": round(t["score"], 1),
            "fuites": t["fuites"],
            "longueur": round(t["longueur"], 0),
        }
        for t in top_rues
    ]

    # Chantiers par état
    cur.execute("SELECT etat, COUNT(*) FROM chantiers GROUP BY etat")
    chantiers_etat = [{"etat": r[0], "count": r[1]} for r in cur.fetchall()]

    conn.close()
    return {
        "total_canalisations": total,
        "km_total": km,
        "criticite_moyenne": moy_crit,
        "total_fuites": total_fuites,
        "critiques": critiques,
        "attention": attention,
        "bon": bon,
        "non_eval": non_eval,
        "nb_chantiers": nb_chantiers,
        "planifies": planifies,
        "valides": valides,
        "materiaux": materiaux,
        "annees": annees,
        "top_rues": top_rues,
        "chantiers_etat": chantiers_etat,
    }


# ── TOP RUES PRIORITAIRES (plan de travaux) ───────────────
@app.get("/api/plan-travaux")
def get_plan_travaux(
    commune: str = Query(default=""),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
):
    conn = get_db()
    cur = conn.cursor()
    filters = ["adresse != ''", "criticite IS NOT NULL"]
    params = []
    if commune:
        filters.append("LOWER(commune) LIKE LOWER(?)")
        params.append(f"%{commune}%")
    where = " AND ".join(filters)

    cur.execute(
        f"""
        SELECT adresse, commune, criticite, nb_fuites, annee_pose, anciennete, longueur, materiau
        FROM canalisations
        WHERE {where}
    """,
        params,
    )
    grouped = {}
    for r in cur.fetchall():
        key = (r["adresse"], r["commune"])
        score = calculate_score_priorite(
            r["criticite"], r["nb_fuites"], r["annee_pose"], r["anciennete"]
        )
        g = grouped.setdefault(
            key,
            {
                "adresse": r["adresse"],
                "commune": r["commune"],
                "nb_canalisations": 0,
                "crit_sum": 0.0,
                "score_max": float("-inf"),
                "total_fuites": 0,
                "longueur_tot": 0.0,
                "materiaux_set": set(),
                "plus_ancienne": None,
            },
        )
        g["nb_canalisations"] += 1
        g["crit_sum"] += float(r["criticite"] or 0)
        g["score_max"] = max(g["score_max"], score)
        g["total_fuites"] += int(r["nb_fuites"] or 0)
        g["longueur_tot"] += float(r["longueur"] or 0)
        if r["materiau"]:
            g["materiaux_set"].add(r["materiau"])
        if r["annee_pose"] is not None:
            g["plus_ancienne"] = (
                r["annee_pose"]
                if g["plus_ancienne"] is None
                else min(g["plus_ancienne"], r["annee_pose"])
            )

    rows_all = []
    for g in grouped.values():
        rows_all.append(
            {
                "adresse": g["adresse"],
                "commune": g["commune"],
                "nb_canalisations": g["nb_canalisations"],
                "crit_moy": round(
                    (g["crit_sum"] / g["nb_canalisations"])
                    if g["nb_canalisations"]
                    else 0,
                    1,
                ),
                "score_max": round(g["score_max"], 1),
                "total_fuites": int(g["total_fuites"]),
                "longueur_tot": round(g["longueur_tot"], 0),
                "materiaux": ", ".join(sorted(g["materiaux_set"])),
                "plus_ancienne": g["plus_ancienne"],
            }
        )

    rows_all.sort(key=lambda x: x["score_max"], reverse=True)
    total = len(rows_all)
    rows = rows_all[offset : offset + limit]
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "rues": rows}


# ── CANALISATIONS PAR IDs (zone carte) ────────────────────
from typing import List


@app.post("/api/canalisations/zone")
def get_canalisations_zone(payload: dict):
    ids = payload.get("ids", [])
    limit = int(payload.get("limit", 100))
    offset = int(payload.get("offset", 0))

    if not ids:
        return {"total": 0, "canalisations": []}

    conn = get_db()
    cur = conn.cursor()
    ph = ",".join("?" * len(ids))

    cur.execute(f"SELECT COUNT(*) FROM canalisations WHERE facilityid IN ({ph})", ids)
    total = cur.fetchone()[0]

    cur.execute(
        f"""
        SELECT facilityid, adresse, commune, materiau, diametre, longueur,
               annee_pose, nb_fuites, vetuste, categorie, anciennete,
               densite, criticite
        FROM canalisations
        WHERE facilityid IN ({ph})
    """,
        ids,
    )
    rows_all = enrich_with_score(cur.fetchall())
    rows_all.sort(key=lambda r: r["score_priorite"], reverse=True)
    rows = rows_all[offset : offset + limit]
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "canalisations": rows}


# ── STATS GLOBALES ────────────────────────────────────────
@app.get("/api/stats")
def get_stats():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM canalisations")
    total = cur.fetchone()[0]

    cur.execute("SELECT AVG(criticite) FROM canalisations WHERE criticite IS NOT NULL")
    moy_crit = round(cur.fetchone()[0] or 0, 1)

    cur.execute("SELECT COUNT(*) FROM canalisations WHERE criticite >= 70")
    critiques = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM canalisations WHERE criticite >= 40 AND criticite < 70"
    )
    attention = cur.fetchone()[0]

    cur.execute(
        "SELECT SUM(longueur)/1000 FROM canalisations WHERE longueur IS NOT NULL"
    )
    km_total = round(cur.fetchone()[0] or 0, 1)

    cur.execute("SELECT COUNT(*) FROM chantiers")
    nb_chantiers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM chantiers WHERE etat = 'Planifié'")
    chantiers_planifies = cur.fetchone()[0]

    cur.execute(
        "SELECT materiau, COUNT(*) as n FROM canalisations WHERE materiau != '' GROUP BY materiau ORDER BY n DESC LIMIT 6"
    )
    materiaux = [{"nom": r[0], "count": r[1]} for r in cur.fetchall()]

    cur.execute("""
        SELECT
            CASE
                WHEN criticite >= 70 THEN 'Critique'
                WHEN criticite >= 40 THEN 'Attention'
                WHEN criticite IS NOT NULL THEN 'Bon état'
                ELSE 'Non évalué'
            END as niveau,
            COUNT(*) as n
        FROM canalisations
        GROUP BY niveau
    """)
    repartition = [{"niveau": r[0], "count": r[1]} for r in cur.fetchall()]

    conn.close()
    return {
        "total_canalisations": total,
        "km_total": km_total,
        "criticite_moyenne": moy_crit,
        "critiques": critiques,
        "attention": attention,
        "nb_chantiers": nb_chantiers,
        "chantiers_planifies": chantiers_planifies,
        "materiaux": materiaux,
        "repartition_criticite": repartition,
    }


# ── STATS PAR ADRESSE ─────────────────────────────────────
@app.get("/api/stats/adresse")
def get_stats_adresse(adresse: str = Query(default="")):
    if not adresse:
        return {}
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COUNT(*), AVG(criticite), SUM(longueur), MAX(criticite),
               COUNT(CASE WHEN criticite >= 70 THEN 1 END),
               SUM(nb_fuites)
        FROM canalisations
        WHERE
            normalize_text(adresse) LIKE '%' || normalize_text(?) || '%'
            OR normalize_text(adresse || ' ' || COALESCE(commune, '')) LIKE '%' || normalize_text(?) || '%'
    """,
        (adresse, adresse),
    )
    r = cur.fetchone()
    conn.close()

    return {
        "nb_canalisations": r[0],
        "criticite_moyenne": round(r[1] or 0, 1),
        "longueur_totale": round(r[2] or 0, 1),
        "criticite_max": round(r[3] or 0, 1),
        "critiques": r[4] or 0,
        "nb_fuites_total": int(r[5] or 0),
    }


# ── CHANTIERS ─────────────────────────────────────────────
@app.get("/api/chantiers")
def get_chantiers(
    commune: str = Query(default=""),
    etat: str = Query(default=""),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    conn = get_db()
    cur = conn.cursor()
    filters = ["1=1"]
    params = []
    if commune:
        filters.append("LOWER(commune) LIKE LOWER(?)")
        params.append(f"%{commune}%")
    if etat:
        filters.append("etat = ?")
        params.append(etat)
    where = " AND ".join(filters)

    cur.execute(f"SELECT COUNT(*) FROM chantiers WHERE {where}", params)
    total = cur.fetchone()[0]

    cur.execute(
        f"""
        SELECT num_op, etat, date_debut, date_fin, commune, libelle
        FROM chantiers WHERE {where}
        ORDER BY date_debut ASC
        LIMIT ? OFFSET ?
    """,
        params + [limit, offset],
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "chantiers": rows}


# ── OPERATIONS ────────────────────────────────────────────
@app.get("/api/operations")
def get_operations(
    commune: str = Query(default=""),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    conn = get_db()
    cur = conn.cursor()
    filters = ["1=1"]
    params = []
    if commune:
        filters.append("LOWER(commune) LIKE LOWER(?)")
        params.append(f"%{commune}%")
    where = " AND ".join(filters)

    cur.execute(f"SELECT COUNT(*) FROM operations WHERE {where}", params)
    total = cur.fetchone()[0]

    cur.execute(
        f"""
        SELECT id_projet, titre, commune, localisation, type_op, demandeur, annee, cpi
        FROM operations WHERE {where}
        ORDER BY id_projet ASC
        LIMIT ? OFFSET ?
    """,
        params + [limit, offset],
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "operations": rows}


# ── VALEURS DISTINCTES pour filtres ──────────────────────
@app.get("/api/filtres")
def get_filtres():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT materiau FROM canalisations WHERE materiau != '' ORDER BY materiau"
    )
    materiaux = [r[0] for r in cur.fetchall()]
    cur.execute(
        "SELECT DISTINCT commune FROM canalisations WHERE commune != '' ORDER BY commune"
    )
    communes = [r[0] for r in cur.fetchall()]
    cur.execute(
        "SELECT DISTINCT anciennete FROM canalisations WHERE anciennete != '' ORDER BY anciennete"
    )
    anciennetes = [r[0] for r in cur.fetchall()]
    conn.close()
    return {"materiaux": materiaux, "communes": communes, "anciennetes": anciennetes}


# ── RECALCULER LES SCORES DE PRIORITE ────────────────────
@app.get("/api/score-priorite/explain")
def explain_score_priorite(
    criticite: float = Query(default=0),
    nb_fuites: int = Query(default=0),
    annee_pose: int | None = Query(default=None),
    anciennete: str = Query(default=""),
):
    """
    Retourne le detail du calcul du score de priorite.
    Exemple:
    /api/score-priorite/explain?criticite=65&nb_fuites=3&annee_pose=1970&anciennete=sup%C3%A9rieur%20%C3%A0%2050%20ans
    """
    details = calculate_score_priorite_details(
        criticite=criticite,
        nb_fuites=nb_fuites,
        annee_pose=annee_pose,
        anciennete=anciennete,
    )
    return {
        "inputs": {
            "criticite": criticite,
            "nb_fuites": nb_fuites,
            "annee_pose": annee_pose,
            "anciennete": anciennete,
        },
        "details": details,
    }


@app.post("/api/recalculate-scores")
def recalculate_scores():
    """
    Conserve pour compatibilite API.
    Le score de priorite est calcule a la volee en Python.
    """
    return {
        "message": "Aucune mise a jour SQL: score_priorite calcule dynamiquement en Python."
    }


from fastapi.responses import FileResponse, Response
import gzip as gz_lib


@app.get("/api/geojson/canalisations")
def get_geojson_canalisations():
    """Sert le GeoJSON compressé gzip directement"""
    path = os.path.join(
        os.path.dirname(__file__), "assets/data/canalisations.geojson.gz"
    )
    with open(path, "rb") as f:
        content = f.read()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Encoding": "gzip", "Cache-Control": "public, max-age=3600"},
    )


app.mount("/", StaticFiles(directory=".", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
