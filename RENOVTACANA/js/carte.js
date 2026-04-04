/**
 * carte.js — Carte interactive Leaflet
 * Canalisations + overlay chantiers + sélection de zone
 */

const GEOJSON_CANALISATIONS = "http://127.0.0.1:8000/api/geojson/canalisations";
const GEOJSON_CHANTIERS     = "../assets/data/chantiers.geojson";

let map, geoLayer, chantiersLayer, drawLayer, selectRectangle;
let allFeatures    = [];
let activeFilter   = "all";
let showChantiers  = false;
let selectMode     = false;

// ── Init ──────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async function () {
    initMap();
    await loadCanalisations();
    initFilters();
    initSearch();
    initChantiers();
    initZoneSelect();
});

// ── Carte Leaflet ─────────────────────────────────────────
function initMap() {
    map = L.map("map", {
        center: [43.718, 7.330],
        zoom:   12,
        zoomControl: false,
    });

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 20,
    }).addTo(map);

    L.control.zoom({ position: "topright" }).addTo(map);
    L.control.scale({ position: "bottomleft", imperial: false, maxWidth: 200 }).addTo(map);
}

// ── Canalisations ─────────────────────────────────────────
async function loadCanalisations() {
    try {
        document.getElementById("map-loading").querySelector("span").textContent = 
            "Chargement des 55 524 canalisations…";
        const res  = await fetch(GEOJSON_CANALISATIONS);
        const data = await res.json();
        allFeatures = data.features || [];
        renderLayer(allFeatures);
        document.getElementById("map-count").textContent =
            `${allFeatures.length.toLocaleString("fr-FR")} canalisations`;
        document.getElementById("map-loading").style.display = "none";
        if (geoLayer) map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] });
    } catch(e) {
        document.getElementById("map-loading").innerHTML =
            `<span style="color:var(--c-danger)">⚠️ Erreur chargement des données</span>`;
    }
}

function renderLayer(features) {
    if (geoLayer) map.removeLayer(geoLayer);
    geoLayer = L.geoJSON({ type: "FeatureCollection", features }, {
        style: f => getLineStyle(f.properties.crit),
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.on("mouseover", e => { layer.setStyle({ weight: 5, opacity: 1 }); showTooltip(e, p); });
            layer.on("mousemove", e => moveTooltip(e));
            layer.on("mouseout",  ()  => { if (!selectMode) geoLayer.resetStyle(layer); hideTooltip(); });
            layer.on("click",     ()  => {
                if (selectMode) return;
                if (p.adr) window.location.href = `adresses.html?adresse=${encodeURIComponent(p.adr)}`;
            });
        }
    }).addTo(map);
}

function getLineStyle(crit) {
    if (crit == null)  return { color: "#475569", weight: 1.5, opacity: 0.5 };
    if (crit >= 70)    return { color: "#ef4444", weight: 3,   opacity: 0.9 };
    if (crit >= 40)    return { color: "#f97316", weight: 2.5, opacity: 0.85 };
    if (crit >= 20)    return { color: "#eab308", weight: 2,   opacity: 0.75 };
    if (crit >= 10)    return { color: "#84cc16", weight: 1.8, opacity: 0.7 };
    return                    { color: "#00d4aa", weight: 1.5, opacity: 0.65 };
}

