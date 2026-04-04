/**
 * search.js — Logique barre de recherche
 * RenovTaCana
 */
document.addEventListener("DOMContentLoaded", function () {

    const searchBars = document.querySelectorAll(".search-bar");

    searchBars.forEach(function (bar) {
        const input = bar.querySelector(".search-bar__input");
        const clearBtn = bar.querySelector(".search-bar__clear-button");

        if (!input) return;

        // Bouton effacer
        if (clearBtn) {
            clearBtn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                input.value = "";
                input.focus();
                toggleClearBtn(clearBtn, false);
            });
        }

        // Afficher/masquer le bouton clear selon contenu
        input.addEventListener("input", function () {
            if (clearBtn) toggleClearBtn(clearBtn, input.value.length > 0);
        });

        // État initial
        if (clearBtn) toggleClearBtn(clearBtn, input.value.length > 0);
    });

    function toggleClearBtn(btn, show) {
        btn.style.opacity = show ? "1" : "0";
        btn.style.pointerEvents = show ? "auto" : "none";
    }

});
