
(() => {
    "use strict";

    async function checkAuthentication() {
        try {
            const response = await fetch(
                "https://scheme-finder-csp-backend.onrender.com/api/auth/session",
                {
                    method: "GET",
                    credentials: "include",
                    cache: "no-store",
                    headers: {
                        "Accept": "application/json"
                    }
                }
            );

            if (!response.ok) {
                throw new Error("Session verification failed.");
            }

            const data = await response.json();

            if (!data.authenticated) {
                window.location.replace("login.html");
                return;
            }

            document.documentElement.dataset.authenticated = "true";

        } catch (error) {
            console.error("Authentication check failed:", error);
            window.location.replace("login.html");
        }
    }

    checkAuthentication();
})();
