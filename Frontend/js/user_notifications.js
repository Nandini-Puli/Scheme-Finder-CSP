
const USER_API_BASE = "http://127.0.0.1:5000/api";

async function loadUserNotificationBadge() {
    const badge = document.getElementById("unreadAlertCount");
    if (!badge) return;

    try {
        const response = await fetch(`${USER_API_BASE}/user/alerts`, {
            credentials: "include",
            headers: { "Accept": "application/json" }
        });

        if (!response.ok) {
            throw new Error("Could not load notification count");
        }

        const data = await response.json();

        const alerts = Array.isArray(data)
            ? data
            : (Array.isArray(data.alerts) ? data.alerts : []);

        const unreadCount = alerts.filter(alert =>
            alert.is_read === false ||
            alert.is_read === 0 ||
            alert.is_read === "0"
        ).length;

        badge.textContent = unreadCount > 99
            ? "99+"
            : String(unreadCount);

        badge.style.display = unreadCount > 0 ? "flex" : "none";
        badge.setAttribute(
            "aria-label",
            `${unreadCount} unread notifications`
        );
    } catch (error) {
        console.error("Notification badge error:", error);
    }
}

document.addEventListener("DOMContentLoaded", loadUserNotificationBadge);
