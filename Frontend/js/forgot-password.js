
(() => {
    "use strict";

    const API_BASE = "http://127.0.0.1:5000";

    window.sendOTP = async function () {
        // Keep the existing button's onclick name to avoid HTML errors.
        const contact = document.getElementById("userContact").value.trim();

        if (!contact) {
            alert("Enter your registered email address.");
            return;
        }

        const button = document.querySelector("#emailSection .reset-button");

        try {
            if (button) {
                button.disabled = true;
                button.textContent = "Sending reset link...";
            }

            const response = await fetch(
                `${API_BASE}/api/auth/forgot-password`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    cache: "no-store",
                    body: JSON.stringify({ contact })
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || "Unable to request reset.");
            }

            alert(data.message);
        } catch (error) {
            console.error("Password reset request failed:", error);
            alert(error.message || "Unable to send the reset link.");
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML =
                    'Send Reset Link <i class="fa-solid fa-arrow-right"></i>';
            }
        }
    };
})();
