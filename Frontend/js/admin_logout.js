
(() => {
    "use strict";

    const API_BASE_URL = "https://scheme-finder-csp-backend.onrender.com";

    // Sidebar toggle
    window.toggleSidebar = function () {
        document.getElementById("sidebar")?.classList.toggle("open");
    };

    // Stay logged in: return to the dashboard without logging out.
    window.goDashboard = function () {
        window.location.href = "admin_dashboard.html";
    };

    // Yes, Logout: invalidate the Flask session first.
    window.logoutAdmin = async function () {
        const button = document.querySelector(".logout");

        try {
            if (button) {
                button.disabled = true;
                button.textContent = "Signing out...";
            }

            const response = await fetch(
                `${API_BASE_URL}/api/admin/logout`,
                {
                    method: "POST",
                    credentials: "include",
                    cache: "no-store",
                    headers: {
                        "Accept": "application/json"
                    }
                }
            );

            if (!response.ok) {
                throw new Error("Server logout failed.");
            }

            // Remove client-side state only after server logout succeeds.
            sessionStorage.clear();

            // Replace the current page in browser history.
            window.location.replace("admin_login.html");

        } catch (error) {
            console.error("Logout failed:", error);

            if (button) {
                button.disabled = false;
                button.innerHTML =
                    '<i class="fa-solid fa-right-from-bracket"></i> Yes, Logout';
            }

            alert("Unable to log out. Please try again.");
        }
    };
})();
