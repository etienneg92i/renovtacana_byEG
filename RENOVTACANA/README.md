# RenovTaCana — Arborescence du projet

```
RENOVTACANA/
├── pages/
│   ├── index.html          ← Page d'accueil (hero + recherche)
│   ├── carte.html          ← Page carte heatmap
│   └── index.html          ← Page résultats adresse (page d'accueil)
│
├── css/
│   └── style.css           ← Feuille de style unique (toutes les pages)
│
├── js/
│   ├── search.js           ← Logique barre de recherche (clear + focus)
│   └── index.js          ← Logique page index (adresses) (URL params + export)
│
└── assets/
    ├── images/
    │   ├── logo_entreprise.png
    │   ├── heatmap_prototype.png
    │   └── fond_page_accueil.png  (plus nécessaire — hero généré en CSS)
    └── icons/
        (icônes remplacées par des SVG inline — aucun fichier nécessaire)
```

## Chemins des liens
- `index.html` est dans `/pages/` → liens vers `carte.html` et `dashboard.html`
- CSS : `../css/style.css`
- JS  : `../js/search.js` et `../js/index.js`
- Assets : `../assets/images/` et `../assets/icons/`

## Polices utilisées (Google Fonts)
- **Syne** (700, 800) — titres et branding
- **DM Mono** (300, 400, 500) — corps de texte, données techniques