// ── Overlay chantiers ─────────────────────────────────────
async function initChantiers() {
    try {
        const res  = await fetch(GEOJSON_CHANTIERS);
        const data = await res.json();

        const etatColor = {
            "Planifié":                    "#22c55e",
            "Validé en planification":     "#00d4aa",
            "En attente de planification": "#64748b",
        };

        chantiersLayer = L.geoJSON(data, {
            pointToLayer: function (feature, latlng) {
                const color = etatColor[feature.properties.etat] || "#64748b";
                return L.circleMarker(latlng, {
                    radius: 5, fillColor: color, color: "#0a0e14",
                    weight: 1, fillOpacity: 0.85,
                });
            },
            onEachFeature: function (feature, layer) {
                const p = feature.properties;
                layer.bindPopup(`
                    <div style="font-family:monospace;font-size:12px;min-width:200px">
                        <div style="font-weight:700;margin-bottom:6px;color:#00d4aa">${p.id}</div>
                        <div style="color:#888;margin-bottom:4px">${p.libelle}</div>
                        <div><b>${p.commune}</b></div>
                        <div style="color:#888;margin-top:4px">${p.debut} → ${p.fin}</div>
                        <div style="margin-top:4px;padding:2px 8px;background:rgba(0,212,170,0.1);
                             border:1px solid rgba(0,212,170,0.3);border-radius:999px;
                             display:inline-block;font-size:11px">${p.etat}</div>
                    </div>
                `, { className: "dark-popup" });
            }
        });
    } catch(e) { console.warn("Chantiers non chargés", e); }

    document.getElementById("toggle-chantiers")?.addEventListener("click", function () {
        showChantiers = !showChantiers;
        this.classList.toggle("active", showChantiers);
        if (showChantiers) {
            chantiersLayer?.addTo(map);
        } else {
            chantiersLayer && map.removeLayer(chantiersLayer);
        }
    });
}

// ── Sélection de zone ─────────────────────────────────────
function initZoneSelect() {
    drawLayer = new L.FeatureGroup().addTo(map);

    // Handler rectangle directement (sans passer par le contrôle UI)
    let drawHandler = null;

    const btn = document.getElementById("toggle-select");
    btn?.addEventListener("click", function () {
        selectMode = !selectMode;
        btn.classList.toggle("active", selectMode);

        if (selectMode) {
            // Activer le dessin rectangle directement
            drawHandler = new L.Draw.Rectangle(map, {
                shapeOptions: { color: "#00d4aa", weight: 2, fillOpacity: 0.08, dashArray: "6 4" }
            });
            drawHandler.enable();
            document.getElementById("map-count").textContent = "Dessinez un rectangle…";
        } else {
            drawHandler?.disable();
            drawLayer.clearLayers();
            document.getElementById("zone-panel").style.display = "none";
            applyFilter();
        }
    });

    map.on(L.Draw.Event.CREATED, function (e) {
        drawLayer.clearLayers();
        drawLayer.addLayer(e.layer);
        const bounds = e.layer.getBounds();
        // Désactiver le mode dessin après tracé
        selectMode = false;
        document.getElementById("toggle-select")?.classList.remove("active");
        analyseZone(bounds);
    });

    document.getElementById("zone-close")?.addEventListener("click", function () {
        document.getElementById("zone-panel").style.display = "none";
        drawLayer.clearLayers();
        selectMode = false;
        drawHandler?.disable();
        document.getElementById("toggle-select")?.classList.remove("active");
        applyFilter();
    });
}

function analyseZone(bounds) {
    const inside = allFeatures.filter(f => {
        const coords = f.geometry.coordinates;
        return coords.some(pt => bounds.contains(L.latLng(pt[1], pt[0])));
    });

    if (!inside.length) return;

    const total   = inside.length;
    const crits   = inside.filter(f => (f.properties.crit ?? 0) >= 70).length;
    const critMoy = inside.filter(f => f.properties.crit != null)
        .reduce((s, f, _, a) => s + f.properties.crit / a.length, 0);

    // Highlight les canalisations sélectionnées
    renderLayer(inside);

    document.getElementById("zone-stats").innerHTML = `
        <div class="zone-stat">
            <div class="zone-stat__val">${total}</div>
            <div class="zone-stat__label">Canalisations</div>
        </div>
        <div class="zone-stat">
            <div class="zone-stat__val" style="color:var(--c-danger)">${crits}</div>
            <div class="zone-stat__label">Critiques</div>
        </div>
        <div class="zone-stat">
            <div class="zone-stat__val">${critMoy.toFixed(1)}%</div>
            <div class="zone-stat__label">Crit. moy.</div>
        </div>
    `;

    // Stocker tous les IDs dans sessionStorage pour la page adresses
    const ids = inside.map(f => f.properties.id);
    sessionStorage.setItem("zone_ids", JSON.stringify(ids));
    sessionStorage.setItem("zone_count", total);

    document.getElementById("zone-voir-adresses").href = "adresses.html?zone=1";
    document.getElementById("zone-title").textContent =
        `${total} canalisation${total > 1 ? "s" : ""} dans la zone`;
    document.getElementById("zone-panel").style.display = "block";
    document.getElementById("map-count").textContent = `${total} dans la zone`;
}

