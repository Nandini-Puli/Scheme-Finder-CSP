
(() => {
    "use strict";

    const STORAGE_KEY = "schemeFinderAppearance";
    const VALID_PREFERENCES = ["light", "system", "dark"];

    function getSavedPreference() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);

            return VALID_PREFERENCES.includes(saved)
                ? saved
                : "light";
        } catch (error) {
            return "light";
        }
    }

    function getActualTheme(preference) {
        if (preference !== "system") {
            return preference;
        }

        const systemPrefersDark =
            window.matchMedia &&
            window.matchMedia("(prefers-color-scheme: dark)").matches;

        return systemPrefersDark ? "dark" : "light";
    }

    function applyTheme(preference = getSavedPreference()) {
        const actualTheme = getActualTheme(preference);

        document.documentElement.setAttribute(
            "data-theme",
            actualTheme
        );

        // Update the selected appearance button if present.
        const options = {
            light: document.getElementById("appearanceLight"),
            system: document.getElementById("appearanceSystem"),
            dark: document.getElementById("appearanceDark")
        };

        Object.entries(options).forEach(([option, element]) => {
            if (!element) return;

            const selected = option === preference;

            element.classList.toggle("active", selected);
            element.setAttribute("aria-pressed", String(selected));
        });
    }

    function savePreference(preference) {
        if (!VALID_PREFERENCES.includes(preference)) {
            return;
        }

        try {
            localStorage.setItem(STORAGE_KEY, preference);
        } catch (error) {
            console.warn(
                "Unable to save appearance preference.",
                error
            );
        }

        applyTheme(preference);
    }

    // Make the functions available to the Settings page.
    window.applySchemeFinderTheme = applyTheme;
    window.saveSchemeFinderAppearance = savePreference;

    // Apply the saved preference as early as possible.
    applyTheme();

    document.addEventListener("DOMContentLoaded", () => {
        const options = [
            ["appearanceLight", "light"],
            ["appearanceSystem", "system"],
            ["appearanceDark", "dark"]
        ];

        options.forEach(([id, preference]) => {
            const element = document.getElementById(id);

            if (element) {
                // Prevent duplicate registration by this script.
                if (element.dataset.appearanceBound === "true") {
                    return;
                }

                element.dataset.appearanceBound = "true";

                element.addEventListener("click", () => {
                    savePreference(preference);
                });
            }
        });

        // React to OS theme changes when System is selected.
        if (window.matchMedia) {
            const systemTheme = window.matchMedia(
                "(prefers-color-scheme: dark)"
            );

            const handleSystemThemeChange = () => {
                if (getSavedPreference() === "system") {
                    applyTheme("system");
                }
            };

            if (systemTheme.addEventListener) {
                systemTheme.addEventListener(
                    "change",
                    handleSystemThemeChange
                );
            } else if (systemTheme.addListener) {
                systemTheme.addListener(handleSystemThemeChange);
            }
        }

        applyTheme();
    });
})();