// ── Filtres rapides ───────────────────────────────────────
function initFilters() {
    document.querySelectorAll(".map-filter-btn").forEach(btn => {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".map-filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeFilter = btn.dataset.filter;
            applyFilter();
        });
    });
}

function applyFilter() {
    let filtered;
    switch (activeFilter) {
        case "critique":  filtered = allFeatures.filter(f => (f.properties.crit ?? 0) >= 70); break;
        case "attention": filtered = allFeatures.filter(f => { const c = f.properties.crit ?? 0; return c >= 40 && c < 70; }); break;
        case "bon":       filtered = allFeatures.filter(f => (f.properties.crit ?? 0) < 40); break;
        default:          filtered = allFeatures;
    }
    renderLayer(filtered);
    document.getElementById("map-count").textContent =
        `${filtered.length.toLocaleString("fr-FR")} canalisations`;
    if (filtered.length > 0 && geoLayer)
        map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] });
}

// ── Recherche ─────────────────────────────────────────────
function initSearch() {
    const form = document.getElementById("search-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        const query = form.querySelector(".search-bar__input").value.trim().toLowerCase();
        if (!query) return;

        const matches = allFeatures.filter(f =>
            f.properties.adr?.toLowerCase().includes(query)
        );

        if (matches.length > 0) {
            renderLayer(matches);
            document.getElementById("map-count").textContent =
                `${matches.length} résultat${matches.length > 1 ? "s" : ""} pour "${query}"`;
            if (geoLayer) map.fitBounds(geoLayer.getBounds(), { padding: [40, 40] });
        } else {
            window.location.href = `adresses.html?adresse=${encodeURIComponent(query)}`;
        }
    });

    form.querySelector(".search-bar__clear-button")?.addEventListener("click", function () {
        renderLayer(allFeatures);
        document.getElementById("map-count").textContent =
            `${allFeatures.length.toLocaleString("fr-FR")} canalisations`;
        document.querySelectorAll(".map-filter-btn").forEach(b => b.classList.remove("active"));
        document.querySelector('[data-filter="all"]')?.classList.add("active");
    });
}

// ── Tooltip ───────────────────────────────────────────────
const tooltip = document.getElementById("map-tooltip");

function showTooltip(e, p) {
    document.getElementById("tt-id").textContent   = p.id || "";
    document.getElementById("tt-adr").textContent  = p.adr || "—";
    document.getElementById("tt-mat").textContent  = p.mat || "—";
    document.getElementById("tt-diam").textContent = p.diam ? `${p.diam} mm` : "—";
    document.getElementById("tt-long").textContent = p.long ? `${p.long} m` : "—";
    const crit = p.crit;
    if (crit != null) {
        document.getElementById("tt-crit-val").textContent = `${crit.toFixed(1)}%`;
        const fill = document.getElementById("tt-fill");
        fill.style.width      = `${Math.min(crit,100)}%`;
        fill.style.background = crit >= 70 ? "#ef4444" : crit >= 40 ? "#f97316" : "#00d4aa";
    } else {
        document.getElementById("tt-crit-val").textContent = "—";
        document.getElementById("tt-fill").style.width = "0%";
    }
    tooltip.style.display = "block";
    moveTooltip(e);
}

function moveTooltip(e) {
    const rect = document.getElementById("map").getBoundingClientRect();
    let x = e.originalEvent.clientX - rect.left + 14;
    let y = e.originalEvent.clientY - rect.top  - 20;
    if (x + 240 > rect.width)  x -= 260;
    if (y + 200 > rect.height) y -= 200;
    tooltip.style.left = `${x}px`;
    tooltip.style.top  = `${y}px`;
}

function hideTooltip() { tooltip.style.display = "none"; }
